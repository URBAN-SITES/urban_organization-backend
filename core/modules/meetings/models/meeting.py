import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.modules.kanban.models.sector import Sector


class Meeting(models.Model):
    """A scheduled call of a project. The LiveKit room is created on the first join."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        related_name="meetings",
        verbose_name=_("sector"),
    )
    title = models.CharField(_("title"), max_length=200)
    description = models.TextField(_("description"), blank=True)
    starts_at = models.DateTimeField(_("starts at"))
    ends_at = models.DateTimeField(_("ends at"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name=_("created by"),
    )
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="meetings",
        blank=True,
        verbose_name=_("participants"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("meeting")
        verbose_name_plural = _("meetings")
        ordering = ["starts_at"]
        indexes = [models.Index(fields=["sector", "starts_at"])]

    def __str__(self):
        return self.title

    @property
    def room_name(self) -> str:
        return f"meeting-{self.id}"


class MeetingConsent(models.Model):
    """Who acknowledged the recording notice before joining, and when (last time)."""

    meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="consents"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    consented_at = models.DateTimeField(_("consented at"))

    class Meta:
        verbose_name = _("meeting consent")
        verbose_name_plural = _("meeting consents")
        constraints = [
            models.UniqueConstraint(
                fields=["meeting", "user"], name="unique_meeting_consent"
            )
        ]

    def __str__(self):
        return f"{self.user_id} @ {self.meeting_id}"


class MeetingRecording(models.Model):
    """One server-side recording (LiveKit Egress) stored in the recordings bucket."""

    class Status(models.TextChoices):
        STARTING = "starting", _("starting")
        RECORDING = "recording", _("recording")
        PROCESSING = "processing", _("processing")
        READY = "ready", _("ready")
        FAILED = "failed", _("failed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="recordings"
    )
    egress_id = models.CharField(_("egress id"), max_length=100, unique=True)
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.STARTING
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    started_at = models.DateTimeField(_("started at"), auto_now_add=True)
    ended_at = models.DateTimeField(_("ended at"), null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(_("duration"), default=0)
    size_bytes = models.BigIntegerField(_("size"), default=0)
    file_key = models.CharField(_("file key"), max_length=500)
    # names seen in the room while recording: [{"identity", "name"}]
    participants = models.JSONField(_("participants"), default=list, blank=True)
    error = models.TextField(_("error"), blank=True)

    class Meta:
        verbose_name = _("meeting recording")
        verbose_name_plural = _("meeting recordings")
        ordering = ["-started_at"]

    def __str__(self):
        return self.file_key

    @property
    def active(self) -> bool:
        return self.status in (self.Status.STARTING, self.Status.RECORDING)
