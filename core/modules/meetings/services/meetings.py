"""Scheduling, joining and recording meetings. Every check runs on the server."""

import logging
import os
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from core.models.user import User
from core.modules.kanban.services.sector import Role, SectorService
from core.modules.meetings.models.meeting import (
    Meeting,
    MeetingConsent,
    MeetingRecording,
)
from core.modules.meetings.response_messages import (
    MSG_MEETING_CONSENT_REQUIRED,
    MSG_MEETING_ENDS_BEFORE_START,
    MSG_MEETING_NOT_INVITED,
    MSG_MEETING_ORGANIZER_REQUIRED,
    MSG_MEETING_PARTICIPANT_INVALID,
    MSG_RECORDING_ALREADY_ACTIVE,
    MSG_RECORDING_NOT_ACTIVE,
    MSG_RECORDING_NOT_READY,
    MSG_RECORDING_ROOM_EMPTY,
)
from core.modules.meetings.services import livekit, storage

logger = logging.getLogger(__name__)
Status = MeetingRecording.Status
DEFAULT_RETENTION_DAYS = 90


def retention_days() -> int:
    try:
        return max(1, int(os.getenv("MEETING_RECORDING_RETENTION_DAYS", "")))
    except ValueError:
        return DEFAULT_RETENTION_DAYS


class Access:
    """What the caller may do with one meeting."""

    def __init__(self, meeting: Meeting, user: User, role: str):
        self.meeting = meeting
        self.role = role
        self.organizer = meeting.created_by_id == user.id
        self.manage = self.organizer or role == Role.MANAGER
        self.join = self.manage or meeting.participants.filter(id=user.id).exists()


class MeetingService:
    @staticmethod
    def list_for_project(user: User, sector_id, when: str = ""):
        sector, role = SectorService.get_sector(user, sector_id)
        meetings = (
            Meeting.objects.filter(sector=sector)
            .select_related("created_by")
            .prefetch_related("participants")
            .annotate(
                recording_count=Count(
                    "recordings", filter=Q(recordings__status=Status.READY)
                )
            )
        )
        now = timezone.now()
        if when == "upcoming":
            meetings = meetings.filter(ends_at__gte=now)
        elif when == "past":
            meetings = meetings.filter(ends_at__lt=now).order_by("-starts_at")
        return meetings, role

    @staticmethod
    def access(user: User, meeting_id) -> Access:
        meeting = (
            Meeting.objects.select_related("sector", "created_by")
            .filter(id=meeting_id)
            .first()
        )
        if meeting is None:
            raise NotFound()
        _sector, role = SectorService.get_sector(user, meeting.sector_id)
        return Access(meeting, user, role)

    @staticmethod
    def _validate(sector, data: dict, current: Meeting | None = None) -> None:
        starts = data.get("starts_at", current.starts_at if current else None)
        ends = data.get("ends_at", current.ends_at if current else None)
        if starts and ends and ends <= starts:
            raise ValidationError({"ends_at": [MSG_MEETING_ENDS_BEFORE_START]})
        participants = data.get("participants")
        if participants is not None:
            allowed = SectorService.participant_ids(sector)
            if any(person.id not in allowed for person in participants):
                raise ValidationError(
                    {"participants": [MSG_MEETING_PARTICIPANT_INVALID]}
                )

    @staticmethod
    @transaction.atomic
    def create(user: User, sector_id, data: dict) -> Meeting:
        sector, _role = SectorService.get_sector(user, sector_id, Role.EDITOR)
        MeetingService._validate(sector, data)
        participants = data.pop("participants", [])
        meeting = Meeting.objects.create(sector=sector, created_by=user, **data)
        meeting.participants.set({*participants, user})
        return meeting

    @staticmethod
    @transaction.atomic
    def update(user: User, meeting_id, data: dict) -> Meeting:
        access = MeetingService.access(user, meeting_id)
        if not access.manage:
            raise PermissionDenied(MSG_MEETING_ORGANIZER_REQUIRED)
        meeting = access.meeting
        MeetingService._validate(meeting.sector, data, meeting)
        participants = data.pop("participants", None)
        for field, value in data.items():
            setattr(meeting, field, value)
        meeting.save()
        if participants is not None:
            keep = {meeting.created_by} if meeting.created_by else set()
            meeting.participants.set({*participants, *keep})
        return meeting

    @staticmethod
    def delete(user: User, meeting_id) -> None:
        access = MeetingService.access(user, meeting_id)
        if not access.manage:
            raise PermissionDenied(MSG_MEETING_ORGANIZER_REQUIRED)
        for recording in access.meeting.recordings.all():
            RecordingService.remove(recording)
        access.meeting.delete()

    @staticmethod
    def join(user: User, meeting_id, consent: bool) -> dict:
        """Room token for invited people only, after the recording notice."""
        access = MeetingService.access(user, meeting_id)
        if not access.join:
            raise PermissionDenied(MSG_MEETING_NOT_INVITED)
        if not consent:
            raise ValidationError({"consent": [MSG_MEETING_CONSENT_REQUIRED]})
        meeting = access.meeting
        cfg = livekit.livekit_settings()
        token = livekit.room_token(
            str(user.id), user.get_full_name() or user.email, meeting.room_name
        )
        MeetingConsent.objects.update_or_create(
            meeting=meeting, user=user, defaults={"consented_at": timezone.now()}
        )
        return {
            "url": cfg.url,
            "token": token,
            "room": meeting.room_name,
            "identity": str(user.id),
            "can_record": access.manage,
            "recording": RecordingService.active(meeting) is not None,
        }


