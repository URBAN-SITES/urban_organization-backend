from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from core.models.user import User
from core.modules.kanban.models.sector import Sector, SectorMember
from core.modules.kanban.models.task import Status, Task
from core.modules.kanban.response_messages import (
    MSG_SECTOR_ALREADY_MEMBER,
    MSG_SECTOR_ROLE_REQUIRED,
    MSG_SECTOR_TEAM_ALREADY_LINKED,
    MSG_SECTOR_TEAM_INVALID,
    MSG_SECTOR_USER_NOT_IN_ORGANIZATION,
)
from core.modules.organizations.models.organization import OrganizationMember
from core.modules.organizations.services.organization import OrganizationService
from core.modules.teams.models.team import SectorTeam, Team, TeamMember

Role = SectorMember.Role
RANK = {Role.VIEWER: 0, Role.EDITOR: 1, Role.MANAGER: 2}
ORG_ADMINS = (OrganizationMember.Role.OWNER, OrganizationMember.Role.ADMIN)
DEFAULT_STATUSES = (
    ("To do", Status.Category.TODO),
    ("In progress", Status.Category.IN_PROGRESS),
    ("Done", Status.Category.DONE),
)


class SectorService:
    @staticmethod
    def effective_role(user: User, sector: Sector) -> str | None:
        """Highest role among: direct, via team, org owner/admin, public viewer."""
        org_member = OrganizationMember.objects.filter(
            organization_id=sector.organization_id, user=user
        ).first()
        if org_member is None:
            return None
        if org_member.role in ORG_ADMINS:
            return Role.MANAGER
        roles = list(
            SectorMember.objects.filter(sector=sector, user=user).values_list(
                "role", flat=True
            )
        )
        roles += SectorTeam.objects.filter(
            sector=sector, team__is_active=True, team__members__user=user
        ).values_list("role", flat=True)
        if not sector.is_private:
            roles.append(Role.VIEWER)
        return max(roles, key=RANK.get, default=None)

    @staticmethod
    def participant_ids(sector: Sector) -> set:
        """Everyone with some access: org owners/admins, participants, linked teams
        and, for a public sector, every organization member."""
        org_members = OrganizationMember.objects.filter(
            organization_id=sector.organization_id
        )
        if not sector.is_private:
            return set(org_members.values_list("user_id", flat=True))
        ids = set(
            org_members.filter(role__in=ORG_ADMINS).values_list("user_id", flat=True)
        )
        ids |= set(
            SectorMember.objects.filter(sector=sector).values_list("user_id", flat=True)
        )
        ids |= set(
            TeamMember.objects.filter(
                team__is_active=True, team__sectors__sector=sector
            ).values_list("user_id", flat=True)
        )
        return ids & set(org_members.values_list("user_id", flat=True))

    @staticmethod
    def get_sector(user: User, sector_id, minimum: str = Role.VIEWER):
        """Returns (sector, role). 404 when the caller cannot see the sector."""
        sector = (
            Sector.objects.select_related("organization")
            .filter(id=sector_id, is_active=True, organization__is_active=True)
            .first()
        )
        role = SectorService.effective_role(user, sector) if sector else None
        if role is None:
            raise NotFound()
        if RANK[role] < RANK[minimum]:
            raise PermissionDenied(MSG_SECTOR_ROLE_REQUIRED)
        return sector, role

    @staticmethod
    def list_for(user: User, organization_id):
        membership = OrganizationService.get_membership(user, organization_id)
        sectors = Sector.objects.filter(organization_id=organization_id, is_active=True)
        if membership.role not in ORG_ADMINS:
            sectors = sectors.filter(
                Q(is_private=False)
                | Q(members__user=user)
                | Q(teams__team__is_active=True, teams__team__members__user=user)
            ).distinct()
        return sectors.order_by("name")

    @staticmethod
    @transaction.atomic
    def create(user: User, organization_id, **data) -> Sector:
        OrganizationService.require_role(
            user, organization_id, OrganizationMember.Role.MEMBER
        )
        sector = Sector.objects.create(
            organization_id=organization_id, owner=user, **data
        )
        SectorMember.objects.create(sector=sector, user=user, role=Role.MANAGER)
        Status.objects.bulk_create(
            Status(sector=sector, name=name, category=category, position=position)
            for position, (name, category) in enumerate(DEFAULT_STATUSES)
        )
        return sector

    @staticmethod
    def update(user: User, sector_id, data: dict) -> Sector:
        sector, _role = SectorService.get_sector(user, sector_id, Role.MANAGER)
        for field, value in data.items():
            setattr(sector, field, value)
        sector.save()
        return sector

    @staticmethod
    def delete(user: User, sector_id) -> None:
        sector, _role = SectorService.get_sector(user, sector_id, Role.MANAGER)
        sector.soft_delete()

    @staticmethod
    def progress(user: User, sector_id) -> dict:
        sector, _role = SectorService.get_sector(user, sector_id)
        tasks = Task.objects.filter(sector=sector, is_active=True)
        total = tasks.count()
        completed = tasks.filter(completed_at__isnull=False).count()
        return {
            "total": total,
            "completed": completed,
            "overdue": tasks.overdue().count(),
            "percent": round(completed * 100 / total, 1) if total else 0.0,
        }

    # participants -------------------------------------------------------

    @staticmethod
    def list_members(user: User, sector_id):
        sector, _role = SectorService.get_sector(user, sector_id)
        return (
            SectorMember.objects.filter(sector=sector)
            .select_related("user")
            .order_by("user__name", "id")
        )

    @staticmethod
    def add_member(user: User, sector_id, user_id, role: str) -> SectorMember:
        sector, _role = SectorService.get_sector(user, sector_id, Role.MANAGER)
        if not OrganizationMember.objects.filter(
            organization_id=sector.organization_id, user_id=user_id
        ).exists():
            raise ValidationError(MSG_SECTOR_USER_NOT_IN_ORGANIZATION)
        member, created = SectorMember.objects.get_or_create(
            sector=sector, user_id=user_id, defaults={"role": role}
        )
        if not created:
            raise ValidationError(MSG_SECTOR_ALREADY_MEMBER)
        return member

    @staticmethod
    def change_member_role(user: User, sector_id, member_id, role: str):
        sector, _role = SectorService.get_sector(user, sector_id, Role.MANAGER)
        member = SectorService._get_member(sector, member_id)
        member.role = role
        member.save(update_fields=["role"])
        return member

    @staticmethod
    def remove_member(user: User, sector_id, member_id) -> None:
        sector, _role = SectorService.get_sector(user, sector_id)
        member = SectorService._get_member(sector, member_id)
        if member.user_id != user.pk:  # leaving is always allowed
            SectorService.get_sector(user, sector_id, Role.MANAGER)
        member.delete()

    @staticmethod
    def _get_member(sector: Sector, member_id) -> SectorMember:
        try:
            return SectorMember.objects.select_related("user").get(
                sector=sector, id=member_id
            )
        except SectorMember.DoesNotExist:
            raise NotFound()

    # teams --------------------------------------------------------------

    @staticmethod
    def list_teams(user: User, sector_id):
        sector, _role = SectorService.get_sector(user, sector_id)
        return SectorTeam.objects.filter(sector=sector).select_related("team")

    @staticmethod
    def add_team(user: User, sector_id, team_id, role: str) -> SectorTeam:
        sector, _role = SectorService.get_sector(user, sector_id, Role.MANAGER)
        team = Team.objects.filter(
            id=team_id, organization_id=sector.organization_id, is_active=True
        ).first()
        if team is None:
            raise ValidationError(MSG_SECTOR_TEAM_INVALID)
        try:
            with transaction.atomic():
                return SectorTeam.objects.create(sector=sector, team=team, role=role)
        except IntegrityError:
            raise ValidationError(MSG_SECTOR_TEAM_ALREADY_LINKED)

    @staticmethod
    def remove_team(user: User, sector_id, link_id) -> None:
        sector, _role = SectorService.get_sector(user, sector_id, Role.MANAGER)
        deleted, _ = SectorTeam.objects.filter(sector=sector, id=link_id).delete()
        if not deleted:
            raise NotFound()
