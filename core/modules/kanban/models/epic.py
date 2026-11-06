import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.modules.kanban.models.sector import Sector


class Epic(models.Model):
    """A larger piece of work of a sector (module/epic) grouping tasks by goal."""

    class State(models.TextChoices):
        PLANNED = "planned", _("planned")
        IN_PROGRESS = "in_progress", _("in progress")
        PAUSED = "paused", _("paused")
        DONE = "done", _("done")
        CANCELLED = "cancelled", _("cancelled")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        related_name="epics",
        verbose_name=_("sector"),
    )
    name = models.CharField(_("name"), max_length=120)
    description = models.TextField(_("description"), blank=True)
    state = models.CharField(
        _("state"), max_length=12, choices=State, default=State.PLANNED
    )
    lead = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("lead"),
    )
    color = models.CharField(_("color"), max_length=7, blank=True)
    start_date = models.DateField(_("start date"), null=True, blank=True)
    target_date = models.DateField(_("target date"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("epic")
        verbose_name_plural = _("epics")
        ordering = ["created_at"]

    def __str__(self) -> str:
        return self.name
