from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models.user import User
from core.modules.notifications.models.notification import DeviceToken
from core.services.user import AuthService


@override_settings(FIREBASE_CREDENTIALS="fake.json")
class PushFrontendContractTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="push@example.com", password="x12345678!"
        )
        tokens = AuthService.create_session(self.user, "test browser", "127.0.0.1")
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.cookies[settings.SIMPLE_JWT["AUTH_COOKIE"]] = tokens["access"]
        self.csrf = "a" * 32
        self.client.cookies[settings.CSRF_COOKIE_NAME] = self.csrf

    @patch("core.modules.notifications.services.notification._firebase_app")
    @patch(
        "core.modules.notifications.services.notification.messaging.send",
        return_value="projects/test/messages/accepted",
    )
    def test_frontend_cookie_csrf_registration_send_and_removal(self, send, _app):
        headers = {
            "HTTP_X_CSRFTOKEN": self.csrf,
            "HTTP_ORIGIN": "http://127.0.0.1:5173",
        }
        device = {"token": "browser-token"}
        response = self.client.post(
            "/api/v1/notifications/devices/", device, format="json", **headers
        )
        self.assertEqual(response.status_code, 204)

        response = self.client.post(
            "/api/v1/notifications/send/",
            {
                **device,
                "title": "ResenhaCoders",
                "body": "As notificações deste navegador estão funcionando.",
            },
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"message_id": "projects/test/messages/accepted"}
        )
        message = send.call_args.args[0]
        self.assertEqual(message.token, device["token"])
        self.assertEqual(message.notification.title, "ResenhaCoders")
        self.assertEqual(self.user.notifications.count(), 0)

        response = self.client.delete(
            "/api/v1/notifications/devices/", device, format="json", **headers
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(DeviceToken.objects.filter(user=self.user).exists())

    def test_cookie_authenticated_registration_requires_csrf_header(self):
        response = self.client.post(
            "/api/v1/notifications/devices/", {"token": "browser-token"}, format="json"
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("CSRF", response.json()["detail"])
        self.assertFalse(DeviceToken.objects.filter(user=self.user).exists())
