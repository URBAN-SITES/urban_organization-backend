from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from core.models.user import User
from core.modules.kanban.models.task import Status, Task
from core.modules.kanban.response_messages import (
    MSG_STATUS_HAS_TASKS,
    MSG_STATUS_LAST_DONE,
    MSG_STATUS_NAME_TAKEN,
)
from core.modules.kanban.services.sector import Role, SectorService


class StatusService:
    @staticmethod
    def list_for(user: User, sector_id):
        sector, _role = SectorService.get_sector(user, sector_id)
        return Status.objects.filter(sector=sector)

    @staticmethod
    def create(user: User, sector_id, **data) -> Status:
        sector, _role = SectorService.get_sector(user, sector_id, Role.MANAGER)
        if data.get("position") is None:
            last = sector.statuses.aggregate(last=Max("position"))["last"]
            data["position"] = 0 if last is None else last + 1
        try:
            with transaction.atomic():
                return Status.objects.create(sector=sector, **data)
        except IntegrityError:
            raise ValidationError(MSG_STATUS_NAME_TAKEN)

    @staticmethod
    def update(user: User, sector_id, status_id, data: dict) -> Status:
        status = StatusService._get(user, sector_id, status_id)
        old_category = status.category
        for field, value in data.items():
            setattr(status, field, value)
        try:
            with transaction.atomic():
                status.save()
                if status.category != old_category:
                    StatusService._sync_completion(status)
        except IntegrityError:
            raise ValidationError(MSG_STATUS_NAME_TAKEN)
        return status

    @staticmethod
    def delete(user: User, sector_id, status_id) -> None:
        status = StatusService._get(user, sector_id, status_id)
        if Task.objects.filter(status=status, is_active=True).exists():
            raise ValidationError(MSG_STATUS_HAS_TASKS)
        is_last_done = (
            status.category == Status.Category.DONE
            and not status.sector.statuses.filter(category=Status.Category.DONE)
            .exclude(pk=status.pk)
            .exists()
        )
        if is_last_done:
            raise ValidationError(MSG_STATUS_LAST_DONE)
        # soft-deleted tasks still reference it (PROTECT), so drop them too
        Task.objects.filter(status=status, is_active=False).delete()
        status.delete()

    @staticmethod
    def _get(user: User, sector_id, status_id) -> Status:
        sector, _role = SectorService.get_sector(user, sector_id, Role.MANAGER)
        try:
            return Status.objects.select_related("sector").get(
                id=status_id, sector=sector
            )
        except Status.DoesNotExist:
            raise NotFound()

    @staticmethod
    def _sync_completion(status: Status) -> None:
        """Keep completed_at coherent when a column changes category."""
        tasks = Task.objects.filter(status=status)
        if status.category == Status.Category.DONE:
            tasks.filter(completed_at__isnull=True).update(completed_at=timezone.now())
        else:
            tasks.update(completed_at=None)
