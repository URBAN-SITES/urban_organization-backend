import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.modules.kanban.models.task import Task


class TimeEntry(models.Model):
    """Time spent on a task: a running timer (no end yet) or a finished/manual entry."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="time_entries",
        verbose_name=_("task"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="time_entries",
        verbose_name=_("user"),
    )
    started_at = models.DateTimeField(_("started at"))
    ended_at = models.DateTimeField(_("ended at"), null=True, blank=True)
    minutes = models.PositiveIntegerField(_("minutes"), default=0)
    note = models.CharField(_("note"), max_length=255, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("time entry")
        verbose_name_plural = _("time entries")
        ordering = ["-started_at"]
        constraints = [
            # one running timer per person
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(ended_at__isnull=True),
                name="one_running_timer_per_user",
            )
        ]

    def __str__(self) -> str:
        return f"{self.task} ({self.minutes} min)"
