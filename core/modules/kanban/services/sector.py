from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, Q, Value
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from core.models.user import User
from core.modules.kanban.identifiers import make_identifier
from core.modules.kanban.models.sector import Sector, SectorFavorite, SectorMember
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
    ("A fazer", Status.Category.TODO),
    ("Em andamento", Status.Category.IN_PROGRESS),
    ("Concluído", Status.Category.DONE),
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
        if org_member.role == OrganizationMember.Role.GUEST:
            # guests: only the projects they were added to, never via teams/public
            return max(roles, key=RANK.get, default=None)
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
        direct = set(
            SectorMember.objects.filter(sector=sector).values_list("user_id", flat=True)
        )
        guests = set(
            org_members.filter(role=OrganizationMember.Role.GUEST).values_list(
                "user_id", flat=True
            )
        )
        if not sector.is_private:
            everyone = set(org_members.values_list("user_id", flat=True))
            return (everyone - guests) | (direct & guests)
        ids = set(
            org_members.filter(role__in=ORG_ADMINS).values_list("user_id", flat=True)
        )
        ids |= direct
        ids |= (
            set(
                TeamMember.objects.filter(
                    team__is_active=True, team__sectors__sector=sector
                ).values_list("user_id", flat=True)
            )
            - guests
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
    def list_for(
        user: User,
        organization_id,
        archived: bool = False,
        search: str = "",
        favorite: bool = False,
        ordering: str = "name",
    ):
        """Sectors the user can see; archived ones only when asked for."""
        membership = OrganizationService.get_membership(
            user, organization_id, allow_guest=True
        )
        sectors = Sector.objects.filter(
            organization_id=organization_id,
            is_active=True,
            archived_at__isnull=not archived,
        )
        if membership.role == OrganizationMember.Role.GUEST:
            sectors = sectors.filter(members__user=user).distinct()
        elif membership.role not in ORG_ADMINS:
            sectors = sectors.filter(
                Q(is_private=False)
                | Q(members__user=user)
                | Q(teams__team__is_active=True, teams__team__members__user=user)
            ).distinct()
        if search:
            sectors = sectors.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )
        if favorite:
            sectors = sectors.filter(favorites__user=user)
        return sectors.order_by(ordering, "id")

    @staticmethod
    def with_can_manage(queryset, user: User, organization_id):
        """Whether the user is a manager of each sector (direct, via team or org admin)."""
        if OrganizationMember.objects.filter(
            organization_id=organization_id, user=user, role__in=ORG_ADMINS
        ).exists():
            return queryset.annotate(can_manage=Value(True))
        return queryset.annotate(
            can_manage=Exists(
                SectorMember.objects.filter(
                    sector=OuterRef("pk"), user=user, role=Role.MANAGER
                )
            )
            | Exists(
                SectorTeam.objects.filter(
                    sector=OuterRef("pk"),
                    role=Role.MANAGER,
                    team__is_active=True,
                    team__members__user=user,
                )
            )
        )

    @staticmethod
    @transaction.atomic
    def create(user: User, organization_id, **data) -> Sector:
        OrganizationService.require_role(
            user, organization_id, OrganizationMember.Role.MEMBER
        )
        data.setdefault("identifier", "")
        data["identifier"] = data["identifier"] or make_identifier(data["name"])
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
        if "identifier" in data and not data["identifier"]:
            data["identifier"] = make_identifier(data.get("name", sector.name))
        for field, value in data.items():
            setattr(sector, field, value)
        sector.save()
        return sector

    @staticmethod
    def with_favorite(queryset, user: User):
        return queryset.annotate(
            is_favorite=Exists(
                SectorFavorite.objects.filter(sector=OuterRef("pk"), user=user)
            )
        )

    @staticmethod
    def with_progress(queryset):
        active = Q(tasks__is_active=True)
        return queryset.annotate(
            task_total=Count("tasks", filter=active, distinct=True),
            task_done=Count(
                "tasks",
                filter=active & Q(tasks__completed_at__isnull=False),
                distinct=True,
            ),
        )

    @staticmethod
    def set_favorite(user: User, sector_id, favorite: bool) -> Sector:
        sector, _role = SectorService.get_sector(user, sector_id)
        if favorite:
            SectorFavorite.objects.get_or_create(sector=sector, user=user)
        else:
            SectorFavorite.objects.filter(sector=sector, user=user).delete()
        sector.is_favorite = favorite
        return sector

    @staticmethod
    def set_archived(user: User, sector_id, archived: bool) -> Sector:
        sector, _role = SectorService.get_sector(user, sector_id, Role.MANAGER)
        if archived and sector.archived_at is None:
            sector.archived_at = timezone.now()
        elif not archived:
            sector.archived_at = None
        sector.save(update_fields=["archived_at", "updated_at"])
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
