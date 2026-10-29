from datetime import timedelta

from django.contrib.auth import get_user_model
from rest_framework import serializers

from core.modules.kanban.services.sector import Role
from core.modules.meetings.models.meeting import Meeting, MeetingRecording
from core.modules.meetings.services.meetings import retention_days

User = get_user_model()


class PersonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    avatar_url = serializers.CharField(allow_blank=True)


class MeetingSerializer(serializers.ModelSerializer):
    """`can_manage`/`can_join` need `user` and the sector `role` in the context."""

    sector_id = serializers.UUIDField(read_only=True)
    created_by = PersonSerializer(read_only=True, allow_null=True)
    participants = PersonSerializer(many=True, read_only=True)
    recording_count = serializers.IntegerField(read_only=True, default=0)
    can_manage = serializers.SerializerMethodField()
    can_join = serializers.SerializerMethodField()

    class Meta:
        model = Meeting
        fields = (
            "id",
            "sector_id",
            "title",
            "description",
            "starts_at",
            "ends_at",
            "created_by",
            "participants",
            "recording_count",
            "can_manage",
            "can_join",
            "created_at",
        )

    def get_can_manage(self, meeting) -> bool:
        user = self.context["user"]
        return meeting.created_by_id == user.id or self.context["role"] == Role.MANAGER

    def get_can_join(self, meeting) -> bool:
        user = self.context["user"]
        return self.get_can_manage(meeting) or any(
            person.id == user.id for person in meeting.participants.all()
        )


class MeetingWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(
        max_length=5000, required=False, allow_blank=True
    )
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    participants = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True),
        many=True,
        required=False,
    )


class MeetingListQuerySerializer(serializers.Serializer):
    when = serializers.ChoiceField(
        choices=("all", "upcoming", "past"), required=False, default="all"
    )


class JoinSerializer(serializers.Serializer):
    consent = serializers.BooleanField()


class JoinResultSerializer(serializers.Serializer):
    url = serializers.CharField()
    token = serializers.CharField()
    room = serializers.CharField()
    identity = serializers.CharField()
    can_record = serializers.BooleanField()
    recording = serializers.BooleanField()


class RecordingSerializer(serializers.ModelSerializer):
    """`links` (signed URLs) come from the context, keyed by recording id."""

    started_by = PersonSerializer(read_only=True, allow_null=True)
    play_url = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    expires_at = serializers.SerializerMethodField()
    insight_status = serializers.SerializerMethodField()

    class Meta:
        model = MeetingRecording
        fields = (
            "id",
            "status",
            "started_by",
            "started_at",
            "ended_at",
            "duration_seconds",
            "size_bytes",
            "participants",
            "error",
            "play_url",
            "download_url",
            "expires_at",
            "insight_status",
        )

    def _links(self, recording) -> dict:
        return self.context.get("links", {}).get(recording.id, {})

    def get_play_url(self, recording) -> str | None:
        return self._links(recording).get("play_url")

    def get_download_url(self, recording) -> str | None:
        return self._links(recording).get("download_url")

    def get_expires_at(self, recording) -> str:
        """When the retention policy deletes it (MEETING_RECORDING_RETENTION_DAYS)."""
        return (recording.started_at + timedelta(days=retention_days())).isoformat()

    def get_insight_status(self, recording) -> str | None:
        insight = getattr(recording, "insight", None)
        return insight.status if insight else None


class DownloadSerializer(serializers.Serializer):
    url = serializers.URLField()
