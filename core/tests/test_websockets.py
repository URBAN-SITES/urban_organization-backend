from asgiref.sync import sync_to_async
from channels.routing import URLRouter
from channels.sessions import CookieMiddleware
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase

from core.models.user import User
from core.utils.cookies import get_auth_cookie_name
from core.websockets.auth import JWTCookieAuthMiddleware
from core.websockets.consumers import send_to_user
from core.websockets.routing import websocket_urlpatterns

application = CookieMiddleware(
    JWTCookieAuthMiddleware(URLRouter(websocket_urlpatterns))
)


class UserConsumerTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user("a@a.com", "S3cure-pass!", name="A")
        self.client.post(
            "/api/v1/login/", {"email": "a@a.com", "password": "S3cure-pass!"}
        )
        self.access = self.client.cookies[get_auth_cookie_name()].value

    def communicator(self, cookie=""):
        return WebsocketCommunicator(
            application, "/ws/", headers=[(b"cookie", cookie.encode())]
        )

    async def test_anonymous_is_rejected(self):
        connected, code = await self.communicator().connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4401)

    async def test_logged_user_receives_pushes(self):
        ws = self.communicator(f"{get_auth_cookie_name()}={self.access}")
        connected, _ = await ws.connect()
        self.assertTrue(connected)

        await sync_to_async(send_to_user)(self.user.pk, {"title": "hi"})
        self.assertEqual(await ws.receive_json_from(), {"title": "hi"})
        await ws.disconnect()
