from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models.fields import EncryptedTextField
from core.modules.kanban.models.task import Task


# [P2-F] Access to Google APIs (Calendar). Not the same thing as Google login.
class UserIntegration(models.Model):
    class Provider(models.TextChoices):
        GOOGLE_CALENDAR = "google_calendar", _("Google Calendar")

    class Status(models.TextChoices):
        ACTIVE = "active", _("active")
        REVOKED = "revoked", _("revoked")
        ERROR = "error", _("error")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="integrations",
        verbose_name=_("user"),
    )
    provider = models.CharField(_("provider"), max_length=30, choices=Provider)
    scopes = models.JSONField(_("scopes"), default=list, blank=True)
    access_token = EncryptedTextField(_("access token"), blank=True)
    refresh_token = EncryptedTextField(_("refresh token"), blank=True)
    expires_at = models.DateTimeField(_("expires at"), null=True, blank=True)
    calendar_id = models.CharField(_("calendar id"), max_length=255, default="primary")
    sync_enabled = models.BooleanField(_("sync enabled"), default=True)
    status = models.CharField(
        _("status"), max_length=10, choices=Status, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("user integration")
        verbose_name_plural = _("user integrations")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "provider"], name="unique_integration_per_provider"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.provider}"


# [P2-F] Google event created from a task due date. One-way sync only.
class TaskCalendarEvent(models.Model):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="calendar_events",
        verbose_name=_("task"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="task_calendar_events",
        verbose_name=_("user"),
    )
    google_event_id = models.CharField(_("google event id"), max_length=255)
    calendar_id = models.CharField(_("calendar id"), max_length=255, default="primary")
    last_synced_at = models.DateTimeField(_("last synced at"), null=True, blank=True)
    last_error = models.TextField(_("last error"), blank=True)

    class Meta:
        verbose_name = _("task calendar event")
        verbose_name_plural = _("task calendar events")
        constraints = [
            models.UniqueConstraint(
                fields=["task", "user"], name="unique_calendar_event_per_task_user"
            )
        ]

    def __str__(self) -> str:
        return f"{self.task} -> {self.google_event_id}"
