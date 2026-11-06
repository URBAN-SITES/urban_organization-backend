from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.calls.serializers import (
    CallStartSerializer,
    MediaSerializer,
    SignalSerializer,
)
from core.modules.calls.services.calls import CallService, call_payload


def _fresh(user, call_id) -> dict:
    return call_payload(CallService.get_for(user, call_id))


@extend_schema(tags=["Calls"])
class CallListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="My call history (latest first, up to 100)", responses={200: dict}
    )
    def get(self, request):
        return Response([call_payload(c) for c in CallService.history(request.user)])

    @extend_schema(
        summary="Start a voice or video call in a chat channel (rings the others)",
        request=CallStartSerializer,
        responses={201: dict},
    )
    def post(self, request):
        serializer = CallStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        call = CallService.start(
            request.user,
            serializer.validated_data["channel_id"],
            serializer.validated_data["kind"],
        )
        return Response(call_payload(call), status=status.HTTP_201_CREATED)


@extend_schema(tags=["Calls"])
class IceServersView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="ICE servers for new RTCPeerConnection({iceServers})",
        responses={200: dict},
    )
    def get(self, request):
        return Response({"ice_servers": CallService.ice_servers(request.user)})


@extend_schema(tags=["Calls"])
class CallDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="A call and who is in it", responses={200: dict})
    def get(self, request, call_id):
        CallService.expire_unanswered(CallService.get_for(request.user, call_id))
        return Response(_fresh(request.user, call_id))


def _action(name: str, summary: str):
    @extend_schema(tags=["Calls"], summary=summary, request=None, responses={200: dict})
    def post(self, request, call_id):
        getattr(CallService, name)(request.user, call_id)
        return Response(_fresh(request.user, call_id))

    return type(
        f"Call{name.capitalize()}View",
        (APIView,),
        {"permission_classes": [IsAuthenticated], "post": post},
    )


CallJoinView = _action("join", "Answer / join the call")
CallDeclineView = _action("decline", "Decline a call that is ringing for me")
CallLeaveView = _action("leave", "Hang up")


@extend_schema(tags=["Calls"])
class CallSignalView(APIView):
    """HTTP fallback; the WebSocket `call.signal` is the normal path."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Relay a WebRTC offer/answer/ICE candidate to one participant",
        request=SignalSerializer,
        responses={204: None},
    )
    def post(self, request, call_id):
        serializer = SignalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        CallService.signal(
            request.user,
            call_id,
            serializer.validated_data["to_user_id"],
            serializer.validated_data["data"],
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Calls"])
class CallMediaView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="My mic/camera/screen state, shown to the others",
        request=MediaSerializer,
        responses={200: dict},
    )
    def post(self, request, call_id):
        serializer = MediaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        CallService.media(request.user, call_id, serializer.validated_data)
        return Response(_fresh(request.user, call_id))
