# memberships/views.py
from __future__ import annotations

from typing import Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import BooleanField, Exists, OuterRef, Q, Value
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.timezone import localdate
from django.views.decorators.http import require_POST

from members.models import Player
from tasks.events import emit

from .forms import ConfirmSubscriptionForm
from .models import MembershipProduct, PaymentPlan, Season, Subscription, resolve_match_fee_for
from .permissions import can_manage_player

# ---------------------------
# Helpers / guards
# ---------------------------


def _get_selectable_season(today=None) -> Season:
    """
    Return the season that should be selectable:
      - If today falls within [start, end] for any season, return that one.
      - Otherwise, return the earliest future season (by start).
      - If none found, raise 404.
    """
    d = today or localdate()

    current = Season.objects.filter(start__lte=d, end__gte=d).order_by("start", "id").first()
    if current:
        return current

    upcoming = Season.objects.filter(start__gt=d).order_by("start", "id").first()
    if upcoming:
        return upcoming

    raise Http404("No selectable season is available.")


def _is_admin(user) -> bool:
    """True if user is superuser or in elevated groups."""
    if not user.is_authenticated:
        return False
    return (
        user.is_superuser
        or user.groups.filter(name__in=["Coach", "Captain", "Club Admin"]).exists()
    )


def _can_manage_subscription(user, sub: Subscription) -> bool:
    """
    Owning creator can manage; elevated roles can manage any.
    NOTE: additional ACTIVE protection is enforced in the cancel/delete views.
    """
    if not user.is_authenticated:
        return False
    if sub.player and getattr(sub.player, "created_by_id", None) == user.id:
        return True
    return _is_admin(user)


def _existing_membership(player: Player, season: Season) -> Optional[Subscription]:
    return (
        Subscription.objects.filter(player=player, season=season, status__in=["pending", "active"])
        .select_related("product", "plan")
        .first()
    )


# ---------------------------
# Choose product / plan / confirm
# ---------------------------


@login_required
def choose_product(request: HttpRequest, player_id: int) -> HttpResponse:
    player = get_object_or_404(Player, pk=player_id)
    if not can_manage_player(request.user, player):
        raise Http404()

    # Use selectable season (current by date, else earliest upcoming)
    season = _get_selectable_season()
    existing = _existing_membership(player, season)

    products_qs = (
        MembershipProduct.objects.filter(season=season, active=True)
        .select_related("category", "season")
        .prefetch_related("plans")
        .filter(
            Q(category__isnull=True)
            | Q(category__applies_to__isnull=True)
            | Q(category__applies_to=player.player_type)
        )
        .distinct()
        .order_by("category__label", "name", "id")
    )

    products = list(products_qs)
    for p in products:
        p.match_fee = resolve_match_fee_for(p)

    return render(
        request,
        "memberships/choose_product.html",
        {
            "player": player,
            "season": season,
            "products": products,
            "has_active": existing is not None,
            "existing_sub": existing,
        },
    )


@login_required
def choose_plan(request: HttpRequest, player_id: int, product_id: int) -> HttpResponse:
    player = get_object_or_404(Player, pk=player_id)
    if not can_manage_player(request.user, player):
        raise Http404()

    product = get_object_or_404(
        MembershipProduct.objects.select_related("season", "category"),
        pk=product_id,
        active=True,
    )

    # Only allow plan selection if the product is in the selectable season
    # Ensure product is in the single selectable season BEFORE any other logic
    selectable = _get_selectable_season()
    if product.season_id != selectable.id:
        raise Http404("Product is not currently selectable.")

    season = product.season
    existing = _existing_membership(player, season)

    plans = product.plans.filter(active=True).order_by("display_order", "label", "id")

    if (not product.requires_plan) and (not plans.exists()):
        confirm_url = f"{reverse('memberships:confirm', args=[player.id, 0])}?product={product.id}"
        return redirect(confirm_url)

    if not plans.exists():
        messages.warning(request, "No payment plans are available for this product.")
        return redirect("memberships:choose", player_id=player.id)

    return render(
        request,
        "memberships/choose_plan.html",
        {
            "player": player,
            "product": product,
            "plans": plans,
            "match_fee": resolve_match_fee_for(product),
            "existing_sub": existing,
        },
    )


