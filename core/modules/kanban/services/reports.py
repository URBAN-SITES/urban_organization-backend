from datetime import timedelta

from django.db.models import Avg, Count, F, Q
from django.utils import timezone

from core.modules.kanban.models.task import Status, Task
from core.modules.kanban.services.dashboard import _week_start, weekly_done
from core.modules.kanban.services.sector import SectorService

PEOPLE_LIMIT = 20


def _avg_days(done):
    avg = done.aggregate(a=Avg(F("completed_at") - F("created_at")))["a"]
    return round(avg.total_seconds() / 86400, 1) if avg else None


def _on_time_pct(done):
    with_due = done.filter(due_date__isnull=False)
    total = with_due.count()
    if not total:
        return None
    on_time = with_due.filter(completed_at__date__lte=F("due_date")).count()
    return round(100 * on_time / total)


class ReportService:
    @staticmethod
    def summary(user, organization_id, days: int) -> dict:
        """Delivery numbers for the last `days` days, limited to sectors the user can see."""
        sectors = SectorService.list_for(user, organization_id)
        tasks = Task.objects.filter(sector__in=sectors, is_active=True)
        now = timezone.now()
        today = timezone.localdate()
        start = now - timedelta(days=days)
        previous_start = start - timedelta(days=days)

        done = tasks.filter(completed_at__isnull=False)
        current = done.filter(completed_at__gte=start, completed_at__lte=now)
        previous = done.filter(completed_at__gte=previous_start, completed_at__lt=start)

        open_tasks = tasks.exclude(status__category=Status.Category.DONE)
        overdue = open_tasks.filter(due_date__lt=today)

        in_window = Q(completed_at__gte=start, completed_at__lte=now)
        people = (
            tasks.filter(assignee__isnull=False)
            .values("assignee_id", "assignee__name")
            .annotate(
                completed=Count("id", filter=in_window),
                with_due=Count("id", filter=in_window & Q(due_date__isnull=False)),
                on_time=Count(
                    "id",
                    filter=in_window & Q(completed_at__date__lte=F("due_date")),
                ),
                open=Count("id", filter=~Q(status__category=Status.Category.DONE)),
                overdue=Count(
                    "id",
                    filter=~Q(status__category=Status.Category.DONE)
                    & Q(due_date__lt=today),
                ),
            )
            .order_by("-completed", "assignee__name")[:PEOPLE_LIMIT]
        )

        return {
            "days": days,
            "completed": current.count(),
            "completed_previous": previous.count(),
            "avg_days_to_complete": _avg_days(current),
            "avg_days_previous": _avg_days(previous),
            "on_time_pct": _on_time_pct(current),
            "on_time_pct_previous": _on_time_pct(previous),
            "open": open_tasks.count(),
            "overdue": overdue.count(),
            "weekly_done": weekly_done(done, _week_start(today)),
            "overdue_by_sector": [
                {"sector": row["sector__name"], "overdue": row["n"]}
                for row in overdue.values("sector__name")
                .annotate(n=Count("id"))
                .order_by("-n", "sector__name")
            ],
            "people": [
                {
                    "user_id": row["assignee_id"],
                    "name": row["assignee__name"],
                    "completed": row["completed"],
                    "on_time_pct": round(100 * row["on_time"] / row["with_due"])
                    if row["with_due"]
                    else None,
                    "open": row["open"],
                    "overdue": row["overdue"],
                }
                for row in people
            ],
        }
