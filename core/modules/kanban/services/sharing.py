"""Read-only public link of a project: anyone with the link sees the board."""

import secrets

from rest_framework.exceptions import NotFound

from core.models.user import User
from core.modules.kanban.models.sector import Sector
from core.modules.kanban.models.task import Task
from core.modules.kanban.services.sector import Role, SectorService


class PublicLinkService:
    @staticmethod
    def get(user: User, sector_id) -> str | None:
        sector, _role = SectorService.get_sector(user, sector_id, Role.MANAGER)
        return sector.public_token

    @staticmethod
    def enable(user: User, sector_id) -> str:
        """Turns the link on; calling again keeps the same address."""
        sector, _role = SectorService.get_sector(user, sector_id, Role.MANAGER)
        if not sector.public_token:
            sector.public_token = secrets.token_urlsafe(24)
            sector.save(update_fields=["public_token", "updated_at"])
        return sector.public_token

    @staticmethod
    def disable(user: User, sector_id) -> None:
        """Turns the link off; turning it on again creates a new address."""
        sector, _role = SectorService.get_sector(user, sector_id, Role.MANAGER)
        sector.public_token = None
        sector.save(update_fields=["public_token", "updated_at"])

    @staticmethod
    def board(token: str) -> dict:
        """What the public page shows: columns and tasks, without people or text
        written inside the tasks (descriptions, comments, files)."""
        sector = (
            Sector.objects.filter(
                public_token=token,
                is_active=True,
                archived_at__isnull=True,
                organization__is_active=True,
            )
            .select_related("organization")
            .first()
            if token
            else None
        )
        if sector is None:
            raise NotFound()
        tasks = (
            Task.objects.filter(
                sector=sector,
                is_active=True,
                archived_at__isnull=True,
                parent__isnull=True,
            )
            .select_related("status")
            .prefetch_related("labels")
            .order_by("status__position", "position", "created_at")[:500]
        )
        prefix = sector.identifier
        return {
            "name": sector.name,
            "description": sector.description,
            "color": sector.color,
            "icon": sector.icon,
            "organization": sector.organization.name,
            "statuses": [
                {
                    "id": status.pk,
                    "name": status.name,
                    "category": status.category,
                    "color": status.color,
                }
                for status in sector.statuses.order_by("position")
            ],
            "tasks": [
                {
                    "id": task.pk,
                    "key": f"{prefix}-{task.sequence}"
                    if prefix and task.sequence
                    else None,
                    "title": task.title,
                    "status_id": task.status_id,
                    "priority": task.priority,
                    "start_date": task.start_date,
                    "due_date": task.due_date,
                    "estimate": task.estimate,
                    "completed": task.completed_at is not None,
                    "labels": [
                        {"name": label.name, "color": label.color}
                        for label in task.labels.all()
                    ],
                }
                for task in tasks
            ],
        }
