import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.modules.kanban.models.task import Task
from core.modules.meetings.models.meeting import MeetingRecording


class MeetingInsight(models.Model):
    """Transcript and AI summary of one recording, made by the worker."""

    class Status(models.TextChoices):
        PENDING = "pending", _("pending")
        TRANSCRIBING = "transcribing", _("transcribing")
        SUMMARIZING = "summarizing", _("summarizing")
        DONE = "done", _("done")
        FAILED = "failed", _("failed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recording = models.OneToOneField(
        MeetingRecording, on_delete=models.CASCADE, related_name="insight"
    )
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.PENDING
    )
    # file already transcribed; the same file is never processed twice
    source_key = models.CharField(_("source key"), max_length=500, blank=True)
    language = models.CharField(_("language"), max_length=10, blank=True)
    audio_seconds = models.FloatField(_("audio seconds"), default=0)
    # [{"id": 0, "start": 1.2, "end": 4.0, "text": "..."}]
    segments = models.JSONField(_("segments"), default=list, blank=True)
    summary = models.JSONField(_("summary"), null=True, blank=True)
    transcribe_model = models.CharField(_("transcription model"), max_length=100)
    summary_model = models.CharField(_("summary model"), max_length=100, blank=True)
    transcribe_seconds = models.FloatField(_("transcription time"), default=0)
    summary_seconds = models.FloatField(_("summary time"), default=0)
    attempts = models.PositiveIntegerField(_("attempts"), default=0)
    error = models.TextField(_("error"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    finished_at = models.DateTimeField(_("finished at"), null=True, blank=True)

    class Meta:
        verbose_name = _("meeting insight")
        verbose_name_plural = _("meeting insights")

    def __str__(self):
        return f"{self.recording_id} ({self.status})"

    @property
    def running(self) -> bool:
        return self.status in (self.Status.TRANSCRIBING, self.Status.SUMMARIZING)


class MeetingActionTask(models.Model):
    """Task created from a suggested action; one per action, never twice."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    insight = models.ForeignKey(
        MeetingInsight, on_delete=models.CASCADE, related_name="action_tasks"
    )
    action_index = models.PositiveIntegerField(_("action index"))
    task = models.ForeignKey(
        Task, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("meeting action task")
        verbose_name_plural = _("meeting action tasks")
        constraints = [
            models.UniqueConstraint(
                fields=["insight", "action_index"], name="unique_meeting_action_task"
            )
        ]

    def __str__(self):
        return f"{self.insight_id}#{self.action_index}"
