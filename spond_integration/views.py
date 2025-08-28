# spond/views.py
from django.contrib.auth.decorators import permission_required
from django.db.models import Q
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_GET, require_POST

from .models import SpondMember, PlayerSpondLink
from members.models import Player

PERM = "spond_integration.access_spond_app"

@require_GET
def can_access(request):
    return JsonResponse({"has_access": request.user.has_perm(PERM)})

@require_GET
@permission_required(PERM, raise_exception=True)
def search_members(request):
    q = (request.GET.get("q") or "").strip()
    qs = SpondMember.objects.all()
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(email__icontains=q))
    results = [
        {
            "id": m.id,
            "spond_member_id": m.spond_member_id,
            "name": m.full_name,
            "email": m.email,
        }
        for m in qs.order_by("full_name")[:25]
    ]
    return JsonResponse({"results": results})

@require_POST
@permission_required(PERM, raise_exception=True)
def link_player(request, player_id: int):
    try:
        player = Player.objects.get(pk=player_id)
    except Player.DoesNotExist:
        return HttpResponseBadRequest("Invalid player")

    try:
        spond_pk = int(request.POST.get("spond_member_pk"))
        sm = SpondMember.objects.get(pk=spond_pk)
    except Exception:
        return HttpResponseBadRequest("Invalid Spond member")

    link, _ = PlayerSpondLink.objects.update_or_create(
        player=player, spond_member=sm, defaults={"linked_by": request.user, "active": True}
    )
    return JsonResponse({"ok": True, "link_id": link.id})

@require_POST
@permission_required(PERM, raise_exception=True)
def unlink_player(request, player_id: int, link_id: int):
    try:
        link = PlayerSpondLink.objects.get(pk=link_id, player_id=player_id)
    except PlayerSpondLink.DoesNotExist:
        return HttpResponseBadRequest("Invalid link")
    link.active = False
    link.save(update_fields=["active"])
    return JsonResponse({"ok": True})