@login_required
def confirm(request: HttpRequest, player_id: int, plan_id: int) -> HttpResponse:
    """
    Confirm and create a pending subscription for the selected product/plan.
    """
    player = get_object_or_404(Player, pk=player_id)
    if not can_manage_player(request.user, player):
        raise Http404()

    # Resolve product + optional plan
    if int(plan_id) == 0:
        product_id = request.GET.get("product")
        if not product_id:
            messages.error(request, "Missing product for confirmation.")
            return redirect("memberships:choose", player_id=player.id)
        product = get_object_or_404(
            MembershipProduct.objects.select_related("season", "category"),
            pk=product_id,
        )
        plan = None
    else:
        plan = get_object_or_404(
            PaymentPlan.objects.select_related("product", "product__season"),
            pk=plan_id,
            active=True,
        )
        product = plan.product

    # Only allow confirmation if product is in the selectable season
    selectable = _get_selectable_season()
    if product.season_id != selectable.id:
        raise Http404("This product is not in the currently selectable season.")

    season = product.season
    existing = _existing_membership(player, season)
    if existing:
        messages.info(
            request,
            f"This player already has a {existing.get_status_display().lower()} membership "
            f"for {season.name} ({existing.product.name}).",
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
                    sub.full_clean()  # validates requires_plan + season alignment
                    sub.save()  # model.save() sets season from product

                    # Emit event after commit only
                    transaction.on_commit(
                        lambda: emit("membership.confirmed", subject=player, actor=request.user)
                    )

            except IntegrityError:
                messages.warning(
                    request,
                    f"A membership already exists for {season.name}. We didn't create a duplicate.",
                )
                return redirect("memberships:mine")
            else:
                messages.success(request, "Subscription created.")
                return redirect("memberships:mine")
    else:
        form = ConfirmSubscriptionForm()

    match_fee = resolve_match_fee_for(product) if getattr(product, "pay_per_match", False) else None

    context = {
        "player": player,
        "product": product,
        "plan": plan,
        "form": form,
        "match_fee": match_fee,
    }
    return render(request, "memberships/confirm.html", context)


# ---------------------------
# My memberships
# ---------------------------


@login_required
def my_memberships(request: HttpRequest) -> HttpResponse:
    """
    List all players managed by the current user and their subscriptions,
    split into active/pending and historical. Hide "Choose membership"
    for players who already have any sub in the current selectable season.
    """
    # Use selectable season
    try:
        current_season = _get_selectable_season()
    except Http404:
        current_season = None

    players_qs = Player.objects.filter(created_by=request.user).order_by("first_name", "last_name")

    if current_season:
        players = players_qs.annotate(
            has_sub_this_season=Exists(
                Subscription.objects.filter(
                    player=OuterRef("pk"),
                    season=current_season,
                )
            )
        )
    else:
        players = players_qs.annotate(has_sub_this_season=Value(False, output_field=BooleanField()))
    active_statuses = ["pending", "active"]

    active_subs = (
        Subscription.objects.filter(player__created_by=request.user, status__in=active_statuses)
        .select_related("player", "product", "product__season", "plan", "season")
        .order_by("player__last_name", "player__first_name", "-started_at")
    )

    old_subs = (
        Subscription.objects.filter(player__created_by=request.user)
        .exclude(status__in=active_statuses)
        .select_related("player", "product", "product__season", "plan", "season")
        .order_by("-started_at")
    )

    return render(
        request,
        "memberships/mine.html",
        {
            "players": players,
            "active_subs": active_subs,
            "old_subs": old_subs,
            "current_season": current_season,
        },
    )


# ---------------------------
# Cancel / delete (state changes)
# ---------------------------


@login_required
@require_POST
def subscription_cancel(request: HttpRequest, sub_id: int) -> HttpResponse:
    """
    Cancel a subscription. Non-admins are blocked from cancelling ACTIVE subscriptions.
    """
    sub = get_object_or_404(
        Subscription.objects.select_related("player", "season", "product"),
        pk=sub_id,
    )
    if not _can_manage_subscription(request.user, sub):
        raise Http404()

    # Server-side safety: creators can cancel pending, but only admins can cancel ACTIVE.
    if sub.status == "active" and not _is_admin(request.user):
        messages.error(request, "Active subscriptions can only be cancelled by a club admin.")
        return redirect("memberships:mine")

    if sub.status in ["cancelled", "paused"]:
        messages.info(request, "This subscription is already not active.")
        return redirect("memberships:mine")

    sub.status = "cancelled"
    sub.save(update_fields=["status"])
    messages.success(
        request,
        f"Subscription for {sub.player} • {sub.product.name} ({sub.season.name}) has been cancelled.",
    )
    return redirect("memberships:mine")


@login_required
def subscription_delete(request: HttpRequest, sub_id: int) -> HttpResponse:
    """
    GET -> render a small confirm page.
    POST -> hard delete the record.
    Non-admins may not delete ACTIVE subscriptions.
    """
    sub = get_object_or_404(
        Subscription.objects.select_related("player", "season", "product"),
        pk=sub_id,
    )
    if not _can_manage_subscription(request.user, sub):
        raise Http404()

    if request.method == "POST":
        if sub.status == "active" and not _is_admin(request.user):
            messages.error(request, "Active subscriptions can only be deleted by a club admin.")
            return redirect("memberships:mine")

        sub.delete()
        messages.success(request, "Subscription deleted.")
        return redirect("memberships:mine")

    return render(request, "memberships/subscription_delete_confirm.html", {"sub": sub})
