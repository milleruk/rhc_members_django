# hockey_app/emails.py
from django.contrib.auth.tokens import default_token_generator
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from django.core.mail import EmailMultiAlternatives
from django.urls import reverse


def send_activation_email(request, user):
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    url = request.build_absolute_uri(
        reverse("activate_account", args=[uidb64, token])
    )

    ctx = {"user": user, "activation_url": url}
    subject = "Confirm your email"
    text_body = render_to_string("email/activation_email.txt", ctx)
    html_body = render_to_string("email/activation_email.html", ctx)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email="Redditch Hockey Club <noreply@redditchhc.co.uk>",  # or settings.DEFAULT_FROM_EMAIL
        to=[user.email],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send()
