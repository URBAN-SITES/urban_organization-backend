from unittest.mock import MagicMock, patch

from django.db import transaction
from django.test import TestCase, override_settings
from firebase_admin import messaging
from rest_framework.test import APIClient

from core.models.user import User
from core.modules.notifications.models.notification import DeviceToken
from core.modules.notifications.services.notification import NotificationService
from core.modules.user_settings.models.user_settings import UserSettings


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

        self.assertEqual(
            len(self.client.get("/api/v1/notifications/").json()["results"]), 2
        )
        self.assertEqual(
            self.client.post(f"/api/v1/notifications/{n1.id}/read/").status_code, 204
        )
        self.assertEqual(
            len(
                self.client.get("/api/v1/notifications/?unread=true").json()["results"]
            ),
            1,
        )
        self.assertEqual(
            self.client.post(f"/api/v1/notifications/{other.id}/read/").status_code, 404
        )
        self.client.post("/api/v1/notifications/read-all/")
        self.assertEqual(
            self.client.get("/api/v1/notifications/?unread=true").json()["results"], []
        )

    def test_register_and_unregister_device(self):
        url = "/api/v1/notifications/devices/"
        self.assertEqual(self.client.post(url, {"token": "t1"}).status_code, 204)
        self.assertTrue(DeviceToken.objects.filter(user=self.user, token="t1").exists())
        # same browser logged in as another user moves the token
        other_client = APIClient()
        other_client.force_authenticate(self.other)
        other_client.post(url, {"token": "t1"})
        self.assertEqual(DeviceToken.objects.get(token="t1").user, self.other)
        self.client.delete(url, {"token": "t1"})
        self.assertTrue(
            DeviceToken.objects.filter(user=self.other, token="t1").exists()
        )
        other_client.delete(url, {"token": "t1"})
        self.assertFalse(DeviceToken.objects.exists())

    def test_anonymous_is_rejected(self):
        self.assertEqual(APIClient().get("/api/v1/notifications/").status_code, 401)


@override_settings(FIREBASE_CREDENTIALS="fake.json", FRONTEND_URL="https://app.example/")
@patch("core.modules.notifications.services.notification._firebase_app")
@patch(
    "core.modules.notifications.services.notification.messaging.send_each_for_multicast"
)
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
        with self.captureOnCommitCallbacks(execute=True):
            notification = NotificationService.notify(
                self.user, "Hi", "body", {"id": 7}
            )
        message = send.call_args.args[0]
        self.assertEqual(message.tokens, ["good", "dead"])
        self.assertEqual(message.data["id"], "7")
        self.assertEqual(message.data["notification_id"], str(notification.pk))
        self.assertTrue(message.webpush.fcm_options.link.endswith("/notificacoes"))
        self.assertEqual(
            list(DeviceToken.objects.values_list("token", flat=True)), ["good"]
        )

    def test_push_failure_keeps_notification(self, send, _app):
        DeviceToken.objects.create(user=self.user, token="t")
        send.side_effect = Exception("network")
        with self.captureOnCommitCallbacks(execute=True):
            NotificationService.notify(self.user, "Hi")
        self.assertEqual(self.user.notifications.count(), 1)

    def test_no_tokens_no_call(self, send, _app):
        with self.captureOnCommitCallbacks(execute=True):
            NotificationService.notify(self.user, "Hi")
        send.assert_not_called()

    def test_opt_out_keeps_in_app_notification_without_push(self, send, _app):
        DeviceToken.objects.create(user=self.user, token="t")
        UserSettings.objects.create(user=self.user, push_enabled=False)
        with self.captureOnCommitCallbacks(execute=True):
            NotificationService.notify(self.user, "Hi")
        send.assert_not_called()
        self.assertEqual(self.user.notifications.count(), 1)

    def test_multicast_is_batched_at_500(self, send, _app):
        DeviceToken.objects.bulk_create(
            [DeviceToken(user=self.user, token=f"t{i}") for i in range(501)]
        )
        send.return_value = MagicMock(responses=[])
        with self.captureOnCommitCallbacks(execute=True):
            NotificationService.notify(self.user, "Hi")
        self.assertEqual(
            [len(call.args[0].tokens) for call in send.call_args_list], [500, 1]
        )


class NotificationDeliveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="a@a.com", password="x12345678!")

    @patch("core.modules.notifications.services.notification.send_to_user")
    @patch.object(NotificationService, "push")
    def test_delivery_waits_for_commit(self, push, websocket):
        with self.captureOnCommitCallbacks(execute=True):
            notification = NotificationService.notify(self.user, "Hi", "body")
            push.assert_not_called()
            websocket.assert_not_called()
        push.assert_called_once_with(notification)
        user_id, payload = websocket.call_args.args
        self.assertEqual(user_id, self.user.pk)
        self.assertEqual(payload["type"], "notification.created")
        self.assertEqual(payload["notification"]["id"], notification.pk)

    @patch.object(NotificationService, "deliver")
    def test_rollback_does_not_deliver(self, deliver):
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                NotificationService.notify(self.user, "Hi")
                transaction.set_rollback(True)
        deliver.assert_not_called()
        self.assertEqual(self.user.notifications.count(), 0)

    @patch(
        "core.modules.notifications.services.notification.send_to_user",
        side_effect=RuntimeError("offline"),
    )
    @patch.object(NotificationService, "push")
    def test_websocket_failure_still_attempts_push(self, push, websocket):
        with self.captureOnCommitCallbacks(execute=True):
            notification = NotificationService.notify(self.user, "Hi")
        push.assert_called_once_with(notification)


class SendPushApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email="a@a.com", password="x12345678!")
        self.client.force_authenticate(self.user)
        DeviceToken.objects.create(user=self.user, token="t")
        self.payload = {"token": "t", "title": "Hi", "body": "there"}

    def test_requires_title_and_token(self):
        res = self.client.post("/api/v1/notifications/send/", {"body": "x"})
        self.assertEqual(res.status_code, 400)

    @override_settings(FIREBASE_CREDENTIALS="fake.json")
    @patch("core.modules.notifications.services.notification.messaging.send")
    def test_cannot_send_to_another_users_device(self, send):
        other = User.objects.create_user(email="b@b.com", password="x12345678!")
        DeviceToken.objects.filter(token="t").update(user=other)
        res = self.client.post("/api/v1/notifications/send/", self.payload)
        self.assertEqual(res.status_code, 403)
        send.assert_not_called()

    @override_settings(FIREBASE_CREDENTIALS="fake.json")
    @patch("core.modules.notifications.services.notification.messaging.send")
    def test_test_push_respects_opt_out(self, send):
        UserSettings.objects.create(user=self.user, push_enabled=False)
        res = self.client.post("/api/v1/notifications/send/", self.payload)
        self.assertEqual(res.status_code, 403)
        send.assert_not_called()

    @override_settings(FIREBASE_CREDENTIALS="")
    def test_not_configured(self):
        res = self.client.post("/api/v1/notifications/send/", self.payload)
        self.assertEqual(res.status_code, 503)

    @override_settings(FIREBASE_CREDENTIALS="missing.json")
    @patch(
        "core.modules.notifications.services.notification._firebase_app",
        side_effect=FileNotFoundError("missing"),
    )
    def test_missing_credentials_returns_unavailable(self, _app):
        res = self.client.post("/api/v1/notifications/send/", self.payload)
        self.assertEqual(res.status_code, 503)

    @override_settings(FIREBASE_CREDENTIALS="fake.json")
    @patch("core.modules.notifications.services.notification._firebase_app")
    @patch(
        "core.modules.notifications.services.notification.messaging.send",
        return_value="msg-1",
    )
    def test_sends(self, send, _app):
        res = self.client.post("/api/v1/notifications/send/", self.payload)
        self.assertEqual(res.json(), {"message_id": "msg-1"})
        message = send.call_args.args[0]
        self.assertEqual(
            (message.token, message.notification.title, message.notification.body),
            ("t", "Hi", "there"),
        )

    @override_settings(FIREBASE_CREDENTIALS="fake.json")
    @patch("core.modules.notifications.services.notification._firebase_app")
    @patch(
        "core.modules.notifications.services.notification.messaging.send",
        side_effect=messaging.UnregisteredError("gone"),
    )
    def test_fcm_error(self, send, _app):
        res = self.client.post("/api/v1/notifications/send/", self.payload)
        self.assertEqual(res.status_code, 502)
