import json
import uuid
import logging
import traceback
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.db import transaction
from apps.main_app.models import Consultation
from .models import Chat

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.consultation_id = None
        self.group_name = None

    async def connect(self):
        # Authentication check
        if not self.scope["user"].is_authenticated:
            await self.close()
            return

        try:
            # Validate consultation ID format
            self.consultation_id = uuid.UUID(
                self.scope["url_route"]["kwargs"]["consultation_id"]
            )

            # Verify active consultation with participant
            consultation = await self.get_valid_consultation()

            # Setup group
            self.group_name = f"consultation_{self.consultation_id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()

        except (ValueError, Consultation.DoesNotExist) as e:
            logger.warning(f"Connection rejected: {str(e)}")
            await self.close(code=4001)
        except Exception as e:
            logger.error(f"Connection error: {traceback.format_exc()}")
            await self.close(code=4001)

    @database_sync_to_async
    def get_valid_consultation(self):
        """Atomic consultation validation"""
        return Consultation.objects.get(
            id=self.consultation_id, participants=self.scope["user"], status="active"
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            if data.get("type") == "end_chat":
                await self.handle_chat_end()
            else:
                await self.handle_chat_message(data)
        except Exception as e:
            logger.error(f"Message receive error: {traceback.format_exc()}")
            await self.send_error("Invalid message format")

    async def handle_chat_end(self):
        try:
            async with transaction.atomic():
                consultation = await database_sync_to_async(
                    Consultation.objects.select_for_update().get
                )(id=self.consultation_id)

                if consultation.status == "active":
                    await database_sync_to_async(consultation.complete)()
                    await self.broadcast_system_message(
                        "Consultation ended by participant", "completed"
                    )
        except Exception as e:
            logger.error(f"End consultation failed: {traceback.format_exc()}")
            await self.send_error("Failed to end consultation")

    async def handle_chat_message(self, data):
        """Handle message from WebSocket (for real-time only)"""
        try:
            # Broadcast message without saving to DB
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "chat_message",
                    "message": data.get("message"),
                    "sender": self.scope["user"].email,
                    "timestamp": timezone.now().isoformat(),
                    "status": "delivered",
                    "system": False,
                },
            )
        except Exception as e:
            logger.error(f"Message handling failed: {traceback.format_exc()}")
            await self.send_error("Message processing failed")

    async def chat_message(self, event):
        """Send message to WebSocket client"""
        await self.send(text_data=json.dumps(event))

    async def broadcast_system_message(self, message, status):
        """Send system notifications"""
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat_message",
                "message": message,
                "sender": "system",
                "timestamp": timezone.now().isoformat(),
                "status": status,
                "system": True,
            },
        )

    async def send_error(self, message):
        await self.send(
            text_data=json.dumps(
                {"error": message, "timestamp": timezone.now().isoformat()}
            )
        )
