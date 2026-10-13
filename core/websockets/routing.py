from django.urls import path

from core.websockets.consumers import UserConsumer

websocket_urlpatterns = [
    path("ws/", UserConsumer.as_asgi()),
]
