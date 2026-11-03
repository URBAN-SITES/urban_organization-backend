import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from core.modules.kanban.models.sector import Sector


class Cycle(models.Model):
    """A time box (sprint) of a sector; tasks join it through Task.cycle."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        related_name="cycles",
        verbose_name=_("sector"),
    )
    name = models.CharField(_("name"), max_length=100)
    description = models.TextField(_("description"), blank=True)
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(_("end date"))
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("cycle")
        verbose_name_plural = _("cycles")
        ordering = ["start_date", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="cycle_end_after_start",
            )
        ]

    def __str__(self) -> str:
        return self.name
