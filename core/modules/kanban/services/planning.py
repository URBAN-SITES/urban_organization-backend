"""Epics (modules), pages (wiki) and the intake inbox of a project."""

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from core.models.user import User
from core.modules.kanban.models.epic import Epic
from core.modules.kanban.models.follow import TaskSubscriber
from core.modules.kanban.models.intake import IntakeRequest
from core.modules.kanban.models.page import Page
from core.modules.kanban.response_messages import (
    MSG_EPIC_DATES_INVALID,
    MSG_EPIC_LEAD_INVALID,
    MSG_INTAKE_ACCEPTED,
    MSG_INTAKE_DECIDED,
    MSG_INTAKE_DECLINED,
    MSG_INTAKE_NEW,
)
from core.modules.kanban.services.sector import RANK, Role, SectorService
from core.modules.kanban.services.task import TaskService
from core.modules.notifications.services.notification import NotificationService

ACTIVE = Q(tasks__is_active=True)
DONE = ACTIVE & Q(tasks__completed_at__isnull=False)


class EpicService:
    @staticmethod
    def list_for(user: User, sector_id):
        sector, _role = SectorService.get_sector(user, sector_id)
        return EpicService._with_progress(Epic.objects.filter(sector=sector))

    @staticmethod
    def create(user: User, sector_id, data: dict) -> Epic:
        sector, _role = SectorService.get_sector(user, sector_id, Role.EDITOR)
        epic = Epic(sector=sector, **data)
        EpicService._check(epic)
        epic.save()
        return EpicService._reload(epic)

    @staticmethod
    def update(user: User, epic_id, data: dict) -> Epic:
        epic = EpicService._get(user, epic_id)
        for field, value in data.items():
            setattr(epic, field, value)
        EpicService._check(epic)
        epic.save()
        return EpicService._reload(epic)

    @staticmethod
    def delete(user: User, epic_id) -> None:
        # the tasks stay in the project, only leave the epic (SET_NULL)
        EpicService._get(user, epic_id).delete()

    @staticmethod
    def _check(epic: Epic) -> None:
        if (
            epic.lead_id
            and SectorService.effective_role(epic.lead, epic.sector) is None
        ):
            raise ValidationError({"lead": [MSG_EPIC_LEAD_INVALID]})
        if epic.start_date and epic.target_date and epic.target_date < epic.start_date:
            raise ValidationError({"target_date": [MSG_EPIC_DATES_INVALID]})

    @staticmethod
    def _with_progress(queryset):
        return queryset.select_related("lead").annotate(
            task_total=Count("tasks", filter=ACTIVE),
            task_done=Count("tasks", filter=DONE),
            points_total=Coalesce(Sum("tasks__estimate", filter=ACTIVE), 0),
            points_done=Coalesce(Sum("tasks__estimate", filter=DONE), 0),
        )

    @staticmethod
    def _reload(epic: Epic) -> Epic:
        return EpicService._with_progress(Epic.objects.filter(pk=epic.pk)).get()

    @staticmethod
    def _get(user: User, epic_id) -> Epic:
        epic = Epic.objects.select_related("sector").filter(id=epic_id).first()
        if epic is None or not epic.sector.is_active:
            raise NotFound()
        SectorService.get_sector(user, epic.sector_id, Role.EDITOR)
        return epic


class PageService:
    @staticmethod
    def list_for(user: User, sector_id):
        sector, _role = SectorService.get_sector(user, sector_id)
        return Page.objects.filter(sector=sector).select_related(
            "created_by", "updated_by"
        )

    @staticmethod
    def get(user: User, page_id) -> Page:
        return PageService._get(user, page_id, Role.VIEWER)

    @staticmethod
    def create(user: User, sector_id, data: dict) -> Page:
        sector, _role = SectorService.get_sector(user, sector_id, Role.EDITOR)
        return Page.objects.create(
            sector=sector, created_by=user, updated_by=user, **data
        )

    @staticmethod
    def update(user: User, page_id, data: dict) -> Page:
        page = PageService._get(user, page_id, Role.EDITOR)
        for field, value in data.items():
            setattr(page, field, value)
        page.updated_by = user
        page.save()
        return page

    @staticmethod
    def delete(user: User, page_id) -> None:
        PageService._get(user, page_id, Role.EDITOR).delete()

    @staticmethod
    def _get(user: User, page_id, minimum: str) -> Page:
        page = (
            Page.objects.select_related("sector", "created_by", "updated_by")
            .filter(id=page_id)
            .first()
        )
        if page is None or not page.sector.is_active:
            raise NotFound()
        SectorService.get_sector(user, page.sector_id, minimum)
        return page


