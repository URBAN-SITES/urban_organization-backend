from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from core.models.user import User
from core.modules.kanban.models.saved_view import TaskDependency
from core.modules.kanban.models.task import Task
from core.modules.kanban.response_messages import (
    MSG_RELATION_EXISTS,
    MSG_RELATION_INVALID,
    MSG_RELATION_LOOP,
    MSG_RELATION_SELF,
)
from core.modules.kanban.services.activity import Action, ActivityService
from core.modules.kanban.services.sector import Role
from core.modules.kanban.services.task import TaskService

BLOCKED_BY = "blocked_by"
BLOCKING = "blocking"


class RelationService:
    """ "Blocked by" links between tasks of one project (TaskDependency rows:
    `task` waits for `depends_on`)."""

    @staticmethod
    def for_task(user: User, task_id) -> dict:
        task, _sector, _role = TaskService.get_task(user, task_id)
        return RelationService._payload(task)

    @staticmethod
    @transaction.atomic
    def add(user: User, task_id, kind: str, other_id) -> dict:
        task, sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        other = Task.objects.filter(id=other_id, is_active=True).first()
        if other is None or other.sector_id != sector.pk:
            raise ValidationError({"task": [MSG_RELATION_INVALID]})
        if other.pk == task.pk:
            raise ValidationError({"task": [MSG_RELATION_SELF]})
        waiting, blocker = (task, other) if kind == BLOCKED_BY else (other, task)
        if TaskDependency.objects.filter(
            task__in=(task, other), depends_on__in=(task, other)
        ).exists():
            raise ValidationError({"task": [MSG_RELATION_EXISTS]})
        if RelationService._reaches(blocker.pk, waiting.pk):
            raise ValidationError({"task": [MSG_RELATION_LOOP]})
        TaskDependency.objects.create(task=waiting, depends_on=blocker)
        ActivityService.record(
            waiting, user, Action.UPDATED, {"blocked_by": [None, blocker.title]}
        )
        return RelationService._payload(task)

    @staticmethod
    @transaction.atomic
    def remove(user: User, task_id, other_id) -> None:
        task, _sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        links = TaskDependency.objects.filter(
            task_id__in=(task.pk, other_id), depends_on_id__in=(task.pk, other_id)
        ).select_related("task", "depends_on")
        link = links.first()
        if link is None:
            raise NotFound()
        ActivityService.record(
            link.task,
            user,
            Action.UPDATED,
            {"blocked_by": [link.depends_on.title, None]},
        )
        link.delete()

    @staticmethod
    def _reaches(start, target) -> bool:
        """Does `start` (transitively) wait for `target`? Then target -> start loops."""
        seen, frontier = set(), {start}
        while frontier:
            if target in frontier:
                return True
            seen |= frontier
            frontier = (
                set(
                    TaskDependency.objects.filter(task_id__in=frontier).values_list(
                        "depends_on_id", flat=True
                    )
                )
                - seen
            )
        return False

    @staticmethod
    def _payload(task: Task) -> dict:
        fields = ("id", "title", "completed_at", "status__name")

        def rows(queryset):
            return [
                {
                    "id": row["id"],
                    "title": row["title"],
                    "status_name": row["status__name"],
                    "is_done": row["completed_at"] is not None,
                }
                for row in queryset.filter(is_active=True)
                .order_by("title")
                .values(*fields)
            ]

        return {
            BLOCKED_BY: rows(Task.objects.filter(dependents__task=task)),
            BLOCKING: rows(Task.objects.filter(dependencies__depends_on=task)),
        }
