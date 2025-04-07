from django.db import models, transaction
from django.core.validators import MinLengthValidator
from apps.accounts.models import User
from apps.main_app.models import Consultation, Doctor
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging

logger = logging.getLogger(__name__)


class Chat(models.Model):
    MESSAGE_STATUS_CHOICES = [
        ("sent", "Sent"),
        ("delivered", "Delivered"),
        ("read", "Read"),
    ]

    created = models.DateTimeField(auto_now_add=True, db_index=True)
    consultation = models.ForeignKey(
        Consultation, on_delete=models.CASCADE, related_name="chats"
    )
    sender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="sent_chats"
    )
    message = models.TextField(validators=[MinLengthValidator(10)])
    status = models.CharField(
        max_length=20, choices=MESSAGE_STATUS_CHOICES, default="delivered"
    )
    timestamp = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["consultation", "-created"]),
            models.Index(fields=["sender", "-created"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Chat {self.id} for Consultation {self.consultation.id}"

    @property
    def read(self):
        return self.status == "read"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        transaction.on_commit(self.send_ws_notification)

    def send_ws_notification(self):
        try:
            channel_layer = get_channel_layer()
            group_name = f"consultation_{self.consultation.id}"
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    "type": "chat_message",
                    "message": self.message,
                    "sender": self.sender.email,
                    "timestamp": self.created.isoformat(),
                    "status": self.status,
                },
            )
        except Exception as e:
            logger.error(f"WebSocket notification failed: {str(e)}")


class Feedback(models.Model):
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="feedbacks")
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.CASCADE,
        related_name="feedbacks",
        null=False,
        help_text="Select the doctor being reviewed",
    )
    feedback = models.TextField(validators=[MinLengthValidator(10)])

    class Meta:
        ordering = ["-created"]
        constraints = [
            models.UniqueConstraint(
                fields=["sender", "doctor"], name="unique_feedback_per_doctor"
            )
        ]

    def __str__(self):
        return f"Feedback #{self.id} for Dr. {self.doctor.name}"
