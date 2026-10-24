from django.utils import timezone

from core.modules.kanban.models.task import Status, Task
from core.modules.kanban.services.sector import SectorService

MAX_SPAN_DAYS = 62


def task_state(task: Task, today) -> str:
    """done | late | in_progress | todo, for the colour of a task on the calendar."""
    if task.status.category == Status.Category.DONE:
        return "done"
    if task.due_date < today:
        return "late"
    return task.status.category


class CalendarService:
    @staticmethod
    def items(user, organization_id, start, end) -> list[dict]:
        """Deliveries between two dates, limited to sectors the user can see."""
        sectors = SectorService.list_for(user, organization_id)
        tasks = (
            Task.objects.filter(
                sector__in=sectors, is_active=True, due_date__range=(start, end)
            )
            .select_related("sector", "status", "assignee")
            .order_by("due_date", "title")
        )
        today = timezone.localdate()
        return [
            {
                "id": t.id,
                "title": t.title,
                "due_date": t.due_date,
                "state": task_state(t, today),
                "sector_name": t.sector.name,
                "assignee_name": t.assignee.name if t.assignee else None,
            }
            for t in tasks
        ]
