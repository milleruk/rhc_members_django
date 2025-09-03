# accounts/adapter.py
from allauth.account.adapter import DefaultAccountAdapter


class RHCAccountAdapter(DefaultAccountAdapter):
    """
    Custom adapter to activate accounts once the email is confirmed.
    """

    def confirm_email(self, request, email_address):
        """
        Called by Allauth when a confirmation link is used.
        Make the user active after their email is verified.
        """
        # Let allauth mark the email as verified / set primary if needed
        resp = super().confirm_email(request, email_address)

        user = email_address.user
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])
        return resp
