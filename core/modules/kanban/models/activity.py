import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.modules.kanban.models.task import Task


class TaskActivity(models.Model):
    """Append-only history of a task: who did what, and which fields changed."""

    class Action(models.TextChoices):
        CREATED = "created", _("created")
        UPDATED = "updated", _("updated")
        MOVED = "moved", _("moved")
        COMMENTED = "commented", _("commented")
        DELETED = "deleted", _("deleted")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="activities",
        verbose_name=_("task"),
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name=_("actor"),
    )
    action = models.CharField(_("action"), max_length=12, choices=Action)
    # {"field": [old, new]} with display values, so the history survives renames
    changes = models.JSONField(_("changes"), default=dict, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("task activity")
        verbose_name_plural = _("task activities")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["task", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.action} {self.task_id}"
