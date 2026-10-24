from django.db import transaction
from django.db.models import Max
from rest_framework.exceptions import NotFound, PermissionDenied

from core.models.user import User
from core.modules.kanban.models.resource_link import ResourceLink
from core.modules.kanban.models.task import ChecklistItem, Comment
from core.modules.kanban.response_messages import (
    MSG_SECTOR_ROLE_REQUIRED,
    MSG_TASK_COMMENTED,
)
from core.modules.kanban.services.sector import Role, SectorService
from core.modules.kanban.services.task import TaskService
from core.modules.organizations.models.organization import OrganizationMember
from core.modules.organizations.services.organization import OrganizationService


class ChecklistService:
    @staticmethod
    def list_for(user: User, task_id):
        task, _sector, _role = TaskService.get_task(user, task_id)
        return ChecklistItem.objects.filter(task=task)

    @staticmethod
    def create(user: User, task_id, data: dict) -> ChecklistItem:
        task, _sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        if data.get("position") is None:
            last = task.checklist_items.aggregate(last=Max("position"))["last"]
            data["position"] = 0 if last is None else last + 1
        return ChecklistItem.objects.create(task=task, **data)

    @staticmethod
    def update(user: User, task_id, item_id, data: dict) -> ChecklistItem:
        item = ChecklistService._get(user, task_id, item_id)
        for field, value in data.items():
            setattr(item, field, value)
        item.save()
        return item

    @staticmethod
    def delete(user: User, task_id, item_id) -> None:
        ChecklistService._get(user, task_id, item_id).delete()

    @staticmethod
    def _get(user: User, task_id, item_id) -> ChecklistItem:
        task, _sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        try:
            return ChecklistItem.objects.get(task=task, id=item_id)
        except ChecklistItem.DoesNotExist:
            raise NotFound()


class CommentService:
    @staticmethod
    def list_for(user: User, task_id):
        task, _sector, _role = TaskService.get_task(user, task_id)
        return Comment.objects.filter(task=task).select_related("author")

    @staticmethod
    @transaction.atomic
    def create(user: User, task_id, content: str) -> Comment:
        task, _sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        comment = Comment.objects.create(task=task, author=user, content=content)
        TaskService._notify_assignee(
            user,
            task,
            title=MSG_TASK_COMMENTED,
            message=content[:200],
            event="task.commented",
            preference="app_comments",
        )
        return comment

    @staticmethod
    def update(user: User, task_id, comment_id, content: str) -> Comment:
        task, _sector, _role = TaskService.get_task(user, task_id)
        comment = CommentService._get(task, comment_id)
        if comment.author_id != user.pk:
            raise PermissionDenied(MSG_SECTOR_ROLE_REQUIRED)
        comment.content = content
        comment.save(update_fields=["content"])
        return comment

    @staticmethod
    def delete(user: User, task_id, comment_id) -> None:
        task, _sector, role = TaskService.get_task(user, task_id)
        comment = CommentService._get(task, comment_id)
        if comment.author_id != user.pk and role != Role.MANAGER:
            raise PermissionDenied(MSG_SECTOR_ROLE_REQUIRED)
        comment.delete()

    @staticmethod
    def _get(task, comment_id) -> Comment:
        try:
            return Comment.objects.select_related("author").get(
                task=task, id=comment_id
            )
        except Comment.DoesNotExist:
            raise NotFound()


class LinkService:
    """Supporting links attached to exactly one of organization / sector / task."""

    @staticmethod
    def list_for_task(user: User, task_id):
        task, _sector, _role = TaskService.get_task(user, task_id)
        return ResourceLink.objects.filter(task=task)

    @staticmethod
    def create_for_task(user: User, task_id, data: dict) -> ResourceLink:
        task, _sector, _role = TaskService.get_task(user, task_id, Role.EDITOR)
        return ResourceLink.objects.create(task=task, created_by=user, **data)

    @staticmethod
    def list_for_sector(user: User, sector_id):
        sector, _role = SectorService.get_sector(user, sector_id)
        return ResourceLink.objects.filter(sector=sector)

    @staticmethod
    def create_for_sector(user: User, sector_id, data: dict) -> ResourceLink:
        sector, _role = SectorService.get_sector(user, sector_id, Role.EDITOR)
        return ResourceLink.objects.create(sector=sector, created_by=user, **data)

    @staticmethod
    def list_for_organization(user: User, organization_id):
        OrganizationService.get_membership(user, organization_id)
        return ResourceLink.objects.filter(organization_id=organization_id)

    @staticmethod
    def create_for_organization(user: User, organization_id, data: dict):
        OrganizationService.require_role(
            user, organization_id, OrganizationMember.Role.MEMBER
        )
        return ResourceLink.objects.create(
            organization_id=organization_id, created_by=user, **data
        )

    @staticmethod
    def delete(user: User, link_id) -> None:
        """Creator, or a manager of the target (sector/task) / admin of the organization."""
        link = ResourceLink.objects.filter(id=link_id).first()
        if link is None:
            raise NotFound()
        if link.task_id:
            _task, _sector, role = TaskService.get_task(user, link.task_id)
            allowed = role == Role.MANAGER
        elif link.sector_id:
            _sector, role = SectorService.get_sector(user, link.sector_id)
            allowed = role == Role.MANAGER
        else:
            membership = OrganizationService.get_membership(user, link.organization_id)
            allowed = membership.role in (
                OrganizationMember.Role.OWNER,
                OrganizationMember.Role.ADMIN,
            )
        if not (allowed or link.created_by_id == user.pk):
            raise PermissionDenied(MSG_SECTOR_ROLE_REQUIRED)
        link.delete()