class RecordingService:
    @staticmethod
    def active(meeting: Meeting) -> MeetingRecording | None:
        return meeting.recordings.filter(
            status__in=(Status.STARTING, Status.RECORDING)
        ).first()

    @staticmethod
    def _room_participants(meeting: Meeting) -> list[dict]:
        data = livekit.twirp(
            "RoomService",
            "ListParticipants",
            {"room": meeting.room_name},
            {"roomAdmin": True, "room": meeting.room_name},
        )
        return [
            {"identity": p.get("identity", ""), "name": p.get("name", "")}
            for p in data.get("participants", [])
            # the recorder joins as a hidden participant
            if p.get("kind") not in ("EGRESS", 2)
        ]

    @staticmethod
    def start(user: User, meeting_id) -> MeetingRecording:
        access = MeetingService.access(user, meeting_id)
        if not access.manage:
            raise PermissionDenied(MSG_MEETING_ORGANIZER_REQUIRED)
        meeting = access.meeting
        if RecordingService.active(meeting):
            raise ValidationError({"detail": MSG_RECORDING_ALREADY_ACTIVE})
        upload = storage.egress_upload()
        people = RecordingService._room_participants(meeting)
        if not people:
            raise ValidationError({"detail": MSG_RECORDING_ROOM_EMPTY})
        stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
        key = f"meetings/{meeting.sector_id}/{meeting.id}/{stamp}.mp4"
        info = livekit.twirp(
            "Egress",
            "StartRoomCompositeEgress",
            {
                "room_name": meeting.room_name,
                "layout": "grid",
                "file_outputs": [{"file_type": "MP4", "filepath": key, "s3": upload}],
            },
            {"roomRecord": True},
        )
        return MeetingRecording.objects.create(
            meeting=meeting,
            egress_id=info.get("egress_id") or info["egressId"],
            started_by=user,
            file_key=key,
            participants=people,
        )

    @staticmethod
    def _recording(meeting: Meeting, recording_id) -> MeetingRecording:
        recording = meeting.recordings.filter(id=recording_id).first()
        if recording is None:
            raise NotFound()
        return recording

    @staticmethod
    def stop(user: User, meeting_id, recording_id) -> MeetingRecording:
        access = MeetingService.access(user, meeting_id)
        if not access.manage:
            raise PermissionDenied(MSG_MEETING_ORGANIZER_REQUIRED)
        recording = RecordingService._recording(access.meeting, recording_id)
        if not recording.active:
            raise ValidationError({"detail": MSG_RECORDING_NOT_ACTIVE})
        livekit.twirp(
            "Egress",
            "StopEgress",
            {"egress_id": recording.egress_id},
            {"roomRecord": True},
        )
        recording.status = Status.PROCESSING
        recording.save(update_fields=["status"])
        return recording

    @staticmethod
    def list(user: User, meeting_id):
        access = MeetingService.access(user, meeting_id)
        if not access.join:
            raise PermissionDenied(MSG_MEETING_NOT_INVITED)
        return access, access.meeting.recordings.select_related("started_by", "insight")

    @staticmethod
    def links(access: Access, recording: MeetingRecording) -> dict:
        """Signed URLs: everyone invited may watch; only managers may download."""
        if recording.status != Status.READY:
            return {"play_url": None, "download_url": None}
        name = f"{access.meeting.title[:60]} {recording.started_at:%Y-%m-%d %H-%M}.mp4"
        return {
            "play_url": storage.presign(recording.file_key),
            "download_url": (
                storage.download_url(recording.file_key, name)
                if access.manage
                else None
            ),
        }

    @staticmethod
    def download(user: User, meeting_id, recording_id) -> str:
        access = MeetingService.access(user, meeting_id)
        if not access.manage:
            raise PermissionDenied(MSG_MEETING_ORGANIZER_REQUIRED)
        recording = RecordingService._recording(access.meeting, recording_id)
        if recording.status != Status.READY:
            raise ValidationError({"detail": MSG_RECORDING_NOT_READY})
        return RecordingService.links(access, recording)["download_url"]

    @staticmethod
    def remove(recording: MeetingRecording) -> None:
        """Stops a running recording, deletes the file, then the row."""
        if recording.active:
            try:
                livekit.twirp(
                    "Egress",
                    "StopEgress",
                    {"egress_id": recording.egress_id},
                    {"roomRecord": True},
                )
            except livekit.MeetingError:
                logger.warning("could not stop egress %s", recording.egress_id)
        if recording.file_key and recording.status == Status.READY:
            storage.delete_object(recording.file_key)
        recording.delete()

    @staticmethod
    def delete(user: User, meeting_id, recording_id) -> None:
        access = MeetingService.access(user, meeting_id)
        if not access.manage:
            raise PermissionDenied(MSG_MEETING_ORGANIZER_REQUIRED)
        RecordingService.remove(
            RecordingService._recording(access.meeting, recording_id)
        )

    @staticmethod
    def purge_expired(now=None) -> int:
        """Retention policy: ready recordings older than the limit are deleted."""
        limit = (now or timezone.now()) - timedelta(days=retention_days())
        expired = MeetingRecording.objects.filter(
            Q(status=Status.READY) | Q(status=Status.FAILED), started_at__lt=limit
        )
        count = 0
        for recording in expired:
            RecordingService.remove(recording)
            count += 1
        return count


