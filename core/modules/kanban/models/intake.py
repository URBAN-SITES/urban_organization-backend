import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.modules.kanban.models.sector import Sector
from core.modules.kanban.models.task import Task


class IntakeRequest(models.Model):
    """A request sent to a sector; editors accept it (it becomes a task) or decline."""

    class State(models.TextChoices):
        PENDING = "pending", _("pending")
        ACCEPTED = "accepted", _("accepted")
        DECLINED = "declined", _("declined")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        related_name="intake_requests",
        verbose_name=_("sector"),
    )
    title = models.CharField(_("title"), max_length=255)
    description = models.TextField(_("description"), blank=True)
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name=_("requester"),
    )
    state = models.CharField(
        _("state"), max_length=10, choices=State, default=State.PENDING
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("task"),
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("decided by"),
    )
    decision_note = models.CharField(_("note"), max_length=500, blank=True)
    decided_at = models.DateTimeField(_("decided at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("intake request")
        verbose_name_plural = _("intake requests")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title
