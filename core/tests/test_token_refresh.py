from django.test import TestCase, override_settings
from rest_framework_simplejwt.tokens import RefreshToken

from core.models.user import User, UserSession


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class TokenRefreshTests(TestCase):
    def test_refresh_rotates_session_tokens_and_updates_activity(self):
        User.objects.create_user(
            "refresh@example.invalid", "S3cure-password!", name="Test"
        )
        login = self.client.post(
            "/api/v1/login/",
            {"email": "refresh@example.invalid", "password": "S3cure-password!"},
            secure=True,
        )
        self.assertEqual(login.status_code, 200)
        session = UserSession.objects.get()
        previous_jti = session.refresh_jti
        previous_activity = session.last_activity

        response = self.client.post("/api/v1/refresh/", secure=True)

        self.assertEqual(response.status_code, 200)
        session.refresh_from_db()
        self.assertNotEqual(session.refresh_jti, previous_jti)
        self.assertEqual(
            session.refresh_jti,
            RefreshToken(response.cookies["refresh_token"].value)["jti"],
        )
        self.assertGreater(session.last_activity, previous_activity)
