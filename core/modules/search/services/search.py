from django.db.models import Q
from rest_framework.exceptions import ValidationError

from core.models.user import User
from core.modules.chat.services.chat import ChatService
from core.modules.kanban.models.task import Task
from core.modules.kanban.services.sector import SectorService
from core.modules.organizations.models.organization import OrganizationMember
from core.modules.organizations.services.organization import OrganizationService
from core.modules.search.response_messages import MSG_SEARCH_TOO_SHORT
from core.modules.uploads.models.attachment import Attachment

LIMIT = 10
MIN_LENGTH = 2


class SearchService:
    @staticmethod
    def search(user: User, organization_id, query: str) -> dict:
        """Tasks, people and files of one organization, limited to what the caller can see."""
        query = query.strip()
        if len(query) < MIN_LENGTH:
            raise ValidationError(MSG_SEARCH_TOO_SHORT)
        OrganizationService.get_membership(user, organization_id)
        sector_ids = list(
            SectorService.list_for(user, organization_id).values_list("pk", flat=True)
        )

        tasks = (
            Task.objects.filter(is_active=True, sector_id__in=sector_ids)
            .filter(Q(title__icontains=query) | Q(description__icontains=query))
            .select_related("sector", "status")
            .order_by("-created_at")[:LIMIT]
        )
        people = (
            OrganizationMember.objects.filter(
                organization_id=organization_id, user__is_active=True
            )
            .filter(Q(user__name__icontains=query) | Q(user__email__icontains=query))
            .select_related("user")
            .order_by("user__name")[:LIMIT]
        )
        no_target = Q(
            sector__isnull=True,
            task__isnull=True,
            comment__isnull=True,
            message__isnull=True,
        )
        channel_ids = ChatService.accessible_channel_ids(user, organization_id)
        files = (
            Attachment.objects.filter(
                organization_id=organization_id, file_name__icontains=query
            )
            .filter(
                no_target
                | Q(sector_id__in=sector_ids)
                | Q(task__sector_id__in=sector_ids)
                | Q(comment__task__sector_id__in=sector_ids)
                | Q(message__channel_id__in=channel_ids)
            )
            .order_by("-created_at")[:LIMIT]
        )
        return {"tasks": tasks, "people": people, "files": files}
