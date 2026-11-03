from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from core.models.user import User
from core.modules.kanban.models.cycle import Cycle
from core.modules.kanban.response_messages import MSG_CYCLE_DATES_INVALID
from core.modules.kanban.services.sector import Role, SectorService

ACTIVE_TASKS = Q(tasks__is_active=True)


def cycle_state(cycle: Cycle) -> str:
    today = timezone.localdate()
    if cycle.end_date < today:
        return "completed"
    if cycle.start_date > today:
        return "upcoming"
    return "current"


class CycleService:
    @staticmethod
    def list_for(user: User, sector_id):
        sector, _role = SectorService.get_sector(user, sector_id)
        return CycleService._with_progress(Cycle.objects.filter(sector=sector))

    @staticmethod
    def create(user: User, sector_id, data: dict) -> Cycle:
        sector, _role = SectorService.get_sector(user, sector_id, Role.EDITOR)
        CycleService._check_dates(data["start_date"], data["end_date"])
        cycle = Cycle.objects.create(sector=sector, **data)
        return CycleService._reload(cycle)

    @staticmethod
    def update(user: User, cycle_id, data: dict) -> Cycle:
        cycle = CycleService._get(user, cycle_id, Role.EDITOR)
        for field, value in data.items():
            setattr(cycle, field, value)
        CycleService._check_dates(cycle.start_date, cycle.end_date)
        cycle.save()
        return CycleService._reload(cycle)

    @staticmethod
    def delete(user: User, cycle_id) -> None:
        # its tasks stay in the project, only leave the cycle (SET_NULL)
        CycleService._get(user, cycle_id, Role.EDITOR).delete()

    @staticmethod
    def _with_progress(queryset):
        return queryset.annotate(
            task_total=Count("tasks", filter=ACTIVE_TASKS),
            task_done=Count(
                "tasks", filter=ACTIVE_TASKS & Q(tasks__completed_at__isnull=False)
            ),
            points_total=Coalesce(Sum("tasks__estimate", filter=ACTIVE_TASKS), 0),
            points_done=Coalesce(
                Sum(
                    "tasks__estimate",
                    filter=ACTIVE_TASKS & Q(tasks__completed_at__isnull=False),
                ),
                0,
            ),
        )

    @staticmethod
    def burndown(user: User, cycle_id) -> dict:
        """What was still open at the end of each day of the cycle (up to today)."""
        cycle = CycleService._get(user, cycle_id, Role.VIEWER)
        rows = list(
            cycle.tasks.filter(is_active=True).values("completed_at", "estimate")
        )
        today = timezone.localdate()
        last = min(cycle.end_date, today)
        days, day = [], cycle.start_date
        while day <= last:
            open_rows = [
                row
                for row in rows
                if row["completed_at"] is None
                or timezone.localtime(row["completed_at"]).date() > day
            ]
            days.append(
                {
                    "date": day,
                    "remaining": len(open_rows),
                    "remaining_points": sum(r["estimate"] or 0 for r in open_rows),
                }
            )
            day += timedelta(days=1)
        return {
            "start_date": cycle.start_date,
            "end_date": cycle.end_date,
            "total": len(rows),
            "total_points": sum(r["estimate"] or 0 for r in rows),
            "days": days,
        }

    @staticmethod
    def _reload(cycle: Cycle) -> Cycle:
        return CycleService._with_progress(Cycle.objects.filter(pk=cycle.pk)).get()

    @staticmethod
    def _get(user: User, cycle_id, minimum: str) -> Cycle:
        cycle = (
            Cycle.objects.select_related("sector")
            .filter(id=cycle_id, sector__is_active=True)
            .first()
        )
        if cycle is None:
            raise NotFound()
        SectorService.get_sector(user, cycle.sector_id, minimum)
        return cycle

    @staticmethod
    def _check_dates(start, end) -> None:
        if end < start:
            raise ValidationError({"end_date": [MSG_CYCLE_DATES_INVALID]})
