import logging
from threading import Lock

import firebase_admin
from django.conf import settings
from django.db import transaction
from firebase_admin import credentials, messaging
from firebase_admin.exceptions import FirebaseError
from rest_framework.exceptions import PermissionDenied

from core.models.user import User
from core.modules.notifications.models.notification import DeviceToken, Notification
from core.modules.notifications.response_messages import (
    MSG_DEVICE_NOT_REGISTERED,
    MSG_PUSH_DISABLED,
)
from core.modules.notifications.serializers.notification import NotificationSerializer
from core.modules.user_settings.models.user_settings import UserSettings
from core.websockets.consumers import send_to_user

logger = logging.getLogger(__name__)
_firebase_lock = Lock()


def _firebase_app():
    # Initialization is lazy and may be reached by concurrent first requests.
    with _firebase_lock:
        try:
            return firebase_admin.get_app()
        except ValueError:
            return firebase_admin.initialize_app(
                credentials.Certificate(settings.FIREBASE_CREDENTIALS)
            )


class NotificationService:
    @staticmethod
    def notify(user: User, title: str, message: str = "", data=None) -> Notification:
        """Call from any service: NotificationService.notify(user, "Payment approved")"""
        notification = Notification.objects.create(
            user=user, title=str(title)[:255], message=message, data=data or {}
        )
        # An external delivery failure must not turn a committed business action
        # into HTTP 500 or prevent later recipients' callbacks from running.
        transaction.on_commit(
            lambda: NotificationService.deliver(notification), robust=True
        )
        return notification

    @staticmethod
    def deliver(notification: Notification) -> None:
        try:
            send_to_user(
                notification.user_id,
                {
                    "type": "notification.created",
                    "notification": NotificationSerializer(notification).data,
                },
            )
        except Exception:
            logger.exception("Notification websocket delivery failed")
        NotificationService.push(notification)

    @staticmethod
    def push(notification: Notification) -> None:
        if not User.objects.filter(pk=notification.user_id, is_active=True).exists():
            return
        if not settings.FIREBASE_CREDENTIALS:
            logger.warning(
                "FCM push skipped: credentials not configured notification_id=%s",
                notification.pk,
            )
            return
        if UserSettings.objects.filter(
            user=notification.user, push_enabled=False
        ).exists():
            logger.debug(
                "FCM push skipped: user opted out notification_id=%s", notification.pk
            )
            return
        tokens = list(
            DeviceToken.objects.filter(user=notification.user).values_list(
                "token", flat=True
            )
        )
        if not tokens:
            logger.debug(
                "FCM push skipped: no registered devices notification_id=%s",
                notification.pk,
            )
            return
        # FCM data values must be strings
        data = {k: str(v) for k, v in notification.data.items()}
        data["notification_id"] = str(notification.id)
        for offset in range(0, len(tokens), 500):
            batch = tokens[offset : offset + 500]
            try:
                result = messaging.send_each_for_multicast(
                    messaging.MulticastMessage(
                        tokens=batch,
                        notification=messaging.Notification(
                            title=notification.title, body=notification.message
                        ),
                        data=data,
                        webpush=NotificationService.webpush(str(notification.id)),
                    ),
                    app=_firebase_app(),
                )
            except Exception:
                # Push is best-effort: the notification is already saved.
                logger.exception("FCM push failed notification_id=%s", notification.pk)
                continue
            dead = []
            for response_index, (token, response) in enumerate(
                zip(batch, result.responses)
            ):
                error = response.exception
                if error is None:
                    continue
                # A project mismatch is a configuration error, not an expired token.
                # Keep the device so fixing credentials does not require registration again.
                if isinstance(error, messaging.UnregisteredError):
                    dead.append(token)
                logger.warning(
                    "FCM device delivery failed notification_id=%s device_index=%s error_type=%s error_code=%s",
                    notification.pk,
                    offset + response_index,
                    type(error).__name__,
                    getattr(error, "code", type(error).__name__),
                )
            DeviceToken.objects.filter(user=notification.user, token__in=dead).delete()
            logger.info(
                "FCM batch completed notification_id=%s success_count=%s failure_count=%s",
                notification.pk,
                result.success_count,
                result.failure_count,
            )

    @staticmethod
    def webpush(tag: str = "") -> messaging.WebpushConfig:
        frontend_url = settings.FRONTEND_URL.rstrip("/")
        return messaging.WebpushConfig(
            notification=messaging.WebpushNotification(
                icon="/icons/hackathon-192.png", tag=tag or None
            ),
            # FCM click links require HTTPS; localhost still supports receiving push.
            fcm_options=(
                messaging.WebpushFCMOptions(link=f"{frontend_url}/notificacoes")
                if frontend_url.startswith("https://")
                else None
            ),
        )

    @staticmethod
    def send_to_token(user: User, token: str, title: str, body: str = "") -> str:
        """Push straight to one FCM token. Raises FirebaseError on failure."""
        if not DeviceToken.objects.filter(user=user, token=token).exists():
            raise PermissionDenied(MSG_DEVICE_NOT_REGISTERED)
        if UserSettings.objects.filter(user=user, push_enabled=False).exists():
            raise PermissionDenied(MSG_PUSH_DISABLED)
        try:
            message_id = messaging.send(
                messaging.Message(
                    token=token,
                    notification=messaging.Notification(title=title, body=body),
                    webpush=NotificationService.webpush(),
                ),
                app=_firebase_app(),
            )
        except FirebaseError as error:
            if isinstance(error, messaging.UnregisteredError):
                DeviceToken.objects.filter(user=user, token=token).delete()
            logger.warning(
                "FCM test delivery failed user_id=%s error_type=%s error_code=%s",
                user.pk,
                type(error).__name__,
                error.code,
            )
            raise
        logger.info("FCM test accepted user_id=%s message_id=%s", user.pk, message_id)
        return message_id

    @staticmethod
    def register_device(user: User, token: str) -> None:
        DeviceToken.objects.update_or_create(token=token, defaults={"user": user})

    @staticmethod
    def unregister_device(user: User, token: str) -> None:
        DeviceToken.objects.filter(user=user, token=token).delete()

    @staticmethod
    def list_for(user: User, unread_only: bool = False):
        notifications = Notification.objects.filter(user=user)
        return notifications.filter(is_read=False) if unread_only else notifications

    @staticmethod
    def mark_as_read(user: User, notification_id: int) -> None:
        updated = Notification.objects.filter(id=notification_id, user=user).update(
            is_read=True
        )
        if not updated:
            raise Notification.DoesNotExist

    @staticmethod
    def mark_all_as_read(user: User) -> None:
        Notification.objects.filter(user=user, is_read=False).update(is_read=True)
