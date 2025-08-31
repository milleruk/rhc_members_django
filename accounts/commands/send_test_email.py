from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings


class Command(BaseCommand):
    help = "Send a test email to verify SMTP configuration"

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            type=str,
            help="Recipient email address (default = EMAIL_HOST_USER)",
        )

    def handle(self, *args, **options):
        recipient = options["to"] or settings.EMAIL_HOST_USER

        subject = "SMTP Test Email"
        message = "This is a test email from the Redditch HC portal."
        sender = settings.DEFAULT_FROM_EMAIL
        recipients = [recipient]

        try:
            send_mail(subject, message, sender, recipients)
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Test email sent to {recipient} (from {sender})"
                )
            )
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"❌ Failed to send email: {e}"))
