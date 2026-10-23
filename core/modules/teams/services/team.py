from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from core.models.user import User
from core.modules.organizations.models.organization import OrganizationMember
from core.modules.organizations.services.organization import (
    RANK,
    OrganizationService,
)
from core.modules.teams.models.team import Team, TeamMember
from core.modules.teams.response_messages import (
    MSG_TEAM_ALREADY_MEMBER,
    MSG_TEAM_NAME_TAKEN,
    MSG_TEAM_PERMISSION_REQUIRED,
    MSG_TEAM_USER_NOT_IN_ORGANIZATION,
)

OrgRole = OrganizationMember.Role


class TeamService:
    @staticmethod
    def list_for(user: User, organization_id):
        OrganizationService.get_membership(user, organization_id)
        return Team.objects.filter(
            organization_id=organization_id, is_active=True
        ).order_by("name")

    @staticmethod
    def get(user: User, organization_id, team_id) -> Team:
        OrganizationService.get_membership(user, organization_id)
        try:
            return Team.objects.get(
                id=team_id, organization_id=organization_id, is_active=True
            )
        except Team.DoesNotExist:
            raise NotFound()

    @staticmethod
    @transaction.atomic
    def create(user: User, organization_id, **data) -> Team:
        OrganizationService.require_role(user, organization_id, OrgRole.ADMIN)
        try:
            with transaction.atomic():
                team = Team.objects.create(
                    organization_id=organization_id, owner=user, **data
                )
        except IntegrityError:
            raise ValidationError(MSG_TEAM_NAME_TAKEN)
        TeamMember.objects.create(team=team, user=user, role=TeamMember.Role.LEAD)
        return team

    @staticmethod
    def update(user: User, organization_id, team_id, data: dict) -> Team:
        team = TeamService._get_managed(user, organization_id, team_id)
        for field, value in data.items():
            setattr(team, field, value)
        try:
            with transaction.atomic():
                team.save()
        except IntegrityError:
            raise ValidationError(MSG_TEAM_NAME_TAKEN)
        return team

    @staticmethod
    def delete(user: User, organization_id, team_id) -> None:
        OrganizationService.require_role(user, organization_id, OrgRole.ADMIN)
        # hard delete: the (organization, name) uniqueness must free the name
        TeamService.get(user, organization_id, team_id).delete()

    @staticmethod
    def list_members(user: User, organization_id, team_id):
        team = TeamService.get(user, organization_id, team_id)
        return (
            TeamMember.objects.filter(team=team)
            .select_related("user")
            .order_by("joined_at", "id")
        )

    @staticmethod
    def add_member(user: User, organization_id, team_id, user_id, role: str):
        team = TeamService._get_managed(user, organization_id, team_id)
        if not OrganizationMember.objects.filter(
            organization_id=organization_id, user_id=user_id
        ).exists():
            raise ValidationError(MSG_TEAM_USER_NOT_IN_ORGANIZATION)
        member, created = TeamMember.objects.get_or_create(
            team=team, user_id=user_id, defaults={"role": role}
        )
        if not created:
            raise ValidationError(MSG_TEAM_ALREADY_MEMBER)
        return member

    @staticmethod
    def change_role(user: User, organization_id, team_id, member_id, role: str):
        team = TeamService._get_managed(user, organization_id, team_id)
        member = TeamService._get_member(team, member_id)
        member.role = role
        member.save(update_fields=["role"])
        return member

    @staticmethod
    def remove_member(user: User, organization_id, team_id, member_id) -> None:
        team = TeamService.get(user, organization_id, team_id)
        member = TeamService._get_member(team, member_id)
        if member.user_id != user.pk:  # leaving is always allowed
            TeamService._get_managed(user, organization_id, team_id)
        member.delete()

    @staticmethod
    def _get_member(team: Team, member_id) -> TeamMember:
        try:
            return TeamMember.objects.select_related("user").get(
                team=team, id=member_id
            )
        except TeamMember.DoesNotExist:
            raise NotFound()

    @staticmethod
    def _get_managed(user: User, organization_id, team_id) -> Team:
        """Team the caller may manage: org admin/owner or the team's lead."""
        team = TeamService.get(user, organization_id, team_id)
        membership = OrganizationService.get_membership(user, organization_id)
        is_admin = RANK[membership.role] >= RANK[OrgRole.ADMIN]
        is_lead = TeamMember.objects.filter(
            team=team, user=user, role=TeamMember.Role.LEAD
        ).exists()
        if not (is_admin or is_lead):
            raise PermissionDenied(MSG_TEAM_PERMISSION_REQUIRED)
        return team
