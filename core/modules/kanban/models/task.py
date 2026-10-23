import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models.base import BaseModel
from core.modules.kanban.models.sector import Sector


# [P1] `category` gives a free-named column its meaning (done = completed).
class Status(models.Model):
    class Category(models.TextChoices):
        TODO = "todo", _("to do")
        IN_PROGRESS = "in_progress", _("in progress")
        DONE = "done", _("done")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        related_name="statuses",
        verbose_name=_("sector"),
    )
    name = models.CharField(_("name"), max_length=100)
    color = models.CharField(_("color"), max_length=20, blank=True)
    category = models.CharField(_("category"), max_length=12, choices=Category)
    position = models.PositiveIntegerField(_("position"))
    wip_limit = models.PositiveIntegerField(_("WIP limit"), null=True, blank=True)

    class Meta:
        verbose_name = _("status")
        verbose_name_plural = _("statuses")
        ordering = ["sector", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["sector", "name"], name="unique_status_name_per_sector"
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.sector})"


class TaskQuerySet(models.QuerySet):
    def overdue(self):
        return self.filter(due_date__lt=timezone.localdate(), completed_at__isnull=True)


# [P1] `owner` (from BaseModel) is the DBML `created_by`.
class Task(BaseModel):
    class Priority(models.TextChoices):
        LOW = "low", _("low")
        MEDIUM = "medium", _("medium")
        HIGH = "high", _("high")
        URGENT = "urgent", _("urgent")

    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        related_name="tasks",
        verbose_name=_("sector"),
    )
    status = models.ForeignKey(
        Status,
        on_delete=models.PROTECT,
        related_name="tasks",
        verbose_name=_("status"),
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subtasks",
        verbose_name=_("parent task"),
    )
    title = models.CharField(_("title"), max_length=255)
    description = models.TextField(_("description"), blank=True)
    priority = models.CharField(
        _("priority"), max_length=10, choices=Priority, default=Priority.MEDIUM
    )
    due_date = models.DateField(_("due date"), null=True, blank=True, db_index=True)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tasks",
        verbose_name=_("assignee"),
    )
    position = models.PositiveIntegerField(_("position"), default=0)

    objects = TaskQuerySet.as_manager()

    class Meta(BaseModel.Meta):
        verbose_name = _("task")
        verbose_name_plural = _("tasks")
        ordering = ["position", "-created_at"]
        indexes = [models.Index(fields=["sector", "status"])]

    def __str__(self) -> str:
        return self.title

    def clean(self):
        # The DBML uses a composite FK (status_id, sector_id); Django has none.
        if self.status_id and self.status.sector_id != self.sector_id:
            raise ValidationError({"status": _("Status belongs to another sector.")})


# [P1]
class ChecklistItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="checklist_items",
        verbose_name=_("task"),
    )
    content = models.CharField(_("content"), max_length=255)
    is_done = models.BooleanField(_("done"), default=False)
    position = models.PositiveIntegerField(_("position"), default=0)

    class Meta:
        verbose_name = _("checklist item")
        verbose_name_plural = _("checklist items")
        ordering = ["position"]

    def __str__(self) -> str:
        return self.content


# [P1]
class Comment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name=_("task"),
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="task_comments",
        verbose_name=_("author"),
    )
    content = models.TextField(_("content"))
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("comment")
        verbose_name_plural = _("comments")
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.author}: {self.content[:30]}"
