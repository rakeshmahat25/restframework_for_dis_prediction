"""
ASGI config for medpredict project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

# import os
# from django.core.asgi import get_asgi_application
# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "medpredict.settings")
# application = get_asgi_application()

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from apps.chats.middleware import JWTAuthMiddleware
import apps.chats.routing

# Ensure the correct settings module is used
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "medpredict.settings")

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": JWTAuthMiddleware(
            AuthMiddlewareStack(URLRouter(apps.chats.routing.websocket_urlpatterns))
        ),
    }
)
