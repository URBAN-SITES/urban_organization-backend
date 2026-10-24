from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from core.models.user import User
from core.modules.kanban.models.sector import Sector
from core.modules.kanban.models.task import Status, Task
from core.modules.kanban.response_messages import (
    MSG_STATUS_INVALID,
    MSG_STATUS_WIP_LIMIT,
    MSG_TASK_ASSIGNED,
    MSG_TASK_ASSIGNEE_INVALID,
    MSG_TASK_PARENT_INVALID,
    MSG_TASK_STATUS_CHANGED,
)
from core.modules.kanban.services.sector import Role, SectorService
from core.modules.notifications.services.notification import NotificationService
from core.modules.user_settings.models.user_settings import UserSettings


class TaskService:
    @staticmethod
    def get_task(user: User, task_id, minimum: str = Role.VIEWER):
        """Returns (task, sector, role); 404 when the task is not visible."""
        task = (
            Task.objects.select_related("sector", "status", "assignee")
            .filter(id=task_id, is_active=True)
            .first()
        )
        if task is None:
            raise NotFound()
        sector, role = SectorService.get_sector(user, task.sector_id, minimum)
        return task, sector, role

    @staticmethod
    def list_for(user: User, sector_id):
        sector, _role = SectorService.get_sector(user, sector_id)
        return Task.objects.filter(sector=sector, is_active=True).select_related(
            "status", "assignee"
        )

    @staticmethod
    @transaction.atomic
    def create(user: User, sector_id, data: dict) -> Task:
        sector, _role = SectorService.get_sector(user, sector_id, Role.EDITOR)
        status = data.pop("status", None) or TaskService._default_status(sector)
        TaskService._check_status(sector, status)
        TaskService._check_assignee(sector, data.get("assignee"))
        parent = data.get("parent")
        if parent and (parent.sector_id != sector.pk or not parent.is_active):
            raise ValidationError(MSG_TASK_PARENT_INVALID)
        TaskService._check_wip(status, task=None)

        last = Task.objects.filter(status=status, is_active=True).aggregate(
            last=Max("position")
        )["last"]
        task = Task(
            sector=sector,
            owner=user,
            status=status,
            position=0 if last is None else last + 1,
            **data,
        )
        TaskService._apply_status(task, status)
        task.save()
        TaskService._notify_assignee(user, task)
        return task

    @staticmethod
    @transaction.atomic
    def update(user: User, task_id, data: dict) -> Task:
        task, sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        old_assignee = task.assignee_id
        if "assignee" in data:
            TaskService._check_assignee(sector, data["assignee"])
        for field, value in data.items():
            setattr(task, field, value)
        task.save()
        if task.assignee_id != old_assignee:
            TaskService._notify_assignee(user, task)
        return task

    @staticmethod
    @transaction.atomic
    def delete(user: User, task_id) -> None:
        task, _sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        task.soft_delete()
        Task.objects.filter(parent=task).update(is_active=False)

    @staticmethod
    @transaction.atomic
    def move(user: User, task_id, status: Status, position: int | None) -> Task:
        """The only place that changes a task's column (keeps completed_at coherent)."""
        task, sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        TaskService._check_status(sector, status)
        status_changed = status.pk != task.status_id
        if status_changed:
            TaskService._check_wip(status, task)
        TaskService._apply_status(task, status)
        task.save()

        siblings = list(
            Task.objects.filter(status=status, is_active=True)
            .exclude(pk=task.pk)
            .order_by("position", "created_at")
        )
        index = len(siblings) if position is None else min(position, len(siblings))
        siblings.insert(index, task)
        for order, sibling in enumerate(siblings):
            sibling.position = order
        Task.objects.bulk_update(siblings, ["position"])
        if status_changed:
            TaskService._notify_assignee(
                user,
                task,
                title=MSG_TASK_STATUS_CHANGED,
                message=f"{task.title}: {status.name}",
                event="task.status_changed",
                preference="app_status",
            )
        return task

    # helpers ------------------------------------------------------------

    @staticmethod
    def _apply_status(task: Task, status: Status) -> None:
        task.status = status
        if status.category == Status.Category.DONE:
            task.completed_at = task.completed_at or timezone.now()
        else:
            task.completed_at = None

    @staticmethod
    def _default_status(sector: Sector) -> Status:
        statuses = sector.statuses.order_by("position")
        return (
            statuses.filter(category=Status.Category.TODO).first() or statuses.first()
        )

    @staticmethod
    def _check_status(sector: Sector, status: Status) -> None:
        if status.sector_id != sector.pk:
            raise ValidationError(MSG_STATUS_INVALID)

    @staticmethod
    def _check_wip(status: Status, task: Task | None) -> None:
        if not status.wip_limit:
            return
        in_column = Task.objects.filter(status=status, is_active=True)
        if task is not None:
            in_column = in_column.exclude(pk=task.pk)
        if in_column.count() >= status.wip_limit:
            raise ValidationError(MSG_STATUS_WIP_LIMIT)

    @staticmethod
    def _check_assignee(sector: Sector, assignee: User | None) -> None:
        if assignee and SectorService.effective_role(assignee, sector) is None:
            raise ValidationError(MSG_TASK_ASSIGNEE_INVALID)

    @staticmethod
    def _notify_assignee(
        actor: User,
        task: Task,
        *,
        title=MSG_TASK_ASSIGNED,
        message: str | None = None,
        event: str = "task.assigned",
        preference: str | None = None,
    ) -> None:
        if not task.assignee_id or task.assignee_id == actor.pk:
            return
        if (
            not task.assignee.is_active
            or SectorService.effective_role(task.assignee, task.sector) is None
        ):
            return
        if (
            preference
            and UserSettings.objects.filter(
                user=task.assignee, **{preference: False}
            ).exists()
        ):
            return
        NotificationService.notify(
            task.assignee,
            str(title),
            task.title if message is None else message,
            {
                "event": event,
                "task_id": str(task.pk),
                "sector_id": str(task.sector_id),
                "organization_id": str(task.sector.organization_id),
            },
        )
