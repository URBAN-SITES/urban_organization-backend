from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Exists, F, Max, OuterRef, Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from core.models.user import User
from core.modules.kanban.models.follow import TaskSubscriber
from core.modules.kanban.models.saved_view import TaskDependency
from core.modules.kanban.models.sector import Sector
from core.modules.kanban.models.task import Status, Task
from core.modules.kanban.response_messages import (
    MSG_CYCLE_INVALID,
    MSG_FOLLOWED_STATUS,
    MSG_STATUS_INVALID,
    MSG_STATUS_WIP_LIMIT,
    MSG_TASK_ASSIGNED,
    MSG_TASK_ASSIGNEE_INVALID,
    MSG_TASK_DATES_INVALID,
    MSG_TASK_PARENT_INVALID,
    MSG_TASK_RESTORE_PARENT,
    MSG_TASK_STATUS_CHANGED,
)
from core.modules.kanban.services.activity import (
    Action,
    ActivityService,
    snapshot,
)
from core.modules.kanban.services.label import LabelService
from core.modules.kanban.services.sector import Role, SectorService
from core.modules.notifications.services.notification import NotificationService
from core.modules.user_settings.models.user_settings import UserSettings


class TaskService:
    @staticmethod
    def get_task(user: User, task_id, minimum: str = Role.VIEWER):
        """Returns (task, sector, role); 404 when the task is not visible."""
        task = (
            Task.objects.select_related(
                "sector", "status", "assignee", "owner", "cycle"
            )
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
        TaskService.auto_archive(sector)
        return (
            Task.objects.filter(sector=sector, is_active=True)
            .select_related("sector", "status", "assignee", "owner")
            .prefetch_related("labels")
            .annotate(
                is_blocked=TaskService.blocked_expression(),
                subtask_total=Count(
                    "subtasks", filter=Q(subtasks__is_active=True), distinct=True
                ),
                subtask_done=Count(
                    "subtasks",
                    filter=Q(
                        subtasks__is_active=True, subtasks__completed_at__isnull=False
                    ),
                    distinct=True,
                ),
                checklist_total=Count("checklist_items", distinct=True),
                checklist_done=Count(
                    "checklist_items",
                    filter=Q(checklist_items__is_done=True),
                    distinct=True,
                ),
                comment_count=Count("comments", distinct=True),
            )
        )

    @staticmethod
    @transaction.atomic
    def create(user: User, sector_id, data: dict) -> Task:
        sector, _role = SectorService.get_sector(user, sector_id, Role.EDITOR)
        label_ids = data.pop("label_ids", None)
        labels = LabelService.resolve(sector, label_ids) if label_ids else []
        status = data.pop("status", None) or TaskService._default_status(sector)
        TaskService._check_status(sector, status)
        TaskService._check_assignee(sector, data.get("assignee"))
        TaskService._check_plan(
            sector, data.get("cycle"), data.get("start_date"), data.get("due_date")
        )
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
            sequence=TaskService._next_number(sector),
            **data,
        )
        TaskService._apply_status(task, status)
        task.save()
        if labels:
            task.labels.set(labels)
        TaskSubscriber.objects.get_or_create(task=task, user=user)
        ActivityService.record(task, user, Action.CREATED)
        TaskService._notify_assignee(user, task)
        return task

    @staticmethod
    @transaction.atomic
    def update(user: User, task_id, data: dict) -> Task:
        task, sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        old_assignee = task.assignee_id
        before, before_display = snapshot(task), ActivityService.display(task)
        label_ids = data.pop("label_ids", None)
        labels = None if label_ids is None else LabelService.resolve(sector, label_ids)
        if "assignee" in data:
            TaskService._check_assignee(sector, data["assignee"])
        for field, value in data.items():
            setattr(task, field, value)
        if {"cycle", "start_date", "due_date"} & data.keys():
            TaskService._check_plan(sector, task.cycle, task.start_date, task.due_date)
        task.save()
        ActivityService.record_changes(task, user, before, before_display)
        if labels is not None:
            TaskService._set_labels(task, user, labels)
        if task.assignee_id != old_assignee:
            TaskService._notify_assignee(user, task)
        return task

    @staticmethod
    @transaction.atomic
    def delete(user: User, task_id) -> None:
        task, _sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        ActivityService.record(task, user, Action.DELETED)
        now = timezone.now()
        task.is_active, task.deleted_at = False, now
        task.save(update_fields=["is_active", "deleted_at", "updated_at"])
        Task.objects.filter(parent=task, is_active=True).update(
            is_active=False, deleted_at=now
        )

    @staticmethod
    def trash(user: User, sector_id):
        """Deleted tasks of the last 30 days (subtasks come back with their parent)."""
        sector, _role = SectorService.get_sector(user, sector_id, Role.EDITOR)
        since = timezone.now() - timedelta(days=30)
        return (
            Task.objects.filter(sector=sector, is_active=False, deleted_at__gte=since)
            .exclude(parent__is_active=False, parent__deleted_at=F("deleted_at"))
            .select_related("sector", "status", "assignee", "owner")
            .order_by("-deleted_at")
        )

    @staticmethod
    @transaction.atomic
    def restore(user: User, task_id) -> Task:
        task = (
            Task.objects.select_related("sector", "parent")
            .filter(id=task_id, is_active=False, deleted_at__isnull=False)
            .first()
        )
        if task is None:
            raise NotFound()
        SectorService.get_sector(user, task.sector_id, Role.EDITOR)
        if task.parent_id and not task.parent.is_active:
            raise ValidationError(MSG_TASK_RESTORE_PARENT)
        Task.objects.filter(parent=task, deleted_at=task.deleted_at).update(
            is_active=True, deleted_at=None
        )
        task.is_active, task.deleted_at = True, None
        task.save(update_fields=["is_active", "deleted_at", "updated_at"])
        ActivityService.record(task, user, Action.UPDATED, {"restored": [None, "sim"]})
        return task

    @staticmethod
    def set_archived(user: User, task_id, archived: bool) -> Task:
        task, _sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        task.archived_at = timezone.now() if archived else None
        task.save(update_fields=["archived_at", "updated_at"])
        return task

    @staticmethod
    def auto_archive(sector: Sector) -> None:
        """Done tasks older than the project's limit leave the board (lazy and on beat)."""
        if not sector.auto_archive_days:
            return
        cutoff = timezone.now() - timedelta(days=sector.auto_archive_days)
        Task.objects.filter(
            sector=sector,
            is_active=True,
            archived_at__isnull=True,
            completed_at__lt=cutoff,
        ).update(archived_at=timezone.now())

    @staticmethod
    @transaction.atomic
    def move(user: User, task_id, status: Status, position: int | None) -> Task:
        """The only place that changes a task's column (keeps completed_at coherent)."""
        task, sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        TaskService._check_status(sector, status)
        status_changed = status.pk != task.status_id
        if status_changed:
            TaskService._check_wip(status, task)
        before, before_display = snapshot(task), ActivityService.display(task)
        TaskService._apply_status(task, status)
        task.save()
        ActivityService.record_changes(task, user, before, before_display)

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
            TaskService.notify_followers(
                user,
                task,
                title=MSG_FOLLOWED_STATUS,
                message=f"{task.title}: {status.name}",
                event="task.status_changed",
                preference="app_status",
                skip={task.assignee_id},
            )
        return task

    @staticmethod
    def blocked_expression():
        """True while some active blocker of the task is still open."""
        return Exists(
            TaskDependency.objects.filter(
                task=OuterRef("pk"),
                depends_on__is_active=True,
                depends_on__completed_at__isnull=True,
            )
        )

    @staticmethod
    def notify_followers(
        actor: User,
        task: Task,
        *,
        title,
        message: str,
        event: str,
        preference: str,
        skip=(),
    ) -> None:
        skipped = {actor.pk, *skip}
        muted = UserSettings.objects.filter(**{preference: False}).values("user_id")
        people = (
            User.objects.filter(followed_tasks__task=task, is_active=True)
            .exclude(pk__in=[pk for pk in skipped if pk])
            .exclude(pk__in=muted)
        )
        allowed = SectorService.participant_ids(task.sector)
        for person in people:
            if person.pk not in allowed:
                continue
            NotificationService.notify(
                person,
                str(title),
                message,
                {
                    "event": event,
                    "task_id": str(task.pk),
                    "sector_id": str(task.sector_id),
                    "organization_id": str(task.sector.organization_id),
                },
            )

    # helpers ------------------------------------------------------------

    @staticmethod
    def _next_number(sector: Sector) -> int:
        locked = Sector.objects.select_for_update().get(pk=sector.pk)
        locked.task_counter += 1
        locked.save(update_fields=["task_counter"])
        sector.task_counter = locked.task_counter
        return locked.task_counter

    @staticmethod
    def _check_plan(sector: Sector, cycle, start_date, due_date) -> None:
        if cycle is not None and cycle.sector_id != sector.pk:
            raise ValidationError({"cycle": [MSG_CYCLE_INVALID]})
        if start_date and due_date and start_date > due_date:
            raise ValidationError({"start_date": [MSG_TASK_DATES_INVALID]})

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
    def _set_labels(task: Task, user: User, labels: list) -> None:
        before = sorted(label.name for label in task.labels.all())
        after = sorted(label.name for label in labels)
        if before == after:
            return
        task.labels.set(labels)
        ActivityService.record(
            task,
            user,
            Action.UPDATED,
            {"labels": [", ".join(before) or None, ", ".join(after) or None]},
        )

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
