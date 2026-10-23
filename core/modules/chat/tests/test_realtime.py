from asgiref.sync import sync_to_async
from channels.routing import URLRouter
from channels.sessions import CookieMiddleware
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.test import TransactionTestCase

from core.models.user import User
from core.modules.chat import presence
from core.modules.chat.services.chat import ChatService
from core.modules.organizations.models.organization import OrganizationMember
from core.modules.organizations.services.organization import OrganizationService
from core.utils.cookies import get_auth_cookie_name
from core.websockets.auth import JWTCookieAuthMiddleware
from core.websockets.routing import websocket_urlpatterns

application = CookieMiddleware(
    JWTCookieAuthMiddleware(URLRouter(websocket_urlpatterns))
)
PASSWORD = "S3cure-pass!"


class ChatRealtimeTests(TransactionTestCase):
    """A message posted over HTTP arrives on the other member's open socket."""

    def setUp(self):
        cache.clear()  # the login throttle (10/min) is shared by every test
        self.ana = User.objects.create_user("ana@a.com", PASSWORD, name="Ana")
        self.bob = User.objects.create_user("bob@a.com", PASSWORD, name="Bob")
        self.org = OrganizationService.create(self.ana, name="Acme")
        OrganizationMember.objects.create(organization=self.org, user=self.bob)
        self.general = next(
            c
            for c in ChatService.list_channels(self.ana, self.org.id)
            if c["kind"] == "organization"
        )["id"]

    def login(self, email):
        self.client.post("/api/v1/login/", {"email": email, "password": PASSWORD})
        return self.client.cookies[get_auth_cookie_name()].value

    async def test_message_is_pushed_to_connected_members(self):
        bob_cookie = await sync_to_async(self.login)("bob@a.com")
        ws = WebsocketCommunicator(
            application,
            "/ws/",
            headers=[(b"cookie", f"{get_auth_cookie_name()}={bob_cookie}".encode())],
        )
        connected, _ = await ws.connect()
        self.assertTrue(connected)

        await sync_to_async(ChatService.send)(self.ana, self.general, "hello bob")

        event = await ws.receive_json_from(timeout=5)
        self.assertEqual(event["type"], "chat.message")
        self.assertEqual(event["message"]["content"], "hello bob")
        self.assertEqual(event["message"]["author_name"], "Ana")
        await ws.disconnect()


class ChatTypingAndPresenceTests(TransactionTestCase):
    def setUp(self):
        cache.clear()  # the login throttle (10/min) is shared by every test
        self.ana = User.objects.create_user("ana@a.com", PASSWORD, name="Ana")
        self.bob = User.objects.create_user("bob@a.com", PASSWORD, name="Bob")
        self.carol = User.objects.create_user("carol@a.com", PASSWORD, name="Carol")
        self.org = OrganizationService.create(self.ana, name="Acme")
        for user in (self.bob, self.carol):
            OrganizationMember.objects.create(organization=self.org, user=user)
        self.direct = str(
            ChatService.open_direct(self.ana, self.org.id, self.bob.id)["id"]
        )

    def login(self, email):
        self.client.post("/api/v1/login/", {"email": email, "password": PASSWORD})
        return self.client.cookies[get_auth_cookie_name()].value

    async def connect(self, email):
        cookie = await sync_to_async(self.login)(email)
        ws = WebsocketCommunicator(
            application,
            "/ws/",
            headers=[(b"cookie", f"{get_auth_cookie_name()}={cookie}".encode())],
        )
        connected, _ = await ws.connect()
        self.assertTrue(connected)
        return ws

    async def test_typing_reaches_only_the_other_participant(self):
        ana_ws = await self.connect("ana@a.com")
        bob_ws = await self.connect("bob@a.com")
        carol_ws = await self.connect("carol@a.com")
        await ana_ws.send_json_to({"type": "chat.typing", "channel_id": self.direct})

        event = await bob_ws.receive_json_from(timeout=5)
        self.assertEqual(event["type"], "chat.typing")
        self.assertEqual((event["user_id"], event["name"]), (str(self.ana.id), "Ana"))
        self.assertTrue(await carol_ws.receive_nothing(timeout=0.5))  # not in the chat
        self.assertTrue(await ana_ws.receive_nothing(timeout=0.5))  # not echoed back
        for ws in (ana_ws, bob_ws, carol_ws):
            await ws.disconnect()

    async def test_malformed_or_foreign_typing_is_ignored(self):
        ana_ws = await self.connect("ana@a.com")
        carol_ws = await self.connect("carol@a.com")
        await carol_ws.send_json_to({"type": "chat.typing", "channel_id": self.direct})
        await carol_ws.send_json_to({"type": "chat.typing", "channel_id": "nope"})
        await carol_ws.send_json_to({"type": "unknown"})
        self.assertTrue(await ana_ws.receive_nothing(timeout=0.5))
        await ana_ws.disconnect()
        await carol_ws.disconnect()

    async def test_presence_follows_the_socket(self):
        self.assertFalse(await sync_to_async(presence.is_online)(self.bob.id))
        ws = await self.connect("bob@a.com")
        self.assertTrue(await sync_to_async(presence.is_online)(self.bob.id))
        await ws.disconnect()
        self.assertFalse(await sync_to_async(presence.is_online)(self.bob.id))
