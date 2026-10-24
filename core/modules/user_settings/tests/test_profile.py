from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models.user import User
from core.modules.user_settings.models.user_settings import UserSettings


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class ProfileSettingsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            "profile@example.invalid", "S3cure-password!", name="Profile"
        )
        self.other = User.objects.create_user(
            "other@example.invalid", "S3cure-password!", name="Other"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = "/api/v1/users/me/settings/"

    def test_settings_require_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(
            self.client.patch(self.url, {"theme": "dark"}).status_code, 401
        )
        self.assertFalse(UserSettings.objects.exists())

    def test_settings_are_created_lazily_and_scoped_to_current_user(self):
        self.assertFalse(UserSettings.objects.exists())
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["theme"], "system")
        self.assertEqual(response.data["timezone"], "America/Sao_Paulo")
        self.client.get(self.url)
        self.assertEqual(UserSettings.objects.count(), 1)
        self.client.patch(
            self.url, {"theme": "dark", "push_enabled": False}, format="json"
        )
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url).data["theme"], "system")
        self.assertTrue(self.client.get(self.url).data["push_enabled"])

    def test_all_settings_round_trip_and_partial_updates_preserve_other_fields(self):
        payload = {
            "theme": "system",
            "locale": "en-US",
            "timezone": "Europe/Lisbon",
            "push_enabled": False,
            "email_product": False,
            "email_weekly_digest": True,
            "email_security": False,
            "email_assigned": True,
            "email_mentions": False,
            "email_deadlines": True,
            "app_comments": False,
            "app_status": True,
            "app_ai": False,
            "date_format": "long",
            "week_start": "monday",
            "compact_cards": True,
            "show_completed": False,
        }
        self.assertEqual(
            self.client.patch(self.url, payload, format="json").data, payload
        )
        self.assertEqual(self.client.get(self.url).data, payload)
        self.client.patch(self.url, {"theme": "light"}, format="json")
        self.assertEqual(self.client.get(self.url).data, {**payload, "theme": "light"})

    def test_invalid_preferences_do_not_write(self):
        for payload in (
            {"theme": "invalid"},
            {"timezone": "Invalid/Zone"},
            {"locale": "invalid locale"},
            {"date_format": "mm/dd/yyyy"},
            {"week_start": "friday"},
        ):
            response = self.client.patch(self.url, payload, format="json")
            self.assertEqual(response.status_code, 400)
        self.assertFalse(UserSettings.objects.exists())

    def test_cookie_authenticated_settings_write_requires_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        response = client.post(
            "/api/v1/login/",
            {"email": self.user.email, "password": "S3cure-password!"},
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            client.patch(
                self.url,
                {"theme": "dark"},
                format="json",
                secure=True,
                HTTP_ORIGIN="https://testserver",
            ).status_code,
            403,
        )
        token = client.cookies["csrftoken"].value
        response = client.patch(
            self.url,
            {"theme": "dark"},
            format="json",
            secure=True,
            HTTP_X_CSRFTOKEN=token,
            HTTP_ORIGIN="https://testserver",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["theme"], "dark")
        sessions = client.get("/api/v1/sessions/", secure=True).data
        self.assertEqual(len(sessions), 1)
        self.assertTrue(sessions[0]["current"])
        self.assertIn("location", sessions[0])
        self.assertIn("last_activity", sessions[0])
        self.assertNotIn("access_jti", sessions[0])

    def test_profile_fields_round_trip_without_exposing_private_data(self):
        payload = {
            "name": "New Name",
            "bio": "About me",
            "avatar_url": "https://example.org/me.png",
        }
        response = self.client.patch("/api/v1/users/me/update/", payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, payload)
        profile = self.client.get("/api/v1/users/me/").data
        for field, value in payload.items():
            self.assertEqual(profile[field], value)
        self.assertEqual(profile["id"], str(self.user.id))
        self.assertNotIn("password", profile)
        response = self.client.patch(
            "/api/v1/users/me/update/", {"email": "bad@example.org"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    @patch("core.services.email_change.send_email_token")
    @patch("core.services.email_change.secrets.randbelow", return_value=123456)
    def test_email_change_requires_code_and_current_password(self, _random, _mail):
        self.assertEqual(
            self.client.post(
                "/api/v1/email-change/request/", {"new_email": "new@example.invalid"}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/email-change/verify/", {"code": "123456"}
            ).status_code,
            200,
        )
        response = self.client.post(
            "/api/v1/email-change/confirm/", {"code": "123456", "password": "wrong"}
        )
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "profile@example.invalid")
        response = self.client.post(
            "/api/v1/email-change/confirm/",
            {"code": "123456", "password": "S3cure-password!"},
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.invalid")
        self.assertEqual(
            self.client.post(
                "/api/v1/email-change/confirm/",
                {"code": "123456", "password": "S3cure-password!"},
            ).status_code,
            400,
        )

    @patch("core.services.password_reset.send_email_token")
    @patch("core.services.password_reset.secrets.randbelow", return_value=123456)
    def test_existing_password_reset_flow_changes_password(self, _random, _mail):
        self.assertEqual(
            self.client.post(
                "/api/v1/password-reset/request/", {"email": self.user.email}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/password-reset/verify/",
                {"email": self.user.email, "code": "123456"},
            ).status_code,
            200,
        )
        payload = {
            "email": self.user.email,
            "code": "123456",
            "new_password": "New-S3cure-password!",
        }
        self.assertEqual(
            self.client.post("/api/v1/password-reset/confirm/", payload).status_code,
            200,
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(payload["new_password"]))
        self.assertFalse(self.user.check_password("S3cure-password!"))