# Egress statuses, by name (JSON) or enum number
EGRESS_ACTIVE = {"EGRESS_STARTING", "EGRESS_ACTIVE", 0, 1}
EGRESS_ENDING = {"EGRESS_ENDING", 2}
EGRESS_DONE = {"EGRESS_COMPLETE", 3}
EGRESS_LIMIT = {"EGRESS_LIMIT_REACHED", 6}


def _duration(file: dict) -> int:
    # LiveKit reports nanoseconds; JSON int64 values may arrive as strings
    return round(int(file.get("duration") or 0) / 1_000_000_000)


class LiveKitWebhookService:
    @staticmethod
    def handle(event: dict) -> None:
        kind = event.get("event", "")
        if kind.startswith("egress_"):
            LiveKitWebhookService._egress(event.get("egressInfo") or {})
        elif kind == "participant_joined":
            LiveKitWebhookService._joined(
                (event.get("room") or {}).get("name", ""),
                event.get("participant") or {},
            )

    @staticmethod
    @transaction.atomic
    def _egress(info: dict) -> None:
        egress_id = info.get("egressId") or info.get("egress_id")
        recording = (
            MeetingRecording.objects.select_for_update()
            .filter(egress_id=egress_id)
            .first()
        )
        if recording is None:
            return
        state = info.get("status")
        became_ready = False
        if state in EGRESS_ACTIVE:
            if recording.status == Status.STARTING:
                recording.status = Status.RECORDING
        elif state in EGRESS_ENDING:
            recording.status = Status.PROCESSING
        elif state in EGRESS_DONE or state in EGRESS_LIMIT:
            files = info.get("fileResults") or info.get("file_results") or []
            file = files[0] if files else info.get("file") or {}
            recording.status = Status.READY
            recording.duration_seconds = _duration(file)
            recording.size_bytes = int(file.get("size") or 0)
            recording.ended_at = timezone.now()
            if state in EGRESS_LIMIT:
                recording.error = "limit_reached"
            became_ready = True
        else:  # failed or aborted
            recording.status = Status.FAILED
            recording.error = info.get("error") or "egress_failed"
            recording.ended_at = timezone.now()
        recording.save()
        if became_ready:
            from core.modules.meetings.services.insights import InsightPipeline

            InsightPipeline.on_recording_ready(recording)

    @staticmethod
    @transaction.atomic
    def _joined(room: str, participant: dict) -> None:
        if not room.startswith("meeting-") or participant.get("kind") in ("EGRESS", 2):
            return
        try:
            meeting_id = uuid.UUID(room.removeprefix("meeting-"))
        except ValueError:
            return
        recording = (
            MeetingRecording.objects.select_for_update()
            .filter(
                meeting_id=meeting_id,
                status__in=(Status.STARTING, Status.RECORDING),
            )
            .first()
        )
        if recording is None:
            return
        identity = participant.get("identity", "")
        if all(p["identity"] != identity for p in recording.participants):
            recording.participants = [
                *recording.participants,
                {"identity": identity, "name": participant.get("name", "")},
            ]
            recording.save(update_fields=["participants"])
