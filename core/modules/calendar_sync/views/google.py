from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.calendar_sync.response_messages import MSG_GOOGLE_DISCONNECTED
from core.modules.calendar_sync.serializers.google import (
    GoogleAuthorizeSerializer,
    GoogleConnectSerializer,
    GoogleStatusSerializer,
)
from core.modules.calendar_sync.services.google import GoogleCalendarService


class GoogleStatusView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Is my Google account connected?",
        responses={200: GoogleStatusSerializer},
    )
    def get(self, request):
        return Response(
            {
                "connected": GoogleCalendarService.get_integration(request.user)
                is not None
            }
        )

    @extend_schema(summary="Disconnect my Google account", responses={200: None})
    def delete(self, request):
        GoogleCalendarService.disconnect(request.user)
        return Response({"detail": MSG_GOOGLE_DISCONNECTED})


class GoogleAuthorizeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Google consent URL (open it in the browser)",
        responses={200: GoogleAuthorizeSerializer},
    )
    def get(self, request):
        return Response({"url": GoogleCalendarService.authorize_url(request.user)})


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
