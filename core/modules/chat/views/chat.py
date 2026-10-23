from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.calendar_sync.services.google import GoogleCalendarService
from core.modules.chat.response_messages import MSG_CHAT_AFTER_INVALID
from core.modules.chat.serializers.chat import (
    ChatChannelSerializer,
    ChatDirectOpenSerializer,
    ChatMessageEditSerializer,
    ChatMessageSerializer,
    ChatMessageWriteSerializer,
    ChatTeamsChannelSerializer,
)
from core.modules.chat.services.chat import ChatService


class ChatChannelListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="My chat channels in an organization (General, my teams, direct)",
        responses={200: ChatChannelSerializer(many=True)},
    )
    def get(self, request, organization_id):
        channels = ChatService.list_channels(request.user, organization_id)
        return Response(ChatChannelSerializer(channels, many=True).data)


class ChatDirectView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Open (or get) the direct conversation with an organization member",
        request=ChatDirectOpenSerializer,
        responses={200: ChatChannelSerializer},
    )
    def post(self, request, organization_id):
        serializer = ChatDirectOpenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        channel = ChatService.open_direct(
            request.user, organization_id, serializer.validated_data["user_id"]
        )
        return Response(ChatChannelSerializer(channel).data)


class ChatTeamsChannelView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Create a conversation shared by two or more teams",
        request=ChatTeamsChannelSerializer,
        responses={201: ChatChannelSerializer},
    )
    def post(self, request, organization_id):
        serializer = ChatTeamsChannelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        channel = ChatService.create_teams_channel(
            request.user, organization_id, **serializer.validated_data
        )
        return Response(
            ChatChannelSerializer(channel).data, status=status.HTTP_201_CREATED
        )


class ChatMessageListCreateView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChatMessageSerializer

    @extend_schema(
        summary="Messages of a channel, newest first",
        parameters=[
            OpenApiParameter(
                "after", str, description="Only messages after this ISO date-time"
            )
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        after = self.request.query_params.get("after")
        if after is not None:
            after = parse_datetime(after)
            if after is None:
                raise ValidationError(MSG_CHAT_AFTER_INVALID)
        return ChatService.list_messages(
            self.request.user, self.kwargs["channel_id"], after
        )

    @extend_schema(
        summary="Send a message (JSON or multipart with files; pushed over /ws/)",
        request=ChatMessageWriteSerializer,
        responses={201: ChatMessageSerializer},
    )
    def post(self, request, channel_id):
        serializer = ChatMessageWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        message = ChatService.send(
            request.user,
            channel_id,
            data.get("content", ""),
            reply_to_id=data.get("reply_to"),
            task_id=data.get("task"),
            mention_ids=data.get("mentions", []),
            files=data.get("files", []),
        )
        return Response(
            ChatMessageSerializer(message).data, status=status.HTTP_201_CREATED
        )


class ChatPresenceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Ids of the organization members that are online now",
        responses={200: None},
    )
    def get(self, request, organization_id):
        return Response(
            {"online": ChatService.online_members(request.user, organization_id)}
        )


class ChatMeetView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Start a Google Meet and post its link in the channel",
        request=None,
        responses={201: ChatMessageSerializer},
    )
    def post(self, request, channel_id):
        channel = ChatService.get_channel(request.user, channel_id)
        link = GoogleCalendarService.create_meet(request.user, channel.name or "Meet")
        message = ChatService.send(
            request.user, channel_id, f"Join the meeting: {link}"
        )
        return Response(
            ChatMessageSerializer(message).data, status=status.HTTP_201_CREATED
        )


class ChatChannelReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Mark a channel as read", request=None, responses={204: None}
    )
    def post(self, request, channel_id):
        ChatService.mark_read(request.user, channel_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChatMessageDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Edit my message",
        request=ChatMessageEditSerializer,
        responses={200: ChatMessageSerializer},
    )
    def patch(self, request, message_id):
        serializer = ChatMessageEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = ChatService.edit(
            request.user, message_id, serializer.validated_data["content"]
        )
        return Response(ChatMessageSerializer(message).data)

    @extend_schema(
        summary="Delete my message (or any, as org admin outside direct chats)",
        responses={204: None},
    )
    def delete(self, request, message_id):
        ChatService.delete(request.user, message_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
