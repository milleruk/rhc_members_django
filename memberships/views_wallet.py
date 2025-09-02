# TODO: Apple Wallet integration
# When ready:
#  1. Enable WALLET_APPLE_ENABLED = True in settings.py
#  2. Add Pass Type ID certificate + key files
#  3. Switch apple_wallet_pkpass to build a real signed pass

# memberships/views_wallet.py
import io, json, zipfile
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseRedirect, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django_walletpass.models import PassBuilder
from members.models import Player  # adjust to your app

def _pass_payload(player):
    name = f"{player.first_name} {player.last_name}".strip()
    if not name:
        name = "Unknown Player"

    return {
        "formatVersion": 1,
        "description": "RHC Membership Card",
        "organizationName": "Redditch Hockey Club",
        "serialNumber": str(player.public_id),
        "passTypeIdentifier": settings.WALLETPASS.get("PASS_TYPE_ID", "pass.uk.example.pending"),
        "teamIdentifier": settings.WALLETPASS.get("TEAM_ID", "TEAMIDPENDING"),
        "generic": {
            "primaryFields": [
                {"key": "name", "label": "Member", "value": name}
            ],
            "auxiliaryFields": [
                {"key": "member_no", "label": "Number", "value": f"RHC{player.membership_number}"}
            ],
            "backFields": [
                {"key": "pid", "label": "Player ID", "value": str(player.public_id)}
            ],
        },
        "barcode": {
            "message": f"RHC:{player.public_id}",
            "format": "PKBarcodeFormatQR",
            "messageEncoding": "iso-8859-1",
        },
    }


@login_required
def apple_wallet_preview(request, public_id):
    player = get_object_or_404(Player, public_id=public_id, user=request.user)
    payload = _pass_payload(player)
    # Simple HTML preview so you can sanity-check fields/colors before certs exist
    return render(request, "wallet/apple_preview.html", {
        "player": player,
        "payload": json.dumps(payload, indent=2),
    })

@login_required
def apple_wallet_pkpass(request, public_id):
    # NOTE: Player has no 'user' field — use public_id only, then authorize.
    player = get_object_or_404(Player, public_id=public_id)

    # Optional authorization: allow creator or staff. Adjust to your policy.
    if getattr(player, "created_by_id", None) and player.created_by_id != request.user.id and not request.user.is_staff:
        return HttpResponseForbidden("Not allowed")

    if not getattr(settings, "WALLET_APPLE_ENABLED", False):
        # Return a dummy .pkpass zip for testing the download flow
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("pass.json", json.dumps({"disabled": True, "payload": _pass_payload(player)}, ensure_ascii=False))
        resp = HttpResponse(buf.getvalue(), content_type="application/vnd.apple.pkpass")
        resp["Content-Disposition"] = f'attachment; filename="RHC-{player.membership_number}-TEST.pkpass"'
        return resp


    # When enabled, build the real signed pass here…
    raise NotImplementedError("Apple Wallet enabled but signer not wired yet")
