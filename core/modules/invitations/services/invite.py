import hashlib
import os
import secrets

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from core.models.user import User
from core.modules.invitations.models.invite import OrganizationInvite
from core.modules.invitations.response_messages import (
    MSG_INVITE_ALREADY_MEMBER,
    MSG_INVITE_ALREADY_PENDING,
    MSG_INVITE_INVALID,
    MSG_INVITE_NOT_PENDING,
)
from core.modules.invitations.tasks.invite import send_invite_email_task
from core.modules.kanban.models.sector import Sector, SectorMember
from core.modules.organizations.models.organization import OrganizationMember
from core.modules.organizations.services.organization import OrganizationService

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
Status = OrganizationInvite.Status


def _hash(token: str) -> str:
    # the token has 256 bits of entropy, so a plain SHA-256 is enough (and indexable)
    return hashlib.sha256(token.encode()).hexdigest()


class InviteService:
    @staticmethod
    def create(user: User, organization_id, email: str, role: str, sector_ids=None):
        actor = OrganizationService.require_role(
            user, organization_id, OrganizationMember.Role.ADMIN
        )
        OrganizationService._check_grant(actor, role)
        organization = actor.organization
        requested_sectors = set(sector_ids or [])
        sectors = list(
            Sector.objects.filter(
                pk__in=requested_sectors, organization=organization, is_active=True
            )
        )
        if len(sectors) != len(requested_sectors):
            raise ValidationError(
                {"sector_ids": "Choose active sectors from this organization."}
            )
        if OrganizationMember.objects.filter(
            organization=organization, user__email__iexact=email
        ).exists():
            raise ValidationError(MSG_INVITE_ALREADY_MEMBER)

        token = secrets.token_urlsafe(32)
        with transaction.atomic():
            # an expired invite must not block a new one (partial unique index)
            OrganizationInvite.objects.filter(
                organization=organization,
                email__iexact=email,
                status=Status.PENDING,
                expires_at__lte=timezone.now(),
            ).update(status=Status.EXPIRED)
            try:
                with transaction.atomic():
                    invite = OrganizationInvite.objects.create(
                        organization=organization,
                        email=email,
                        role=role,
                        token_hash=_hash(token),
                        invited_by=user,
                    )
            except IntegrityError:
                raise ValidationError(MSG_INVITE_ALREADY_PENDING)
            invite.sectors.set(sectors)
            link = f"{FRONTEND_URL}/invitations/accept?token={token}"
            transaction.on_commit(
                lambda: send_invite_email_task.delay(email, organization.name, link)
            )
        return invite

    @staticmethod
    def list_for_organization(user: User, organization_id):
        OrganizationService.require_role(
            user, organization_id, OrganizationMember.Role.ADMIN
        )
        return (
            OrganizationInvite.objects.filter(organization_id=organization_id)
            .select_related("organization")
            .prefetch_related("sectors")
        )

    @staticmethod
    def revoke(user: User, organization_id, invite_id) -> None:
        OrganizationService.require_role(
            user, organization_id, OrganizationMember.Role.ADMIN
        )
        updated = OrganizationInvite.objects.filter(
            id=invite_id, organization_id=organization_id
        )
        if not updated.exists():
            raise NotFound()
        if not updated.filter(status=Status.PENDING).update(status=Status.REVOKED):
            raise ValidationError(MSG_INVITE_NOT_PENDING)

    @staticmethod
    def list_mine(user: User):
        """Pending, unexpired invitations addressed to the caller's e-mail."""
        return (
            OrganizationInvite.objects.filter(
                email__iexact=user.email,
                status=Status.PENDING,
                expires_at__gt=timezone.now(),
                organization__is_active=True,
            )
            .select_related("organization")
            .prefetch_related("sectors")
        )

    @staticmethod
    def accept(user: User, token: str) -> OrganizationMember:
        with transaction.atomic():
            invite = (
                OrganizationInvite.objects.select_for_update()
                .select_related("organization")
                .filter(token_hash=_hash(token))
                .first()
            )
            # same answer for unknown, used, expired or someone else's invite
            if (
                invite is None
                or invite.status != Status.PENDING
                or not invite.organization.is_active
                or invite.email.lower() != user.email.lower()
            ):
                raise ValidationError(MSG_INVITE_INVALID)
            if invite.expires_at > timezone.now():
                member, _ = OrganizationMember.objects.get_or_create(
                    organization=invite.organization,
                    user=user,
                    defaults={"role": invite.role},
                )
                for sector in invite.sectors.filter(
                    organization_id=invite.organization_id, is_active=True
                ):
                    SectorMember.objects.get_or_create(
                        sector=sector,
                        user=user,
                        defaults={
                            "role": SectorMember.Role.VIEWER
                            if member.role == OrganizationMember.Role.VIEWER
                            else SectorMember.Role.EDITOR
                        },
                    )
                invite.status = Status.ACCEPTED
                invite.accepted_by = user
                invite.accepted_at = timezone.now()
                invite.save(update_fields=["status", "accepted_by", "accepted_at"])
                return member
            # raising inside the block would roll this save back
            invite.status = Status.EXPIRED
            invite.save(update_fields=["status"])
        raise ValidationError(MSG_INVITE_INVALID)
