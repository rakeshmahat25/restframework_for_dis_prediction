from channels.auth import AuthMiddlewareStack
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth.models import AnonymousUser
from asgiref.sync import sync_to_async
from apps.main_app.models import Consultation
from apps.accounts.models import User
import logging

logger = logging.getLogger(__name__)


class JWTAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        try:
            # Token extraction
            token = None
            headers = dict(scope.get("headers", []))

            if b"authorization" in headers:
                auth_header = headers[b"authorization"].decode()
                if auth_header.startswith("Bearer "):
                    token = auth_header.split("Bearer ")[1]

            if not token and "query_string" in scope:
                query_string = scope["query_string"].decode()
                token = next(
                    (
                        p.split("=")[1]
                        for p in query_string.split("&")
                        if p.startswith("token=")
                    ),
                    None,
                )

            # Authentication
            if token:
                access_token = AccessToken(token)
                user = await sync_to_async(User.objects.get)(id=access_token["user_id"])
                scope["user"] = user
                logger.debug(f"Authenticated user {user.id}")
            else:
                scope["user"] = AnonymousUser()
                await self._reject_connection(send, 4001)
                return

            # Consultation validation
            consultation_id = scope["url_route"]["kwargs"]["consultation_id"]
            try:
                consultation = await sync_to_async(Consultation.objects.get)(
                    id=consultation_id
                )
                participants = await sync_to_async(list)(
                    consultation.participants.values_list("id", flat=True)
                )

                logger.info(
                    f"Consultation {consultation_id} check | "
                    f"Status: {consultation.status} | "
                    f"Participants: {participants} | "
                    f"User: {user.id}"
                )

                if consultation.status != "active":
                    logger.warning(f"Rejected inactive consultation {consultation_id}")
                    await self._reject_connection(send, 4003)
                    return

                if user.id not in participants:
                    logger.warning(f"User {user.id} not in participants")
                    await self._reject_connection(send, 4003)
                    return

            except Consultation.DoesNotExist:
                logger.warning(f"Consultation {consultation_id} not found")
                await self._reject_connection(send, 4003)
                return

        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            await self._reject_connection(send, 4001)
            return

        return await self.inner(scope, receive, send)

    async def _reject_connection(self, send, code):
        await send({"type": "websocket.close", "code": code})
