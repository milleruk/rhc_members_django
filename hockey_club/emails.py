# hockey_club/emails.py
from allauth.account.models import EmailAddress, EmailConfirmationHMAC

def send_activation_email(request, user):
    if not user.email:
        return
    email_address, _ = EmailAddress.objects.get_or_create(
        user=user, email=user.email, defaults={"primary": True}
    )
    if email_address.verified:
        return
    EmailConfirmationHMAC(email_address).send(request, signup=True)
