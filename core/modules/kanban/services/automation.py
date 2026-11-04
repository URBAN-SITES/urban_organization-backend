"""Automation rules: "when X happens in this project, do Y".

Rules run once per event, in creation order, and their changes never fire other
rules (no chains, so no loops). The person whose action fired the rule is the
author of the change in the task history, with the rule name noted.
"""

import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import F, Max
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from core.models.user import User
from core.modules.kanban.models.activity import TaskActivity
from core.modules.kanban.models.automation import AutomationRule, AutomationRun
from core.modules.kanban.models.label import Label
from core.modules.kanban.models.task import Status, Task
from core.modules.kanban.response_messages import (
    MSG_AUTOMATION_LIMIT,
    MSG_AUTOMATION_NOTICE,
    MSG_AUTOMATION_VALUE_INVALID,
)
from core.modules.kanban.services.activity import ActivityService, snapshot
from core.modules.kanban.services.sector import Role, SectorService
from core.modules.notifications.services.notification import NotificationService

Trigger = AutomationRule.Trigger
Action = AutomationRule.Action
PRIORITIES = {choice for choice, _label in Task.Priority.choices}
MAX_RULES = 50


def _uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


class AutomationService:
    # ── CRUD (manager) ──────────────────────────────────────────────────────
    @staticmethod
    def list_for(user: User, sector_id):
        sector, _role = SectorService.get_sector(user, sector_id, Role.EDITOR)
        return AutomationRule.objects.filter(sector=sector)

    @staticmethod
    def create(user: User, sector_id, data: dict) -> AutomationRule:
        sector, _role = SectorService.get_sector(user, sector_id, Role.MANAGER)
        if AutomationRule.objects.filter(sector=sector).count() >= MAX_RULES:
            raise ValidationError(MSG_AUTOMATION_LIMIT)
        AutomationService._check(sector, data)
        return AutomationRule.objects.create(sector=sector, created_by=user, **data)

    @staticmethod
    def update(user: User, rule_id, data: dict) -> AutomationRule:
        rule = AutomationService._get(user, rule_id)
        for field, value in data.items():
            setattr(rule, field, value)
        AutomationService._check(
            rule.sector,
            {
                "trigger": rule.trigger,
                "trigger_value": rule.trigger_value,
                "action": rule.action,
                "action_value": rule.action_value,
            },
        )
        rule.save()
        return rule

    @staticmethod
    def delete(user: User, rule_id) -> None:
        AutomationService._get(user, rule_id).delete()

    @staticmethod
    def _get(user: User, rule_id) -> AutomationRule:
        rule = (
            AutomationRule.objects.select_related("sector").filter(id=rule_id).first()
        )
        if rule is None:
            raise NotFound()
        SectorService.get_sector(user, rule.sector_id, Role.MANAGER)
        return rule

    @staticmethod
    def _check(sector, data: dict) -> None:
        """The values must point at things of this project."""
        trigger, value = data["trigger"], data.get("trigger_value", "")
        action, target = data["action"], data.get("action_value", "")

        def bad(field: str):
            raise ValidationError({field: [MSG_AUTOMATION_VALUE_INVALID]})

        if trigger == Trigger.MOVED and value:
            if not Status.objects.filter(sector=sector, id=_uuid(value)).exists():
                bad("trigger_value")
        elif trigger == Trigger.PRIORITY and value not in PRIORITIES:
            bad("trigger_value")
        elif trigger in (Trigger.CREATED, Trigger.OVERDUE, Trigger.ASSIGNED) and value:
            bad("trigger_value")

        if action in (Action.ASSIGN, Action.NOTIFY):
            person = _uuid(target)
            if person is None or person not in SectorService.participant_ids(sector):
                bad("action_value")
        elif action == Action.PRIORITY and target not in PRIORITIES:
            bad("action_value")
        elif action == Action.LABEL:
            if not Label.objects.filter(sector=sector, id=_uuid(target)).exists():
                bad("action_value")
        elif action == Action.MOVE:
            if not Status.objects.filter(sector=sector, id=_uuid(target)).exists():
                bad("action_value")
        elif action == Action.DUE:
            if not (target.isdigit() and 0 <= int(target) <= 365):
                bad("action_value")
        elif action == Action.ARCHIVE and target:
            bad("action_value")
        # a rule that undoes its own trigger would only add noise to the history
        if trigger == Trigger.MOVED and action == Action.MOVE and value == target:
            bad("action_value")
        if trigger == Trigger.PRIORITY and action == Action.PRIORITY:
            bad("action")

    # ── execution ───────────────────────────────────────────────────────────
    @staticmethod
    def run(task: Task, trigger: str, actor: User | None, value: str = "") -> None:
        """Applies the active rules of the task's project for this event."""
        rules = AutomationRule.objects.filter(
            sector_id=task.sector_id, trigger=trigger, is_active=True
        )
        for rule in rules:
            if rule.trigger_value and rule.trigger_value != str(value):
                continue
            AutomationService._apply(rule, task, actor)

    @staticmethod
    def run_overdue(today=None) -> int:
        """Beat job: OVERDUE rules run once for each task whose due date passed."""
        today = today or timezone.localdate()
        count = 0
        for rule in AutomationRule.objects.filter(
            trigger=Trigger.OVERDUE, is_active=True
        ).select_related("created_by"):
            tasks = (
                Task.objects.filter(
                    sector_id=rule.sector_id,
                    is_active=True,
                    archived_at__isnull=True,
                    completed_at__isnull=True,
                    due_date__lt=today,
                )
                .exclude(automation_runs__rule=rule)
                .select_related("sector", "status")[:500]
            )
            for task in tasks:
                try:
                    with transaction.atomic():
                        AutomationRun.objects.create(rule=rule, task=task)
                        AutomationService._apply(rule, task, rule.created_by)
                except IntegrityError:
                    continue
                count += 1
        return count

    @staticmethod
    def _apply(rule: AutomationRule, task: Task, actor: User | None) -> None:
        before, before_display = snapshot(task), ActivityService.display(task)
        target = rule.action_value
        changed = False
        if rule.action == Action.ASSIGN:
            person = User.objects.filter(id=_uuid(target), is_active=True).first()
            if person and SectorService.effective_role(person, task.sector):
                task.assignee, changed = person, task.assignee_id != person.pk
        elif rule.action == Action.PRIORITY:
            task.priority, changed = target, task.priority != target
        elif rule.action == Action.DUE:
            due = timezone.localdate() + timedelta(days=int(target))
            task.due_date, changed = due, task.due_date != due
        elif rule.action == Action.MOVE:
            status = Status.objects.filter(sector_id=task.sector_id, id=_uuid(target))
            status = status.first()
            if status and status.pk != task.status_id:
                last = Task.objects.filter(status=status, is_active=True).aggregate(
                    last=Max("position")
                )["last"]
                task.position = 0 if last is None else last + 1
                task.status = status
                if status.category == Status.Category.DONE:
                    task.completed_at = task.completed_at or timezone.now()
                else:
                    task.completed_at = None
                changed = True
        elif rule.action == Action.ARCHIVE and not task.archived_at:
            task.archived_at, changed = timezone.now(), True
        elif rule.action == Action.LABEL:
            label = Label.objects.filter(sector_id=task.sector_id, id=_uuid(target))
            label = label.first()
            if label and not task.labels.filter(pk=label.pk).exists():
                task.labels.add(label)
                if actor:
                    ActivityService.record(
                        task,
                        actor,
                        TaskActivity.Action.UPDATED,
                        {
                            "labels": [None, label.name],
                            "automation": [None, rule.name],
                        },
                    )
                changed = True
        elif rule.action == Action.NOTIFY:
            person = User.objects.filter(id=_uuid(target), is_active=True).first()
            if person and SectorService.effective_role(person, task.sector):
                NotificationService.notify(
                    person,
                    str(MSG_AUTOMATION_NOTICE),
                    f"{rule.name}: {task.title}",
                    {
                        "event": "automation.notice",
                        "task_id": str(task.pk),
                        "sector_id": str(task.sector_id),
                        "organization_id": str(task.sector.organization_id),
                    },
                )
                changed = True

        if not changed:
            return
        note = {"automation": [None, rule.name]}
        if rule.action == Action.ARCHIVE:
            task.save(update_fields=["archived_at", "updated_at"])
            if actor:
                ActivityService.record(
                    task,
                    actor,
                    TaskActivity.Action.UPDATED,
                    {"archived": [None, "sim"], **note},
                )
        elif rule.action not in (Action.LABEL, Action.NOTIFY):
            task.save()
            if actor:
                ActivityService.record_changes(
                    task, actor, before, before_display, extra=note
                )
        AutomationRule.objects.filter(pk=rule.pk).update(
            run_count=F("run_count") + 1, last_run_at=timezone.now()
        )
