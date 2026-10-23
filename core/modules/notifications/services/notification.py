import logging

import firebase_admin
from django.conf import settings
from django.db import transaction
from firebase_admin import credentials, messaging
from rest_framework.exceptions import PermissionDenied

from core.models.user import User
from core.modules.notifications.models.notification import DeviceToken, Notification
from core.modules.notifications.response_messages import MSG_DEVICE_NOT_REGISTERED
from core.modules.notifications.serializers.notification import NotificationSerializer
from core.modules.user_settings.models.user_settings import UserSettings
from core.websockets.consumers import send_to_user

logger = logging.getLogger(__name__)


def _firebase_app():
    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            credentials.Certificate(settings.FIREBASE_CREDENTIALS)
        )
    return firebase_admin.get_app()


class NotificationService:
    @staticmethod
    def notify(user: User, title: str, message: str = "", data=None) -> Notification:
        """Call from any service: NotificationService.notify(user, "Payment approved")"""
        notification = Notification.objects.create(
            user=user, title=title, message=message, data=data or {}
        )
        transaction.on_commit(lambda: NotificationService.deliver(notification))
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
        if not settings.FIREBASE_CREDENTIALS or not notification.user.is_active:
            return
        if UserSettings.objects.filter(
            user=notification.user, push_enabled=False
        ).exists():
            return
        tokens = list(
            DeviceToken.objects.filter(user=notification.user).values_list(
                "token", flat=True
            )
        )
        if not tokens:
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
                logger.exception("FCM push failed")
                continue
            dead = [
                token
                for token, response in zip(batch, result.responses)
                if isinstance(
                    response.exception,
                    (messaging.UnregisteredError, messaging.SenderIdMismatchError),
                )
            ]
            DeviceToken.objects.filter(user=notification.user, token__in=dead).delete()

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
            raise PermissionDenied(MSG_DEVICE_NOT_REGISTERED)
        return messaging.send(
            messaging.Message(
                token=token,
                notification=messaging.Notification(title=title, body=body),
                webpush=NotificationService.webpush(),
            ),
            app=_firebase_app(),
        )

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
