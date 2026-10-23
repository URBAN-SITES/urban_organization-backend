import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from core.modules.kanban.models.custom_field import CustomField
from core.modules.kanban.models.sector import Sector
from core.modules.kanban.models.task import Task


# [P3] Saved view of a sector (the DBML `views` table; renamed to avoid clashing
# with Django/DRF "views").
class SavedView(models.Model):
    class Layout(models.TextChoices):
        BOARD = "board", _("board")
        TABLE = "table", _("table")
        CALENDAR = "calendar", _("calendar")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        related_name="saved_views",
        verbose_name=_("sector"),
    )
    name = models.CharField(_("name"), max_length=100)
    layout = models.CharField(
        _("layout"), max_length=10, choices=Layout, default=Layout.BOARD
    )
    group_by_field = models.ForeignKey(
        CustomField,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("group by field"),
    )
    filters = models.JSONField(_("filters"), default=dict, blank=True)
    sort = models.JSONField(_("sort"), default=list, blank=True)
    position = models.PositiveIntegerField(_("position"), default=0)

    class Meta:
        verbose_name = _("saved view")
        verbose_name_plural = _("saved views")
        ordering = ["position"]

    def __str__(self) -> str:
        return self.name


# [P3]
class TaskDependency(models.Model):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="dependencies",
        verbose_name=_("task"),
    )
    depends_on = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="dependents",
        verbose_name=_("depends on"),
    )

    class Meta:
        verbose_name = _("task dependency")
        verbose_name_plural = _("task dependencies")
        constraints = [
            models.UniqueConstraint(
                fields=["task", "depends_on"], name="unique_task_dependency"
            ),
            models.CheckConstraint(
                condition=~models.Q(task=models.F("depends_on")),
                name="task_dependency_not_self",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.task} -> {self.depends_on}"