class IntakeService:
    """Anyone who sees the project may ask; editors answer. Viewers see their own."""

    @staticmethod
    def list_for(user: User, sector_id):
        sector, role = SectorService.get_sector(user, sector_id)
        rows = IntakeRequest.objects.filter(sector=sector).select_related(
            "requester", "decided_by", "task", "task__sector"
        )
        if RANK[role] < RANK[Role.EDITOR]:
            rows = rows.filter(requester=user)
        return rows

    @staticmethod
    def create(user: User, sector_id, data: dict) -> IntakeRequest:
        sector, _role = SectorService.get_sector(user, sector_id)
        request = IntakeRequest.objects.create(sector=sector, requester=user, **data)
        ids = SectorService.participant_ids(sector) - {user.pk}
        for person in User.objects.filter(pk__in=ids, is_active=True):
            role = SectorService.effective_role(person, sector)
            if role is None or RANK[role] < RANK[Role.EDITOR]:
                continue
            NotificationService.notify(
                person,
                str(MSG_INTAKE_NEW),
                f"{sector.name}: {request.title}",
                IntakeService._data(request, "intake.created"),
            )
        return request

    @staticmethod
    @transaction.atomic
    def accept(user: User, request_id, data: dict) -> IntakeRequest:
        request = IntakeService._pending(user, request_id)
        task = TaskService.create(
            user,
            request.sector_id,
            {"title": request.title, "description": request.description, **data},
        )
        IntakeService._decide(user, request, IntakeRequest.State.ACCEPTED, "", task)
        # whoever asked follows the task: comments and status changes reach them
        if request.requester_id:
            TaskSubscriber.objects.get_or_create(task=task, user=request.requester)
        return request

    @staticmethod
    def decline(user: User, request_id, note: str) -> IntakeRequest:
        request = IntakeService._pending(user, request_id)
        IntakeService._decide(user, request, IntakeRequest.State.DECLINED, note, None)
        return request

    @staticmethod
    def _decide(user, request, state, note, task) -> None:
        request.state = state
        request.decision_note = note
        request.task = task
        request.decided_by = user
        request.decided_at = timezone.now()
        request.save()
        if request.requester_id and request.requester_id != user.pk:
            accepted = state == IntakeRequest.State.ACCEPTED
            NotificationService.notify(
                request.requester,
                str(MSG_INTAKE_ACCEPTED if accepted else MSG_INTAKE_DECLINED),
                note or request.title,
                IntakeService._data(
                    request, "intake.accepted" if accepted else "intake.declined"
                ),
            )

    @staticmethod
    def _pending(user: User, request_id) -> IntakeRequest:
        request = (
            IntakeRequest.objects.select_related("sector", "requester")
            .filter(id=request_id)
            .first()
        )
        if request is None or not request.sector.is_active:
            raise NotFound()
        SectorService.get_sector(user, request.sector_id, Role.EDITOR)
        if request.state != IntakeRequest.State.PENDING:
            raise ValidationError(MSG_INTAKE_DECIDED)
        return request

    @staticmethod
    def _data(request: IntakeRequest, event: str) -> dict:
        data = {
            "event": event,
            "intake_id": str(request.pk),
            "sector_id": str(request.sector_id),
            "organization_id": str(request.sector.organization_id),
        }
        if request.task_id:
            data["task_id"] = str(request.task_id)
        return data
