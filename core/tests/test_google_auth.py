from unittest import mock

from django.test import TestCase

from core.models.user import User

VERIFY = "core.services.google_auth.id_token.verify_oauth2_token"
GOOGLE_PAYLOAD = {"email": "g@gmail.com", "email_verified": True, "name": "G User"}


class GoogleLoginTests(TestCase):
    def login(self):
        return self.client.post("/api/login/google/", {"credential": "token"})

    @mock.patch(VERIFY, return_value=GOOGLE_PAYLOAD)
    def test_first_login_creates_user_and_sets_cookies(self, _):
        response = self.login()

        self.assertEqual(response.status_code, 200)
        self.assertIn("access_token", response.cookies)
        user = User.objects.get(email="g@gmail.com")
        self.assertEqual(user.name, "G User")
        self.assertFalse(user.has_usable_password())

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
            "/api/login/", {"email": "a@a.com", "password": "S3cure-pass!"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("refresh_token", response.cookies)
