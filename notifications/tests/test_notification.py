from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from firebase_admin import messaging
from rest_framework.test import APIClient

from core.models.user import User
from notifications.models.notification import DeviceToken
from notifications.services.notification import NotificationService


class NotificationApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="a@a.com", password="x12345678!")
        self.other = User.objects.create_user(email="b@b.com", password="x12345678!")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_list_read_and_read_all(self):
        n1 = NotificationService.notify(self.user, "One")
        NotificationService.notify(self.user, "Two")
        other = NotificationService.notify(self.other, "Not mine")

        self.assertEqual(len(self.client.get("/api/notifications/").json()), 2)
        self.assertEqual(
            self.client.post(f"/api/notifications/{n1.id}/read/").status_code, 204
        )
        self.assertEqual(
            len(self.client.get("/api/notifications/?unread=true").json()), 1
        )
        self.assertEqual(
            self.client.post(f"/api/notifications/{other.id}/read/").status_code, 404
        )
        self.client.post("/api/notifications/read-all/")
        self.assertEqual(self.client.get("/api/notifications/?unread=true").json(), [])

    def test_register_and_unregister_device(self):
        url = "/api/notifications/devices/"
        self.assertEqual(self.client.post(url, {"token": "t1"}).status_code, 204)
        self.assertTrue(DeviceToken.objects.filter(user=self.user, token="t1").exists())
        # same browser logged in as another user moves the token
        other_client = APIClient()
        other_client.force_authenticate(self.other)
        other_client.post(url, {"token": "t1"})
        self.assertEqual(DeviceToken.objects.get(token="t1").user, self.other)
        other_client.delete(url, {"token": "t1"})
        self.assertFalse(DeviceToken.objects.exists())

    def test_anonymous_is_rejected(self):
        self.assertEqual(APIClient().get("/api/notifications/").status_code, 401)


@override_settings(FIREBASE_CREDENTIALS="fake.json")
@patch("notifications.services.notification._firebase_app")
@patch("notifications.services.notification.messaging.send_each_for_multicast")
class NotificationPushTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="a@a.com", password="x12345678!")

    def test_push_sends_and_drops_dead_tokens(self, send, _app):
        DeviceToken.objects.create(user=self.user, token="good")
        DeviceToken.objects.create(user=self.user, token="dead")
        send.return_value = MagicMock(
            responses=[
                MagicMock(exception=None),
                MagicMock(exception=messaging.UnregisteredError("gone")),
            ]
        )
        NotificationService.notify(self.user, "Hi", "body", {"id": 7})
        message = send.call_args.args[0]
        self.assertEqual(message.tokens, ["good", "dead"])
        self.assertEqual(message.data["id"], "7")
        self.assertEqual(
            list(DeviceToken.objects.values_list("token", flat=True)), ["good"]
        )

    def test_push_failure_keeps_notification(self, send, _app):
        DeviceToken.objects.create(user=self.user, token="t")
        send.side_effect = Exception("network")
        NotificationService.notify(self.user, "Hi")
        self.assertEqual(self.user.notifications.count(), 1)

    def test_no_tokens_no_call(self, send, _app):
        NotificationService.notify(self.user, "Hi")
        send.assert_not_called()


class SendPushApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(
            User.objects.create_user(email="a@a.com", password="x12345678!")
        )
        self.payload = {"token": "t", "title": "Hi", "body": "there"}

    def test_requires_title_and_token(self):
        res = self.client.post("/api/notifications/send/", {"body": "x"})
        self.assertEqual(res.status_code, 400)

    @override_settings(FIREBASE_CREDENTIALS="")
    def test_not_configured(self):
        res = self.client.post("/api/notifications/send/", self.payload)
        self.assertEqual(res.status_code, 503)

    @override_settings(FIREBASE_CREDENTIALS="fake.json")
    @patch("notifications.services.notification._firebase_app")
    @patch("notifications.services.notification.messaging.send", return_value="msg-1")
    def test_sends(self, send, _app):
        res = self.client.post("/api/notifications/send/", self.payload)
        self.assertEqual(res.json(), {"message_id": "msg-1"})
        message = send.call_args.args[0]
        self.assertEqual(
            (message.token, message.notification.title, message.notification.body),
            ("t", "Hi", "there"),
        )

    @override_settings(FIREBASE_CREDENTIALS="fake.json")
    @patch("notifications.services.notification._firebase_app")
    @patch(
        "notifications.services.notification.messaging.send",
        side_effect=messaging.UnregisteredError("gone"),
    )
    def test_fcm_error(self, send, _app):
        res = self.client.post("/api/notifications/send/", self.payload)
        self.assertEqual(res.status_code, 502)
