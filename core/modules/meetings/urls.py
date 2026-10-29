from django.urls import path

from core.modules.meetings.views.meeting import (
    LiveKitWebhookView,
    MeetingDetailView,
    MeetingJoinView,
    MeetingRecordingDetailView,
    MeetingRecordingDownloadView,
    MeetingRecordingStopView,
    MeetingRecordingsView,
    ProjectMeetingsView,
)

app_name = "meetings"

urlpatterns = [
    path(
        "sectors/<uuid:sector_id>/meetings/",
        ProjectMeetingsView.as_view(),
        name="project-meetings",
    ),
    path("meetings/livekit/webhook/", LiveKitWebhookView.as_view(), name="webhook"),
    path("meetings/<uuid:meeting_id>/", MeetingDetailView.as_view(), name="detail"),
    path("meetings/<uuid:meeting_id>/join/", MeetingJoinView.as_view(), name="join"),
    path(
        "meetings/<uuid:meeting_id>/recordings/",
        MeetingRecordingsView.as_view(),
        name="recordings",
    ),
    path(
        "meetings/<uuid:meeting_id>/recordings/<uuid:recording_id>/",
        MeetingRecordingDetailView.as_view(),
        name="recording",
    ),
    path(
        "meetings/<uuid:meeting_id>/recordings/<uuid:recording_id>/stop/",
        MeetingRecordingStopView.as_view(),
        name="recording-stop",
    ),
    path(
        "meetings/<uuid:meeting_id>/recordings/<uuid:recording_id>/download/",
        MeetingRecordingDownloadView.as_view(),
        name="recording-download",
    ),
]
