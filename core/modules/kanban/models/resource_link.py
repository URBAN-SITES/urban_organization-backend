import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.modules.kanban.models.sector import Sector
from core.modules.kanban.models.task import Task
from core.modules.organizations.models.organization import Organization


# [P1] Supporting material. Attached to exactly one of organization/sector/task.
class ResourceLink(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="resource_links",
        verbose_name=_("organization"),
    )
    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="resource_links",
        verbose_name=_("sector"),
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="resource_links",
        verbose_name=_("task"),
    )
    title = models.CharField(_("title"), max_length=255, blank=True)
    url = models.URLField(_("url"), max_length=2048)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name=_("created by"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("resource link")
        verbose_name_plural = _("resource links")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                name="resource_link_exactly_one_target",
                condition=(
                    models.Q(
                        organization__isnull=False,
                        sector__isnull=True,
                        task__isnull=True,
                    )
                    | models.Q(
                        organization__isnull=True,
                        sector__isnull=False,
                        task__isnull=True,
                    )
                    | models.Q(
                        organization__isnull=True,
                        sector__isnull=True,
                        task__isnull=False,
                    )
                ),
            )
        ]

    def __str__(self) -> str:
        return self.title or self.url
