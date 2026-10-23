from django.conf import settings
from drf_spectacular.utils import OpenApiParameter, extend_schema
from firebase_admin.exceptions import FirebaseError
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.notifications.models.notification import Notification
from core.modules.notifications.response_messages import MSG_PUSH_NOT_CONFIGURED
from core.modules.notifications.serializers.notification import (
    DeviceTokenSerializer,
    NotificationSerializer,
    SendPushSerializer,
)
from core.modules.notifications.services.notification import NotificationService


@extend_schema(tags=["Notificações"])
class NotificationListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    @extend_schema(
        summary="List my notifications",
        parameters=[OpenApiParameter("unread", bool, description="Only unread")],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        unread_only = self.request.query_params.get("unread") == "true"
        return NotificationService.list_for(self.request.user, unread_only)


@extend_schema(tags=["Notificações"])
class NotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Mark a notification as read", request=None, responses={204: None}
    )
    def post(self, request, notification_id):
        try:
            NotificationService.mark_as_read(request.user, notification_id)
        except Notification.DoesNotExist:
            raise NotFound()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Notificações"])
class NotificationReadAllView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Mark all notifications as read", request=None, responses={204: None}
    )
    def post(self, request):
        NotificationService.mark_all_as_read(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Notificações"])
class DeviceTokenView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Register this device's FCM token for push",
        request=DeviceTokenSerializer,
        responses={204: None},
    )
    def post(self, request):
        serializer = DeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        NotificationService.register_device(
            request.user, serializer.validated_data["token"]
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="Remove this device's FCM token (call on logout)",
        request=DeviceTokenSerializer,
        responses={204: None},
    )
    def delete(self, request):
        serializer = DeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        NotificationService.unregister_device(
            request.user, serializer.validated_data["token"]
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Notificações"])
class SendPushView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Send a test push to my registered device",
        request=SendPushSerializer,
        responses={200: None, 403: None, 502: None, 503: None},
    )
    def post(self, request):
        serializer = SendPushSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not settings.FIREBASE_CREDENTIALS:
            return Response(
                {"detail": MSG_PUSH_NOT_CONFIGURED},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            message_id = NotificationService.send_to_token(
                request.user, **serializer.validated_data
            )
        except OSError, ValueError:
            return Response(
                {"detail": MSG_PUSH_NOT_CONFIGURED},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except FirebaseError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"message_id": message_id})
