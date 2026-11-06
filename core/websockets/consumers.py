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
            await database_sync_to_async(self._went_offline)(self.scope["user"])

    async def receive_json(self, content, **kwargs):
        """Client -> server:
        {"type": "chat.typing", "channel_id": "<uuid>"}
        {"type": "call.signal", "call_id", "to_user_id", "data": {"sdp"|"candidate"}}
        """
        if content.get("type") == "chat.typing":
            await self._relay_typing(content.get("channel_id"))
        elif content.get("type") == "call.signal":
            await self._relay_signal(content)

    async def _relay_signal(self, content):
        from rest_framework.exceptions import APIException

        from core.modules.calls.services.calls import CallService

        try:
            await database_sync_to_async(CallService.signal)(
                self.scope["user"],
                content.get("call_id"),
                content.get("to_user_id"),
                content.get("data"),
            )
        except APIException as error:
            await self.send_json(
                {
                    "type": "call.error",
                    "call_id": str(content.get("call_id", "")),
                    "detail": str(error.detail),
                }
            )

    def _went_offline(self, user):
        from core.modules.calls.services.calls import CallService

        presence = self._presence()
        presence.mark_offline(user.pk)
        if not presence.is_online(user.pk):  # last tab closed: hang up its calls
            CallService.leave_all(user)

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
