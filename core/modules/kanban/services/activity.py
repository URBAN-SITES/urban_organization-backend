from core.models.user import User
from core.modules.kanban.models.activity import TaskActivity
from core.modules.kanban.models.task import Task

Action = TaskActivity.Action
# fields shown in the history; description only says "changed" (it can be long)
TRACKED = (
    "title",
    "description",
    "priority",
    "start_date",
    "due_date",
    "assignee",
    "status",
    "cycle",
    "epic",
    "estimate",
)


def _display(task: Task, field: str):
    if field == "assignee":
        return task.assignee.name if task.assignee_id else None
    if field == "status":
        return task.status.name if task.status_id else None
    if field == "cycle":
        return task.cycle.name if task.cycle_id else None
    if field == "epic":
        return task.epic.name if task.epic_id else None
    if field == "description":
        return None
    value = getattr(task, field)
    return value.isoformat() if hasattr(value, "isoformat") else value


def snapshot(task: Task) -> dict:
    """Comparable values of the tracked fields (ids for relations)."""
    return {
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "start_date": task.start_date,
        "due_date": task.due_date,
        "assignee": task.assignee_id,
        "status": task.status_id,
        "cycle": task.cycle_id,
        "epic": task.epic_id,
        "estimate": task.estimate,
    }


class ActivityService:
    @staticmethod
    def record(task: Task, actor: User, action: str, changes: dict | None = None):
        return TaskActivity.objects.create(
            task=task, actor=actor, action=action, changes=changes or {}
        )

    @staticmethod
    def record_changes(task: Task, actor: User, before: dict, before_display: dict):
        """Logs an update with only the fields that really changed."""
        after = snapshot(task)
        changes = {
            field: [before_display[field], _display(task, field)]
            for field in TRACKED
            if before[field] != after[field]
        }
        if not changes:
            return None
        action = Action.MOVED if set(changes) == {"status"} else Action.UPDATED
        return ActivityService.record(task, actor, action, changes)

    @staticmethod
    def display(task: Task) -> dict:
        return {field: _display(task, field) for field in TRACKED}

    @staticmethod
    def for_task(task: Task):
        return TaskActivity.objects.filter(task=task).select_related("actor")

    @staticmethod
    def recent(sectors, limit: int = 10):
        return (
            TaskActivity.objects.filter(task__sector__in=sectors, task__is_active=True)
            .select_related("actor", "task", "task__sector")
            .order_by("-created_at")[:limit]
        )
