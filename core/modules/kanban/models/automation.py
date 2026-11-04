import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.modules.kanban.models.sector import Sector


class AutomationRule(models.Model):
    """When <trigger> happens in a project, do <action> (one pass, no chains)."""

    class Trigger(models.TextChoices):
        CREATED = "created", _("task created")
        MOVED = "moved", _("task moved to a column")
        PRIORITY = "priority", _("priority changed to")
        ASSIGNED = "assigned", _("assignee changed")
        OVERDUE = "overdue", _("due date passed")

    class Action(models.TextChoices):
        ASSIGN = "assign", _("assign to")
        PRIORITY = "priority", _("set priority")
        LABEL = "label", _("add label")
        MOVE = "move", _("move to column")
        DUE = "due", _("set due date in N days")
        NOTIFY = "notify", _("notify a person")
        ARCHIVE = "archive", _("archive the task")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        related_name="automations",
        verbose_name=_("sector"),
    )
    name = models.CharField(_("name"), max_length=120)
    trigger = models.CharField(_("trigger"), max_length=12, choices=Trigger)
    # status id (moved), priority (priority) or blank for "any"
    trigger_value = models.CharField(_("trigger value"), max_length=64, blank=True)
    action = models.CharField(_("action"), max_length=12, choices=Action)
    # user id, priority, label id, status id or number of days, by action
    action_value = models.CharField(_("action value"), max_length=64, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    run_count = models.PositiveIntegerField(_("runs"), default=0)
    last_run_at = models.DateTimeField(_("last run at"), null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name=_("created by"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("automation rule")
        verbose_name_plural = _("automation rules")
        ordering = ["created_at"]
        indexes = [models.Index(fields=["sector", "trigger", "is_active"])]

    def __str__(self) -> str:
        return self.name


class AutomationRun(models.Model):
    """Marks that an OVERDUE rule already ran for a task (it runs once per task)."""

    rule = models.ForeignKey(
        AutomationRule, on_delete=models.CASCADE, related_name="runs"
    )
    task = models.ForeignKey(
        "core.Task", on_delete=models.CASCADE, related_name="automation_runs"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["rule", "task"], name="unique_rule_run")
        ]

    def __str__(self) -> str:
        return f"{self.rule_id} -> {self.task_id}"
