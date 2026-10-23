from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.calendar_sync.response_messages import MSG_GOOGLE_DISCONNECTED
from core.modules.calendar_sync.serializers.google import (
    GoogleAuthorizeSerializer,
    GoogleConnectSerializer,
    GoogleStatusSerializer,
    TaskCalendarStatusSerializer,
)
from core.modules.calendar_sync.services.google import (
    SCOPE_DRIVE,
    GoogleCalendarService,
)
from core.modules.calendar_sync.services.tasks import TaskCalendarService


@extend_schema(tags=["Integrações"])
class GoogleStatusView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Is my Google account connected?",
        responses={200: GoogleStatusSerializer},
    )
    def get(self, request):
        integration = GoogleCalendarService.get_integration(request.user)
        return Response(
            {
                "connected": integration is not None,
                "drive": integration is not None
                and GoogleCalendarService.has_scope(integration, SCOPE_DRIVE),
            }
        )

    @extend_schema(summary="Disconnect my Google account", responses={200: None})
    def delete(self, request):
        GoogleCalendarService.disconnect(request.user)
        return Response({"detail": MSG_GOOGLE_DISCONNECTED})


@extend_schema(tags=["Integrações"])
class GoogleAuthorizeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Google consent URL (open it in the browser); ?drive=true also asks for Drive",
        parameters=[
            OpenApiParameter(
                "drive", bool, description="Also ask for Google Drive access"
            )
        ],
        responses={200: GoogleAuthorizeSerializer},
    )
    def get(self, request):
        drive = request.query_params.get("drive") == "true"
        return Response(
            {"url": GoogleCalendarService.authorize_url(request.user, drive)}
        )


@extend_schema(tags=["Integrações"])
class GoogleConnectView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Finish the connection with the code and state Google sent back",
        request=GoogleConnectSerializer,
        responses={200: GoogleStatusSerializer},
    )
    def post(self, request):
        serializer = GoogleConnectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        GoogleCalendarService.connect(request.user, **serializer.validated_data)
        return Response({"connected": True}, status=status.HTTP_200_OK)


@extend_schema(tags=["Integrações"])
class TaskCalendarView(APIView):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _payload(event):
        return {
            "synced": event is not None,
            "last_synced_at": event.last_synced_at if event else None,
        }

    @extend_schema(
        summary="Is this task in my Google Calendar?",
        responses={200: TaskCalendarStatusSerializer},
    )
    def get(self, request, task_id):
        return Response(self._payload(TaskCalendarService.get(request.user, task_id)))

    @extend_schema(
        summary="Add (or update) the task's due date as an all-day event in my Google Calendar",
        request=None,
        responses={200: TaskCalendarStatusSerializer},
    )
    def post(self, request, task_id):
        return Response(self._payload(TaskCalendarService.sync(request.user, task_id)))

    @extend_schema(
        summary="Remove the task's event from my Google Calendar", responses={204: None}
    )
    def delete(self, request, task_id):
        TaskCalendarService.unsync(request.user, task_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
