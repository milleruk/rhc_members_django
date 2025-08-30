from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.db import IntegrityError, transaction

from django.views.decorators.http import require_POST
from django.utils.timezone import now

from members.models import Player
from .models import (
    Season,
    MembershipProduct,
    PaymentPlan,
    Subscription,
    resolve_match_fee_for,
    MatchFeeTariff,
)
from .forms import ConfirmSubscriptionForm
from .permissions import can_manage_player


def _get_active_season():
    season = Season.objects.filter(is_active=True).order_by("-start").first()
    if not season:
        raise Http404("No active season configured.")
    return season

def _can_manage_subscription(user, sub: Subscription) -> bool:
    if not user.is_authenticated:
        return False
    if sub.player and getattr(sub.player, "created_by_id", None) == user.id:
        return True
    return user.is_superuser or user.groups.filter(name__in=["Coach", "Captain", "Club Admin"]).exists()

def choose_product(request, player_id):
    player = get_object_or_404(Player, pk=player_id)
    if not can_manage_player(request.user, player):
        raise Http404()

    season = _get_active_season()

    # 🔒 If the player already has a membership this season, don't show products.
    existing = (
        Subscription.objects
        .filter(player=player, season=season, status__in=["pending", "active"])
        .select_related("product", "plan")
        .first()
    )
    has_active = existing is not None

    products = []
    #if has_active:
    #    messages.info(
    #        request,
    #        f"Membership already in place for {season.name}: "
    #        f"{existing.product.name} ({existing.get_status_display()})."
    #    )
    #else:
    products = (
        MembershipProduct.objects.filter(season=season, active=True)
        .select_related("category", "season")
        .prefetch_related("plans")
        .distinct()
    )
    # Optional filter by player type (via category.applies_to)
    products = [
        p for p in products
        if not p.category.applies_to.exists() or player.player_type in p.category.applies_to.all()
    ]
    # Attach resolved match fee for template display
    for p in products:
        p.match_fee = resolve_match_fee_for(p)

    context = {
        "player": player,
        "season": season,
        "products": products,        # [] if has_active
        "has_active": has_active,
        "existing_sub": existing,    # for banner details
    }
    return render(request, "memberships/choose_product.html", context)


def choose_plan(request, player_id, product_id):
    player = get_object_or_404(Player, pk=player_id)
    if not can_manage_player(request.user, player):
        raise Http404()

    product = get_object_or_404(
        MembershipProduct.objects.select_related("season", "category"),
        pk=product_id,
        active=True,
    )
    if not product.season.is_active:
        raise Http404("Product is not in active season.")

    # If player already has a membership for this season, bounce
    season = product.season
    existing = Subscription.objects.filter(
        player=player, season=season, status__in=["pending", "active"]
    ).first()
    #if existing:
    #    messages.info(
    #        request,
    #        f"This player already has a membership for {season.name}."
    #    )
    #    return redirect("memberships:mine")

    plans = product.plans.filter(active=True)

    # Only skip to confirm when no plan is required and there are no plans
    if (not product.requires_plan) and (not plans.exists()):
        return redirect(f"{reverse('memberships:confirm', args=[player.id, 0])}?product={product.id}")

    if not plans.exists():
        messages.warning(request, "No payment plans available for this product.")
        return redirect("memberships:choose", player_id=player.id)

    context = {
        "player": player,
        "product": product,
        "plans": plans,
        "match_fee": resolve_match_fee_for(product),
    }
    return render(request, "memberships/choose_plan.html", context)


def confirm(request, player_id, plan_id):
    player = get_object_or_404(Player, pk=player_id)
    if not can_manage_player(request.user, player):
        raise Http404()

    if int(plan_id) == 0:
        product_id = request.GET.get("product")
        if not product_id:
            messages.error(request, "Missing product for confirmation.")
            return redirect("memberships:choose", player_id=player.id)
        product = get_object_or_404(
            MembershipProduct.objects.select_related("season", "category"),
            pk=product_id
        )
        plan = None
    else:
        plan = get_object_or_404(
            PaymentPlan.objects.select_related("product", "product__season"),
            pk=plan_id,
            active=True
        )
        product = plan.product

    if not product.season.is_active:
        raise Http404("Not in active season.")

    season = product.season
    existing = Subscription.objects.filter(
        player=player,
        season=season,
        status__in=["pending", "active"],
    ).select_related("product", "plan").first()
    if existing:
        messages.info(
            request,
            f"This player already has a {existing.get_status_display().lower()} membership "
            f"for {season.name} ({existing.product.name})."
        )
        return redirect("memberships:mine")

    if request.method == "POST":
        form = ConfirmSubscriptionForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    sub = Subscription(
                        player=player,
                        product=product,
                        plan=plan,  # may be None
                        status="pending",
                        created_by=request.user if request.user.is_authenticated else None,
                    )
                    sub.full_clean()  # enforces requires_plan and season alignment
                    sub.save()        # season is set in model.save()
            except IntegrityError:
                messages.warning(
                    request,
                    f"A membership already exists for {season.name}. We didn't create a duplicate."
                )
                return redirect("memberships:mine")
            else:
                messages.success(request, "Subscription created.")
                return redirect("memberships:mine")
    else:
        form = ConfirmSubscriptionForm()

    match_fee = resolve_match_fee_for(product) if product.pay_per_match else None

    context = {
        "player": player,
        "product": product,
        "plan": plan,
        "form": form,
        "match_fee": match_fee,
    }
    return render(request, "memberships/confirm.html", context)


def my_memberships(request):
    if not request.user.is_authenticated:
        raise Http404()

    # All players this user can manage (adjust if you have a different ownership rule)
    players = Player.objects.filter(created_by=request.user).order_by("first_name", "last_name")

    # Split active/pending vs everything else
    active_statuses = ["pending", "active"]
    active_subs = (
        Subscription.objects
        .filter(player__created_by=request.user, status__in=active_statuses)
        .select_related("player", "product", "product__season", "plan")
        .order_by("player__last_name", "player__first_name", "-started_at")
    )
    old_subs = (
        Subscription.objects
        .filter(player__created_by=request.user)
        .exclude(status__in=active_statuses)
        .select_related("player", "product", "product__season", "plan")
        .order_by("-started_at")
    )

    return render(request, "memberships/mine.html", {
        "players": players,
        "active_subs": active_subs,
        "old_subs": old_subs,
    })


@require_POST
def subscription_cancel(request, sub_id: int):
    sub = get_object_or_404(
        Subscription.objects.select_related("player", "season", "product"),
        pk=sub_id,
    )
    if not _can_manage_subscription(request.user, sub):
        raise Http404()

    if sub.status in ["cancelled", "paused"]:
        messages.info(request, "This subscription is already not active.")
        return redirect("memberships:mine")

    sub.status = "cancelled"
    # optional: track when cancelled in external_ref notes or add a field later
    sub.save(update_fields=["status"])
    messages.success(
        request,
        f"Subscription for {sub.player} • {sub.product.name} ({sub.season.name}) has been cancelled."
    )
    return redirect("memberships:mine")


def subscription_delete(request, sub_id: int):
    """
    GET -> render a small confirm page.
    POST -> hard delete the record.
    """
    sub = get_object_or_404(
        Subscription.objects.select_related("player", "season", "product"),
        pk=sub_id,
    )
    if not _can_manage_subscription(request.user, sub):
        raise Http404()

    if request.method == "POST":
        # Hard-delete
        sub.delete()
        messages.success(request, "Subscription deleted.")
        return redirect("memberships:mine")

    # Render confirm page
    return render(request, "memberships/subscription_delete_confirm.html", {"sub": sub})