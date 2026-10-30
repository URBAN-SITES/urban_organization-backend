from django.test import TestCase, override_settings

from core.models.user import User


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class RememberMeTests(TestCase):
    def setUp(self):
        User.objects.create_user(
            "remember@example.invalid", "S3cure-password!", name="Test"
        )

    def login(self, **extra):
        return self.client.post(
            "/api/v1/login/",
            {
                "email": "remember@example.invalid",
                "password": "S3cure-password!",
                **extra,
            },
            content_type="application/json",
            secure=True,
        )

    def test_login_remembers_by_default(self):
        response = self.login()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.cookies["access_token"]["max-age"])
        self.assertTrue(response.cookies["refresh_token"]["max-age"])
        self.assertEqual(response.cookies["session_only"].value, "")

    def test_login_without_remember_sets_session_cookies(self):
        response = self.login(remember=False)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.cookies["access_token"]["max-age"], "")
        self.assertEqual(response.cookies["refresh_token"]["max-age"], "")
        self.assertEqual(response.cookies["refresh_token"]["expires"], "")
        self.assertEqual(response.cookies["session_only"].value, "1")
        self.assertTrue(response.cookies["session_only"]["httponly"])

    def test_refresh_keeps_session_only_cookies(self):
        self.login(remember=False)

        response = self.client.post("/api/v1/refresh/", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.cookies["access_token"]["max-age"], "")
        self.assertEqual(response.cookies["refresh_token"]["max-age"], "")

    def test_refresh_keeps_persistent_cookies(self):
        self.login()

        response = self.client.post("/api/v1/refresh/", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.cookies["refresh_token"]["max-age"])

    def test_remembered_login_clears_old_marker(self):
        self.login(remember=False)

        response = self.login(remember=True)

        self.assertEqual(response.cookies["session_only"].value, "")
        self.assertEqual(response.cookies["session_only"]["max-age"], 0)

    def test_logout_removes_marker(self):
        self.login(remember=False)

        response = self.client.post("/api/v1/me/logout/", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.cookies["session_only"].value, "")
