from allauth.account.signals import email_changed, email_confirmed
from django.dispatch import receiver


def _activate_on_email_confirm(request, email_address, **kwargs):
    user = email_address.user
    if not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])


@receiver(email_confirmed)
def activate_user_on_confirm(request, email_address, **kwargs):
    user = email_address.user
    if not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])


def _maybe_sync_username(user):
    # keep username in lockstep with current primary email
    primary = getattr(user, "email", None)
    if primary and user.username != primary:
        user.username = primary.lower().strip()
        user.save(update_fields=["username"])


@receiver(email_confirmed)
def on_email_confirmed(request, email_address, **kwargs):
    # If user makes a new email primary after confirming, allauth may also emit email_changed.
    # This ensures username sync even if only confirmation occurs.
    if email_address.user and email_address.user.email == email_address.email:
        _maybe_sync_username(email_address.user)


try:
    # Newer allauth versions
    @receiver(email_changed)
    def on_email_changed(request, user, from_email_address, to_email_address, **kwargs):
        _maybe_sync_username(user)

except Exception:
    pass
