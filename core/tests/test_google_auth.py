from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from google.auth.exceptions import TransportError

from core.models.user import User

VERIFY = "core.services.google_auth.id_token.verify_oauth2_token"
GOOGLE_PAYLOAD = {"email": "g@gmail.com", "email_verified": True, "name": "G User"}


class GoogleLoginTests(TestCase):
    def setUp(self):
        cache.clear()  # the login throttle (10/min) is shared by every test
        self.addCleanup(cache.clear)

    def login(self):
        return self.client.post("/api/v1/login/google/", {"credential": "token"})

    @mock.patch(VERIFY, return_value=GOOGLE_PAYLOAD)
    def test_first_login_creates_user_and_sets_cookies(self, _):
        response = self.login()

        self.assertEqual(response.status_code, 200)
        self.assertIn("access_token", response.cookies)
        user = User.objects.get(email="g@gmail.com")
        self.assertEqual(user.name, "G User")
        self.assertFalse(user.has_usable_password())

    @mock.patch("core.services.google_auth.GOOGLE_CLIENT_ID", "test-client-id")
    @mock.patch(VERIFY, side_effect=ValueError)
    def test_invalid_credential_is_rejected(self, _):
        # DRF answers 403 on views without authentication classes
        self.assertEqual(self.login().status_code, 403)

    @mock.patch(VERIFY, return_value=GOOGLE_PAYLOAD)
    def test_deactivated_user_is_rejected(self, _):
        user = User.objects.create_user("g@gmail.com", "x", name="G", is_active=False)
        user.last_login = user.created_at
        user.save()
        # DRF answers 403 on views without authentication classes
        self.assertEqual(self.login().status_code, 403)

    def test_email_login_still_works(self):
        User.objects.create_user("a@a.com", "S3cure-pass!", name="A")
        response = self.client.post(
            "/api/v1/login/", {"email": "a@a.com", "password": "S3cure-pass!"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("refresh_token", response.cookies)

    def test_login_body_does_not_expose_the_tokens(self):
        User.objects.create_user("a@a.com", "S3cure-pass!", name="A")
        response = self.client.post(
            "/api/v1/login/", {"email": "a@a.com", "password": "S3cure-pass!"}
        )
        self.assertEqual(list(response.json()), ["detail"])
        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)


class GoogleLoginHardeningTests(TestCase):
    def setUp(self):
        cache.clear()  # the login throttle (10/min) is shared by every test
        self.addCleanup(cache.clear)

    def login(self):
        return self.client.post("/api/v1/login/google/", {"credential": "token"})

    @mock.patch(VERIFY, side_effect=TransportError("offline"))
    def test_google_unreachable_is_a_503_not_a_server_error(self, _):
        self.assertEqual(self.login().status_code, 503)

    @mock.patch(VERIFY, side_effect=ValueError)
    def test_missing_client_id_is_reported_as_not_configured(self, _):
        with mock.patch("core.services.google_auth.GOOGLE_CLIENT_ID", ""):
            response = self.login()
        self.assertEqual(response.status_code, 503)
        self.assertIn("not configured", response.json()["detail"])

    @mock.patch(VERIFY, return_value={"email_verified": True, "name": "No Mail"})
    def test_token_without_email_is_rejected(self, _):
        self.assertEqual(self.login().status_code, 403)
        self.assertEqual(User.objects.count(), 0)

    @mock.patch(VERIFY, return_value=GOOGLE_PAYLOAD)
    def test_token_is_verified_against_our_client_id_with_clock_tolerance(self, verify):
        with mock.patch("core.services.google_auth.GOOGLE_CLIENT_ID", "client-123"):
            self.login()
        args, kwargs = verify.call_args
        self.assertEqual(
            args[2], "client-123"
        )  # never None: that disables the audience check
        self.assertEqual(kwargs["clock_skew_in_seconds"], 10)
