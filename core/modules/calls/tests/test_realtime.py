from asgiref.sync import sync_to_async
from channels.routing import URLRouter
from channels.sessions import CookieMiddleware
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.test import TransactionTestCase

from core.models.user import User
from core.modules.calls.models.call import Call
from core.modules.calls.services.calls import CallService
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


class CallSignalingTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.ana = User.objects.create_user("ana@a.com", PASSWORD, name="Ana")
        self.bob = User.objects.create_user("bob@a.com", PASSWORD, name="Bob")
        org = OrganizationService.create(self.ana, name="Acme")
        OrganizationMember.objects.create(organization=org, user=self.bob)
        channel = ChatService.open_direct(self.ana, org.id, self.bob.id)["id"]
        self.call = CallService.start(self.ana, channel, "video")
        CallService.join(self.bob, self.call.id)

    def socket(self, email):
        self.client.post("/api/v1/login/", {"email": email, "password": PASSWORD})
        cookie = self.client.cookies[get_auth_cookie_name()].value
        return WebsocketCommunicator(
            application,
            "/ws/",
            headers=[(b"cookie", f"{get_auth_cookie_name()}={cookie}".encode())],
        )

    async def test_signal_is_relayed_and_closing_the_socket_hangs_up(self):
        ana = await sync_to_async(self.socket)("ana@a.com")
        bob = await sync_to_async(self.socket)("bob@a.com")
        self.assertTrue((await ana.connect())[0])
        self.assertTrue((await bob.connect())[0])

        await ana.send_json_to(
            {
                "type": "call.signal",
                "call_id": str(self.call.id),
                "to_user_id": str(self.bob.id),
                "data": {"sdp": {"type": "offer", "sdp": "v=0"}},
            }
        )
        event = await bob.receive_json_from(timeout=5)
        self.assertEqual(event["type"], "call.signal")
        self.assertEqual(event["from_user_id"], str(self.ana.id))

        # a bad target answers with call.error instead of closing the socket
        await ana.send_json_to(
            {"type": "call.signal", "call_id": str(self.call.id), "to_user_id": "x"}
        )
        self.assertEqual((await ana.receive_json_from(timeout=5))["type"], "call.error")

        await bob.disconnect()
        status = await sync_to_async(lambda: Call.objects.get(pk=self.call.pk).status)()
        self.assertEqual(status, "ended")
        await ana.disconnect()
