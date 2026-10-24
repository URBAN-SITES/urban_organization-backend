from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

from django.db import transaction
from django.test import SimpleTestCase, TestCase, override_settings
from firebase_admin import messaging
from firebase_admin.exceptions import UnavailableError
from rest_framework.test import APIClient

from core.models.user import User
from core.modules.notifications.models.notification import DeviceToken
from core.modules.notifications.response_messages import MSG_PUSH_DISABLED
from core.modules.notifications.services.notification import (
    NotificationService,
    _firebase_app,
)
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


@override_settings(
    FIREBASE_CREDENTIALS="fake.json", FRONTEND_URL="https://app.example/"
)
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

    def test_project_mismatch_is_logged_without_deleting_device(self, send, _app):
        DeviceToken.objects.create(user=self.user, token="private-device-token")
        send.return_value = MagicMock(
            responses=[
                MagicMock(exception=messaging.SenderIdMismatchError("wrong project"))
            ],
            success_count=0,
            failure_count=1,
        )
        with self.assertLogs(
            "core.modules.notifications.services.notification", level="WARNING"
        ) as logs:
            with self.captureOnCommitCallbacks(execute=True):
                NotificationService.notify(self.user, "Hi")
        self.assertTrue(DeviceToken.objects.filter(user=self.user).exists())
        self.assertIn("SenderIdMismatchError", " ".join(logs.output))
        self.assertNotIn("private-device-token", " ".join(logs.output))

    def test_individual_transient_error_is_logged_and_token_is_kept(self, send, _app):
        DeviceToken.objects.create(user=self.user, token="private-device-token")
        send.return_value = MagicMock(
            responses=[MagicMock(exception=UnavailableError("try later"))],
            success_count=0,
            failure_count=1,
        )
        with self.assertLogs(
            "core.modules.notifications.services.notification", level="WARNING"
        ) as logs:
            with self.captureOnCommitCallbacks(execute=True):
                NotificationService.notify(self.user, "Hi")
        self.assertTrue(DeviceToken.objects.filter(user=self.user).exists())
        self.assertEqual(self.user.notifications.count(), 1)
        self.assertIn("UNAVAILABLE", " ".join(logs.output))
        self.assertNotIn("private-device-token", " ".join(logs.output))

    @override_settings(FIREBASE_CREDENTIALS="")
    def test_missing_configuration_is_logged_without_sending(self, send, _app):
        DeviceToken.objects.create(user=self.user, token="t")
        with self.assertLogs(
            "core.modules.notifications.services.notification", level="WARNING"
        ) as logs:
            with self.captureOnCommitCallbacks(execute=True):
                NotificationService.notify(self.user, "Hi")
        self.assertIn("credentials not configured", " ".join(logs.output))
        send.assert_not_called()
        self.assertEqual(self.user.notifications.count(), 1)

    @override_settings(FRONTEND_URL="http://localhost:5173/")
    def test_localhost_receives_notification_without_https_click_link(self, send, _app):
        DeviceToken.objects.create(user=self.user, token="t")
        send.return_value = MagicMock(responses=[])
        with self.captureOnCommitCallbacks(execute=True):
            NotificationService.notify(self.user, "Hi", "body")
        message = send.call_args.args[0]
        self.assertEqual(message.notification.title, "Hi")
        self.assertEqual(message.notification.body, "body")
        self.assertIsNone(message.webpush.fcm_options)

    def test_deactivation_before_commit_suppresses_push(self, send, _app):
        DeviceToken.objects.create(user=self.user, token="t")
        with self.captureOnCommitCallbacks(execute=True):
            NotificationService.notify(self.user, "Hi")
            User.objects.filter(pk=self.user.pk).update(is_active=False)
        send.assert_not_called()


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

    @patch.object(NotificationService, "deliver")
    def test_unexpected_delivery_failure_does_not_skip_later_recipients(self, deliver):
        deliver.side_effect = [
            RuntimeError("database unavailable during delivery"),
            None,
        ]
        with self.assertLogs("django.test", level="ERROR"):
            with self.captureOnCommitCallbacks(execute=True):
                first = NotificationService.notify(self.user, "First")
                second = NotificationService.notify(self.user, "Second")
        self.assertEqual(
            [call.args[0] for call in deliver.call_args_list], [first, second]
        )
        self.assertEqual(self.user.notifications.count(), 2)

    def test_generated_title_fits_database_limit(self):
        notification = NotificationService.notify(
            self.user, "a" * 255 + " mentioned you"
        )
        self.assertEqual(len(notification.title), 255)


class FirebaseInitializationTests(SimpleTestCase):
    @override_settings(FIREBASE_CREDENTIALS="fake.json")
    @patch("core.modules.notifications.services.notification.credentials.Certificate")
    @patch(
        "core.modules.notifications.services.notification.firebase_admin.initialize_app"
    )
    @patch("core.modules.notifications.services.notification.firebase_admin.get_app")
    def test_concurrent_initialization_uses_one_default_app(
        self, get_app, initialize, certificate
    ):
        app = object()
        initialized = False

        def get():
            if not initialized:
                raise ValueError("No default app")
            return app

        def create(credential):
            nonlocal initialized
            if initialized:
                raise ValueError("App already exists")
            initialized = True
            return app

        get_app.side_effect = get
        initialize.side_effect = create
        with ThreadPoolExecutor(max_workers=4) as executor:
            apps = list(executor.map(lambda _: _firebase_app(), range(8)))
        self.assertTrue(all(result is app for result in apps))
        initialize.assert_called_once_with(certificate.return_value)
        certificate.assert_called_once_with("fake.json")


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
        self.assertEqual(res.json()["detail"], str(MSG_PUSH_DISABLED))
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
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"message_id": "msg-1"})
        # The frontend test checks FCM delivery, not inbox persistence.
        self.assertEqual(self.user.notifications.count(), 0)
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
        self.assertFalse(DeviceToken.objects.filter(user=self.user, token="t").exists())

    @override_settings(FIREBASE_CREDENTIALS="fake.json")
    @patch("core.modules.notifications.services.notification._firebase_app")
    @patch(
        "core.modules.notifications.services.notification.messaging.send",
        side_effect=messaging.SenderIdMismatchError("wrong project"),
    )
    def test_test_push_project_mismatch_preserves_token(self, send, _app):
        with self.assertLogs(
            "core.modules.notifications.services.notification", level="WARNING"
        ) as logs:
            res = self.client.post(
                "/api/v1/notifications/send/", self.payload, format="json"
            )
        self.assertEqual(res.status_code, 502)
        self.assertTrue(DeviceToken.objects.filter(user=self.user, token="t").exists())
        self.assertIn("SenderIdMismatchError", " ".join(logs.output))

    @override_settings(FIREBASE_CREDENTIALS="fake.json")
    @patch("core.modules.notifications.services.notification._firebase_app")
    @patch(
        "core.modules.notifications.services.notification.messaging.send",
        side_effect=UnavailableError("try later"),
    )
    def test_test_push_transient_error_preserves_token(self, send, _app):
        res = self.client.post(
            "/api/v1/notifications/send/", self.payload, format="json"
        )
        self.assertEqual(res.status_code, 502)
        self.assertTrue(DeviceToken.objects.filter(user=self.user, token="t").exists())
