from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from core.modules.kanban.models.task import Status, Task
from core.modules.kanban.services.sector import SectorService

WEEKS = 6
TODAY_LIMIT = 8


def _week_start(day):
    return day - timedelta(days=day.weekday())


def weekly_done(done, week_start):
    """Completed-task counts for the last WEEKS weeks, oldest first."""
    series = []
    for i in range(WEEKS - 1, -1, -1):
        start = week_start - timedelta(weeks=i)
        count = done.filter(
            completed_at__date__gte=start,
            completed_at__date__lt=start + timedelta(days=7),
        ).count()
        series.append({"week_start": start, "done": count})
    return series


class DashboardService:
    @staticmethod
    def summary(user, organization_id) -> dict:
        """Numbers for the home dashboard, limited to sectors the user can see."""
        sectors = SectorService.list_for(user, organization_id)
        tasks = Task.objects.filter(sector__in=sectors, is_active=True)
        open_tasks = tasks.exclude(status__category=Status.Category.DONE)
        mine = open_tasks.filter(assignee=user)

        today = timezone.localdate()
        week = _week_start(today)
        last_week = week - timedelta(days=7)
        week_end = week + timedelta(days=7)
        done = tasks.filter(completed_at__isnull=False)
        overdue = mine.overdue().order_by("due_date")

        def done_between(start, end):
            return done.filter(
                assignee=user, completed_at__date__gte=start, completed_at__date__lt=end
            ).count()

        first_overdue = overdue.first()
        due_soon = mine.filter(due_date__lte=today + timedelta(days=1)).order_by(
            "due_date"
        )
        return {
            "open_tasks": mine.count(),
            "due_this_week": mine.filter(
                due_date__gte=week, due_date__lt=week_end
            ).count(),
            "done_this_week": done_between(week, week_end),
            "done_last_week": done_between(last_week, week),
            "overdue": overdue.count(),
            "overdue_title": first_overdue.title if first_overdue else None,
            "today": [
                {
                    "id": t.id,
                    "title": t.title,
                    "sector_name": t.sector.name,
                    "due_date": t.due_date,
                    "is_overdue": t.due_date < today,
                }
                for t in due_soon.select_related("sector")[:TODAY_LIMIT]
            ],
            "weekly_done": weekly_done(done, week),
            "open_by_sector": [
                {"sector": row["sector__name"], "open": row["open"]}
                for row in open_tasks.values("sector__name")
                .annotate(open=Count("id"))
                .order_by("-open", "sector__name")
            ],
        }
