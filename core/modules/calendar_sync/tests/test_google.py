from datetime import timedelta
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import requests
from django.core import signing
from django.db import connection
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models.user import User
from core.modules.calendar_sync.models.calendar import UserIntegration
from core.modules.calendar_sync.services.google import GoogleCalendarService
from core.modules.chat.models.chat import ChatMessage
from core.modules.chat.services.chat import ChatService
from core.modules.organizations.services.organization import OrganizationService

POST = "core.modules.calendar_sync.services.google.requests.post"
ENV = {
    "GOOGLE_CLIENT_ID": "client-id",
    "GOOGLE_CLIENT_SECRET": "secret",
    "GOOGLE_OAUTH_REDIRECT_URI": "http://front/callback",
}
API = "/api/v1/"


def reply(status=200, data=None):
    response = MagicMock(status_code=status, ok=status < 400)
    response.json.return_value = data or {}
    return response


def google_env():
    return patch.dict("os.environ", ENV)


class GoogleServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a@a.com", "x12345678!", name="Ana")
        self.other = User.objects.create_user("b@a.com", "x12345678!", name="Bob")

    def connect(self, **token):
        state = signing.dumps({"user": str(self.user.pk)}, salt="google-oauth")
        data = {
            "access_token": "AT",
            "refresh_token": "RT",
            "expires_in": 3600,
            **token,
        }
        with google_env(), patch(POST, return_value=reply(200, data)):
            return GoogleCalendarService.connect(self.user, "code", state)

    def test_authorize_url_carries_scope_offline_access_and_signed_state(self):
        with google_env():
            url = GoogleCalendarService.authorize_url(self.user)
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["client_id"], ["client-id"])
        self.assertEqual(query["access_type"], ["offline"])
        self.assertIn("calendar.events", query["scope"][0])
        data = signing.loads(query["state"][0], salt="google-oauth")
        self.assertEqual(data["user"], str(self.user.pk))

    def test_not_configured_is_a_503(self):
        client = APIClient()
        client.force_authenticate(self.user)
        with patch.dict(
            "os.environ", {"GOOGLE_CLIENT_ID": "", "GOOGLE_CLIENT_SECRET": ""}
        ):
            self.assertEqual(
                client.get(f"{API}integrations/google/authorize/").status_code, 503
            )

    def test_connect_stores_tokens_encrypted_at_rest(self):
        integration = self.connect()
        self.assertEqual(
            (integration.access_token, integration.refresh_token), ("AT", "RT")
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT access_token, refresh_token FROM core_userintegration"
            )
            raw = cursor.fetchone()
        self.assertNotIn("AT", raw[0])
        self.assertNotIn("RT", raw[1])

    def test_reconnecting_keeps_the_refresh_token_google_omits(self):
        self.connect()
        again = self.connect(refresh_token="")
        self.assertEqual(again.refresh_token, "RT")
        self.assertEqual(UserIntegration.objects.count(), 1)

    def test_state_must_be_valid_and_belong_to_the_caller(self):
        foreign = signing.dumps({"user": str(self.other.pk)}, salt="google-oauth")
        with google_env(), patch(POST) as post:
            for state in (foreign, "garbage"):
                with self.assertRaises(Exception) as caught:
                    GoogleCalendarService.connect(self.user, "code", state)
                self.assertEqual(caught.exception.status_code, 400)
            post.assert_not_called()

    def test_google_rejecting_the_code_is_a_400(self):
        state = signing.dumps({"user": str(self.user.pk)}, salt="google-oauth")
        with google_env(), patch(POST, return_value=reply(400)):
            with self.assertRaises(Exception) as caught:
                GoogleCalendarService.connect(self.user, "bad", state)
        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(UserIntegration.objects.count(), 0)

    def test_create_meet_returns_the_link(self):
        self.connect()
        with (
            google_env(),
            patch(
                POST, return_value=reply(200, {"hangoutLink": "https://meet/x"})
            ) as post,
        ):
            link = GoogleCalendarService.create_meet(self.user, "Sprint")
        self.assertEqual(link, "https://meet/x")
        call = post.call_args
        self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer AT")
        self.assertEqual(call.kwargs["json"]["summary"], "Sprint")
        self.assertEqual(call.kwargs["params"], {"conferenceDataVersion": 1})

    def test_expired_token_is_refreshed_first(self):
        self.connect()
        UserIntegration.objects.update(expires_at=timezone.now() - timedelta(minutes=5))
        responses = [
            reply(200, {"access_token": "NEW", "expires_in": 3600}),
            reply(200, {"hangoutLink": "https://meet/y"}),
        ]
        with google_env(), patch(POST, side_effect=responses) as post:
            link = GoogleCalendarService.create_meet(self.user, "Daily")
        self.assertEqual(link, "https://meet/y")
        self.assertEqual(
            post.call_args_list[0].kwargs["data"]["grant_type"], "refresh_token"
        )
        self.assertEqual(
            post.call_args_list[1].kwargs["headers"]["Authorization"], "Bearer NEW"
        )
        self.assertEqual(UserIntegration.objects.get().access_token, "NEW")

    def test_revoked_access_disconnects_the_account(self):
        self.connect()
        with google_env(), patch(POST, return_value=reply(401)):
            with self.assertRaises(Exception) as caught:
                GoogleCalendarService.create_meet(self.user, "x")
        self.assertEqual(caught.exception.status_code, 400)
        self.assertIsNone(GoogleCalendarService.get_integration(self.user))

    def test_not_connected_and_network_failure(self):
        with google_env():
            with self.assertRaises(Exception) as caught:
                GoogleCalendarService.create_meet(self.user, "x")
            self.assertEqual(caught.exception.status_code, 400)
            self.connect()
            with patch(POST, side_effect=requests.ConnectionError()):
                with self.assertRaises(Exception) as caught:
                    GoogleCalendarService.create_meet(self.user, "x")
            self.assertEqual(caught.exception.status_code, 502)
            # no hangoutLink in the answer is also a Google-side failure
            with patch(POST, return_value=reply(200, {})):
                with self.assertRaises(Exception) as caught:
                    GoogleCalendarService.create_meet(self.user, "x")
            self.assertEqual(caught.exception.status_code, 502)


class GoogleApiAndMeetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a@a.com", "x12345678!", name="Ana")
        self.org = OrganizationService.create(self.user, name="Acme")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.general = ChatService.list_channels(self.user, self.org.id)[0]["id"]

    def test_status_connect_and_disconnect(self):
        base = f"{API}integrations/google/"
        self.assertEqual(self.client.get(base).json(), {"connected": False})
        with google_env():
            url = self.client.get(f"{base}authorize/").json()["url"]
            state = parse_qs(urlparse(url).query)["state"][0]
            data = {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600}
            with patch(POST, return_value=reply(200, data)):
                res = self.client.post(f"{base}connect/", {"code": "c", "state": state})
        self.assertEqual(res.json(), {"connected": True})
        self.assertEqual(self.client.get(base).json(), {"connected": True})
        self.client.delete(base)
        self.assertEqual(self.client.get(base).json(), {"connected": False})
        self.assertEqual(APIClient().get(base).status_code, 401)

    def test_meet_posts_the_link_in_the_channel(self):
        UserIntegration.objects.create(
            user=self.user,
            provider="google_calendar",
            access_token="AT",
            refresh_token="RT",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        with (
            google_env(),
            patch(POST, return_value=reply(200, {"hangoutLink": "https://meet/z"})),
        ):
            res = self.client.post(f"{API}chat/channels/{self.general}/meet/")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertIn("https://meet/z", res.json()["content"])
        self.assertEqual(ChatMessage.objects.get().author, self.user)

    def test_meet_needs_a_connected_account_and_channel_access(self):
        res = self.client.post(f"{API}chat/channels/{self.general}/meet/")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(ChatMessage.objects.count(), 0)
        stranger = APIClient()
        stranger.force_authenticate(
            User.objects.create_user("s@a.com", "x12345678!", name="S")
        )
        self.assertEqual(
            stranger.post(f"{API}chat/channels/{self.general}/meet/").status_code, 404
        )
