from urllib.parse import urlparse

from django.db.models import Q

from core.modules.kanban.models.resource_link import ResourceLink
from core.modules.kanban.services.sector import SectorService

LIMIT = 500


def link_origin(url: str) -> str:
    """drive | docs | meet | upload | link, from where the URL points."""
    host = urlparse(url).netloc.lower()
    if host == "meet.google.com":
        return "meet"
    if host in {"docs.google.com", "sheets.google.com", "slides.google.com"}:
        return "docs"
    if host.endswith("drive.google.com"):
        return "drive"
    if host.endswith("cloudinary.com"):
        return "upload"
    return "link"


class FileService:
    @staticmethod
    def list_for(user, organization_id) -> list[dict]:
        """Everything attached to the organization, its sectors and their tasks."""
        sectors = SectorService.list_for(user, organization_id)
        links = (
            ResourceLink.objects.filter(
                Q(organization_id=organization_id)
                | Q(sector__in=sectors)
                | Q(task__sector__in=sectors, task__is_active=True)
            )
            .select_related("task", "sector", "created_by")
            .order_by("-created_at")
            .distinct()[:LIMIT]
        )
        return [
            {
                "id": link.id,
                "title": link.title or link.url,
                "url": link.url,
                "origin": link_origin(link.url),
                "task_title": link.task.title if link.task else None,
                "sector_name": link.sector.name if link.sector else None,
                "owner_name": link.created_by.name,
                "created_at": link.created_at,
            }
            for link in links
        ]
