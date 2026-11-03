from django.db.models import Count, Q
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
        )

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
