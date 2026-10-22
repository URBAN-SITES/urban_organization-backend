import logging

import firebase_admin
from django.conf import settings
from firebase_admin import credentials, messaging

from core.models.user import User
from notifications.models.notification import DeviceToken, Notification

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
        NotificationService.push(notification)
        return notification

    @staticmethod
    def push(notification: Notification) -> None:
        if not settings.FIREBASE_CREDENTIALS:
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
        try:
            result = messaging.send_each_for_multicast(
                messaging.MulticastMessage(
                    tokens=tokens,
                    notification=messaging.Notification(
                        title=notification.title, body=notification.message
                    ),
                    data=data,
                ),
                app=_firebase_app(),
            )
        except Exception:
            # push is best-effort: the notification is already saved
            logger.exception("FCM push failed")
            return
        dead = [
            token
            for token, response in zip(tokens, result.responses)
            if isinstance(
                response.exception,
                (messaging.UnregisteredError, messaging.SenderIdMismatchError),
            )
        ]
        DeviceToken.objects.filter(token__in=dead).delete()

    @staticmethod
    def send_to_token(token: str, title: str, body: str = "") -> str:
        """Push straight to one FCM token. Raises FirebaseError on failure."""
        return messaging.send(
            messaging.Message(
                token=token,
                notification=messaging.Notification(title=title, body=body),
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
