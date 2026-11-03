import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.modules.kanban.models.sector import Sector


class TaskTemplate(models.Model):
    """A ready-made task of a project: fields and checklist copied on creation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        related_name="task_templates",
        verbose_name=_("sector"),
    )
    name = models.CharField(_("name"), max_length=100)
    title = models.CharField(_("title"), max_length=255, blank=True)
    description = models.TextField(_("description"), blank=True)
    priority = models.CharField(_("priority"), max_length=10, default="medium")
    estimate = models.PositiveSmallIntegerField(_("estimate"), null=True, blank=True)
    label_ids = models.JSONField(_("labels"), default=list, blank=True)
    checklist = models.JSONField(_("checklist"), default=list, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name=_("created by"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("task template")
        verbose_name_plural = _("task templates")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
