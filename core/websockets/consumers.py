from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
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
        await database_sync_to_async(self._presence().mark_online)(user.pk)

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)
            await database_sync_to_async(self._presence().mark_offline)(
                self.scope["user"].pk
            )

    async def receive_json(self, content, **kwargs):
        """Client -> server: {"type": "chat.typing", "channel_id": "<uuid>"}"""
        if content.get("type") == "chat.typing":
            await self._relay_typing(content.get("channel_id"))

    async def _relay_typing(self, channel_id):
        from core.modules.chat.services.chat import ChatService

        user = self.scope["user"]
        try:
            recipients = await database_sync_to_async(ChatService.typing_recipients)(
                user, channel_id
            )
        except Exception:  # malformed channel id from the client
            return
        payload = {
            "type": "chat.typing",
            "channel_id": str(channel_id),
            "user_id": str(user.pk),
            "name": user.name,
        }
        for user_id in recipients:
            await self.channel_layer.group_send(
                user_group(user_id), {"type": "push", "payload": payload}
            )

    @staticmethod
    def _presence():
        from core.modules.chat import presence

        return presence

    async def push(self, event):
        await self.send_json(event["payload"])
