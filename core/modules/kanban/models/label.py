import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from core.modules.kanban.models.sector import Sector


class Label(models.Model):
    """A colored tag of a sector, applied to its tasks."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        related_name="labels",
        verbose_name=_("sector"),
    )
    name = models.CharField(_("name"), max_length=50)
    color = models.CharField(_("color"), max_length=7, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("label")
        verbose_name_plural = _("labels")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["sector", "name"], name="unique_label_name_per_sector"
            )
        ]

    def __str__(self) -> str:
        return self.name
