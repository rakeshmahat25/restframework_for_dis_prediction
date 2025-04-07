from django.core.mail import send_mail
import logging

logger = logging.getLogger(__name__)


class DjangoMail:
    def __init__(self):
        self.from_email = "rootking098@gmail.com"
        self.fail_silently = False

    def send(self, dct):
        subject = dct["subject"]
        message = dct["message"]
        to_emails = dct["to"]
        try:
            send_mail(
                subject,
                message,
                self.from_email,
                to_emails,
                fail_silently=self.fail_silently,
            )
            logger.info(f"Email sent to {to_emails}: {subject}")
        except Exception as e:
            logger.error(f"Failed to send email to {to_emails}: {e}")

    def send_otp(self, email, otp):
        subject = "Your OTP for Account Verification"
        message = f"Your OTP is {otp}. Please use it to verify your account."
        self.send({"subject": subject, "message": message, "to": [email]})
