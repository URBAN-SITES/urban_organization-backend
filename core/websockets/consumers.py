from asgiref.sync import async_to_sync
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.layers import get_channel_layer


def user_group(user_id) -> str:
    return f"user_{user_id}"


def send_to_user(user_id, payload: dict) -> None:
    """Push a JSON message to every open socket of a user, from sync code (views, tasks)."""
    async_to_sync(get_channel_layer().group_send)(
        user_group(user_id), {"type": "push", "payload": payload}
    )


class UserConsumer(AsyncJsonWebsocketConsumer):
    """ws://<host>/ws/ — one channel per logged user. Extend receive_json for chat-like flows."""

    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close(code=4401)
            return
        self.group = user_group(user.pk)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def push(self, event):
        await self.send_json(event["payload"])
