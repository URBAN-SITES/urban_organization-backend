"""Time tracking on tasks and the workload of a project's people."""

from datetime import datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from core.models.user import User
from core.modules.kanban.models.task import Status, Task
from core.modules.kanban.models.time_entry import TimeEntry
from core.modules.kanban.response_messages import MSG_TIME_NOT_YOURS, MSG_TIMER_RUNNING
from core.modules.kanban.services.sector import Role, SectorService
from core.modules.kanban.services.task import TaskService

MAX_ENTRY_MINUTES = 24 * 60


def _minutes(start, end) -> int:
    return max(1, min(MAX_ENTRY_MINUTES, round((end - start).total_seconds() / 60)))


class TimeService:
    @staticmethod
    def running(user: User) -> TimeEntry | None:
        return (
            TimeEntry.objects.filter(user=user, ended_at__isnull=True)
            .select_related("task", "task__sector")
            .first()
        )

    @staticmethod
    @transaction.atomic
    def start(user: User, task_id) -> TimeEntry:
        """Starts a timer on the task; a timer running elsewhere stops first."""
        task, _sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        current = TimeService.running(user)
        if current is not None:
            if current.task_id == task.pk:
                return current
            TimeService._close(current)
        try:
            with transaction.atomic():
                return TimeEntry.objects.create(
                    task=task, user=user, started_at=timezone.now()
                )
        except IntegrityError:
            raise ValidationError(MSG_TIMER_RUNNING) from None

    @staticmethod
    def stop(user: User) -> TimeEntry | None:
        current = TimeService.running(user)
        if current is not None:
            TimeService._close(current)
        return current

    @staticmethod
    def add(user: User, task_id, data: dict) -> TimeEntry:
        """A manual entry (forgot the timer): minutes on a given day."""
        task, _sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        day = data.get("date") or timezone.localdate()
        started = timezone.make_aware(datetime.combine(day, time(9)))
        minutes = data["minutes"]
        return TimeEntry.objects.create(
            task=task,
            user=user,
            started_at=started,
            ended_at=started + timedelta(minutes=minutes),
            minutes=minutes,
            note=data.get("note", ""),
        )

    @staticmethod
    def for_task(user: User, task_id) -> dict:
        task, _sector, _role = TaskService.get_task(user, task_id)
        entries = list(TimeEntry.objects.filter(task=task).select_related("user")[:100])
        now = timezone.now()
        total = sum(
            entry.minutes if entry.ended_at else _minutes(entry.started_at, now)
            for entry in entries
        )
        return {"total_minutes": total, "entries": entries}

    @staticmethod
    def delete(user: User, entry_id) -> None:
        entry = TimeEntry.objects.select_related("task").filter(id=entry_id).first()
        if entry is None:
            raise NotFound()
        TaskService.get_task(user, entry.task_id)
        if entry.user_id != user.pk:
            raise PermissionDenied(MSG_TIME_NOT_YOURS)
        entry.delete()

    @staticmethod
    def _close(entry: TimeEntry) -> None:
        entry.ended_at = timezone.now()
        entry.minutes = _minutes(entry.started_at, entry.ended_at)
        entry.save(update_fields=["ended_at", "minutes"])


class WorkloadService:
    @staticmethod
    def for_sector(user: User, sector_id) -> dict:
        """Per person with access: what is open, late and due this week, points and
        hours logged in the last 7 days. People with nothing at all are left out."""
        sector, _role = SectorService.get_sector(user, sector_id)
        today = timezone.localdate()
        week_end = today + timedelta(days=6)
        open_q = Q(
            assigned_tasks__sector=sector,
            assigned_tasks__is_active=True,
            assigned_tasks__archived_at__isnull=True,
        ) & ~Q(assigned_tasks__status__category=Status.Category.DONE)
        ids = SectorService.participant_ids(sector)
        people = (
            User.objects.filter(pk__in=ids, is_active=True)
            .annotate(
                open=Count("assigned_tasks", filter=open_q, distinct=True),
                overdue=Count(
                    "assigned_tasks",
                    filter=open_q & Q(assigned_tasks__due_date__lt=today),
                    distinct=True,
                ),
                due_week=Count(
                    "assigned_tasks",
                    filter=open_q
                    & Q(assigned_tasks__due_date__range=(today, week_end)),
                    distinct=True,
                ),
            )
            .order_by("name")
        )
        points = dict(
            Task.objects.filter(sector=sector, is_active=True, archived_at__isnull=True)
            .exclude(status__category=Status.Category.DONE)
            .values("assignee_id")
            .annotate(p=Coalesce(Sum("estimate"), 0))
            .values_list("assignee_id", "p")
        )
        since = timezone.now() - timedelta(days=7)
        logged = dict(
            TimeEntry.objects.filter(task__sector=sector, started_at__gte=since)
            .values("user_id")
            .annotate(m=Sum("minutes"))
            .values_list("user_id", "m")
        )
        unassigned = (
            Task.objects.filter(
                sector=sector,
                is_active=True,
                archived_at__isnull=True,
                assignee__isnull=True,
                parent__isnull=True,
            )
            .exclude(status__category=Status.Category.DONE)
            .count()
        )
        rows = [
            {
                "user_id": person.pk,
                "name": person.name or person.email,
                "open": person.open,
                "overdue": person.overdue,
                "due_week": person.due_week,
                "points": points.get(person.pk, 0),
                "minutes_week": logged.get(person.pk, 0),
            }
            for person in people
            if person.open or logged.get(person.pk)
        ]
        return {"people": rows, "unassigned": unassigned}
