from django.urls import re_path
from .consumers import ChatConsumer

websocket_urlpatterns = [
    re_path(r"ws/chat/(?P<consultation_id>[0-9a-f-]{36})/$", ChatConsumer.as_asgi()),
]
