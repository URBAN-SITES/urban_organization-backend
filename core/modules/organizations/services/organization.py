from django.db import IntegrityError, transaction
from django.db.models import F
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from core.models.user import User
from core.modules.organizations.models.organization import (
    Organization,
    OrganizationMember,
)
from core.modules.organizations.response_messages import (
    MSG_ORGANIZATION_ALREADY_MEMBER,
    MSG_ORGANIZATION_OWNER_PROTECTED,
    MSG_ORGANIZATION_PERSONAL_PROTECTED,
    MSG_ORGANIZATION_ROLE_REQUIRED,
    MSG_ORGANIZATION_USER_NOT_FOUND,
)

Role = OrganizationMember.Role
RANK = {Role.VIEWER: 0, Role.MEMBER: 1, Role.ADMIN: 2, Role.OWNER: 3}


class OrganizationService:
    @staticmethod
    def ensure_personal(user: User) -> None:
        """Every user owns one personal organization (created lazily on first list)."""
        if Organization.objects.filter(owner=user, is_personal=True).exists():
            return
        OrganizationService.create(
            user, name=f"{user.get_short_name()}'s workspace", is_personal=True
        )

    @staticmethod
    @transaction.atomic
    def create(user: User, is_personal: bool = False, **data) -> Organization:
        try:
            with transaction.atomic():
                organization = Organization.objects.create(
                    owner=user, is_personal=is_personal, **data
                )
        except IntegrityError:
            raise ValidationError({"slug": "This workspace address is already in use."})
        OrganizationMember.objects.create(
            organization=organization, user=user, role=Role.OWNER
        )
        return organization

    @staticmethod
    def list_for(user: User):
        OrganizationService.ensure_personal(user)
        return (
            Organization.objects.filter(is_active=True, members__user=user)
            .annotate(current_role=F("members__role"))
            .order_by("-is_personal", "name")
        )

    @staticmethod
    def get_membership(user: User, organization_id) -> OrganizationMember:
        """The caller's membership; 404 for non-members so existence stays hidden."""
        try:
            return OrganizationMember.objects.select_related("organization").get(
                organization_id=organization_id,
                organization__is_active=True,
                user=user,
            )
        except OrganizationMember.DoesNotExist:
            raise NotFound()

    @staticmethod
    def require_role(user: User, organization_id, minimum: str) -> OrganizationMember:
        membership = OrganizationService.get_membership(user, organization_id)
        if RANK[membership.role] < RANK[minimum]:
            raise PermissionDenied(MSG_ORGANIZATION_ROLE_REQUIRED)
        return membership

    @staticmethod
    def update(user: User, organization_id, data: dict) -> Organization:
        organization = OrganizationService.require_role(
            user, organization_id, Role.ADMIN
        ).organization
        for field, value in data.items():
            setattr(organization, field, value)
        organization.save()
        return organization

    @staticmethod
    def delete(user: User, organization_id) -> None:
        organization = OrganizationService.require_role(
            user, organization_id, Role.OWNER
        ).organization
        if organization.is_personal:
            raise ValidationError(MSG_ORGANIZATION_PERSONAL_PROTECTED)
        organization.soft_delete()

    @staticmethod
    def list_members(user: User, organization_id):
        OrganizationService.get_membership(user, organization_id)
        return (
            OrganizationMember.objects.filter(organization_id=organization_id)
            .select_related("user")
            .order_by("joined_at", "id")
        )

    @staticmethod
    def add_member(user: User, organization_id, email: str, role: str):
        actor = OrganizationService.require_role(user, organization_id, Role.ADMIN)
        OrganizationService._check_grant(actor, role)
        target = User.objects.filter(email__iexact=email, is_active=True).first()
        if target is None:
            raise ValidationError(MSG_ORGANIZATION_USER_NOT_FOUND)
        member, created = OrganizationMember.objects.get_or_create(
            organization_id=organization_id, user=target, defaults={"role": role}
        )
        if not created:
            raise ValidationError(MSG_ORGANIZATION_ALREADY_MEMBER)
        return member

    @staticmethod
    def change_role(user: User, organization_id, member_id, role: str):
        actor = OrganizationService.require_role(user, organization_id, Role.ADMIN)
        member = OrganizationService._get_member(organization_id, member_id)
        OrganizationService._check_grant(actor, role)
        OrganizationService._check_target(actor, member)
        member.role = role
        member.save(update_fields=["role"])
        return member

    @staticmethod
    def remove_member(user: User, organization_id, member_id) -> None:
        actor = OrganizationService.get_membership(user, organization_id)
        member = OrganizationService._get_member(organization_id, member_id)
        if member.user_id != actor.user_id:  # leaving is always allowed
            actor = OrganizationService.require_role(user, organization_id, Role.ADMIN)
            OrganizationService._check_target(actor, member)
        elif member.role == Role.OWNER:
            raise PermissionDenied(MSG_ORGANIZATION_OWNER_PROTECTED)
        member.delete()

    @staticmethod
    def _get_member(organization_id, member_id) -> OrganizationMember:
        try:
            return OrganizationMember.objects.select_related("user").get(
                organization_id=organization_id, id=member_id
            )
        except OrganizationMember.DoesNotExist:
            raise NotFound()

    @staticmethod
    def _check_grant(actor: OrganizationMember, role: str) -> None:
        # owner is never granted here; only an owner may grant admin
        if role == Role.OWNER:
            raise PermissionDenied(MSG_ORGANIZATION_OWNER_PROTECTED)
        if RANK[role] >= RANK[actor.role]:
            raise PermissionDenied(MSG_ORGANIZATION_ROLE_REQUIRED)

    @staticmethod
    def _check_target(actor: OrganizationMember, member: OrganizationMember) -> None:
        if member.role == Role.OWNER:
            raise PermissionDenied(MSG_ORGANIZATION_OWNER_PROTECTED)
        if RANK[member.role] >= RANK[actor.role]:
            raise PermissionDenied(MSG_ORGANIZATION_ROLE_REQUIRED)
