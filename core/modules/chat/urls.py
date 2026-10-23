from django.urls import path

from core.modules.chat.views.chat import (
    ChatChannelListView,
    ChatChannelReadView,
    ChatDirectView,
    ChatMeetView,
    ChatMessageDetailView,
    ChatMessageListCreateView,
    ChatPresenceView,
    ChatTeamsChannelView,
)

app_name = "chat"

# mounted at the API root: organization-scoped and channel/message-scoped routes
urlpatterns = [
    path(
        "organizations/<uuid:organization_id>/chat/channels/",
        ChatChannelListView.as_view(),
        name="channel-list",
    ),
    path(
        "organizations/<uuid:organization_id>/chat/direct/",
        ChatDirectView.as_view(),
        name="direct",
    ),
    path(
        "organizations/<uuid:organization_id>/chat/team-channels/",
        ChatTeamsChannelView.as_view(),
        name="teams-channel",
    ),
    path(
        "organizations/<uuid:organization_id>/chat/presence/",
        ChatPresenceView.as_view(),
        name="presence",
    ),
    path(
        "chat/channels/<uuid:channel_id>/messages/",
        ChatMessageListCreateView.as_view(),
        name="message-list",
    ),
    path(
        "chat/channels/<uuid:channel_id>/meet/",
        ChatMeetView.as_view(),
        name="channel-meet",
    ),
    path(
        "chat/channels/<uuid:channel_id>/read/",
        ChatChannelReadView.as_view(),
        name="channel-read",
    ),
    path(
        "chat/messages/<uuid:message_id>/",
        ChatMessageDetailView.as_view(),
        name="message-detail",
    ),
]
