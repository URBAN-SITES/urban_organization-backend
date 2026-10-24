import hashlib
import os
import secrets

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from core.models.user import User
from core.modules.invitations.models.invite import OrganizationInvite
from core.modules.invitations.response_messages import (
    MSG_INVITE_ACCEPTED,
    MSG_INVITE_ALREADY_MEMBER,
    MSG_INVITE_ALREADY_PENDING,
    MSG_INVITE_EXPIRED,
    MSG_INVITE_INVALID,
    MSG_INVITE_NOT_PENDING,
    MSG_INVITE_RECEIVED,
    MSG_INVITE_USED,
    MSG_INVITE_WRONG_ACCOUNT,
)
from core.modules.invitations.tasks.invite import send_invite_email_task
from core.modules.kanban.models.sector import Sector, SectorMember
from core.modules.notifications.services.notification import NotificationService
from core.modules.organizations.models.organization import OrganizationMember
from core.modules.organizations.services.organization import OrganizationService

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
Status = OrganizationInvite.Status


def _hash(token: str) -> str:
    # the token has 256 bits of entropy, so a plain SHA-256 is enough (and indexable)
    return hashlib.sha256(token.encode()).hexdigest()


def _error(code: str, message=MSG_INVITE_INVALID, **extra) -> ValidationError:
    """400 with a machine-readable `code` so the app can say what actually went wrong."""
    return ValidationError({"detail": str(message), "code": code, **extra})


def _mask(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:1]}***@{domain}"


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
                lambda: send_invite_email_task.delay(email, organization.name, link),
                robust=True,
            )
            target = User.objects.filter(email__iexact=email, is_active=True).first()
            if target is not None and target.pk != user.pk:
                NotificationService.notify(
                    target,
                    str(MSG_INVITE_RECEIVED),
                    organization.name,
                    {
                        "event": "organization.invited",
                        "organization_id": str(organization.pk),
                        "invite_id": str(invite.pk),
                    },
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
        return InviteService._accept(user, token_hash=_hash(token))

    @staticmethod
    def accept_by_id(user: User, invite_id) -> OrganizationMember:
        """In-app acceptance of an invitation listed in `list_mine` (no e-mail token)."""
        return InviteService._accept(user, id=invite_id)

    @staticmethod
    def decline(user: User, invite_id) -> None:
        updated = OrganizationInvite.objects.filter(
            id=invite_id,
            email__iexact=user.email,
            status=Status.PENDING,
            expires_at__gt=timezone.now(),
        ).update(status=Status.REVOKED)
        if not updated:
            raise ValidationError(MSG_INVITE_INVALID)

    @staticmethod
    def _accept(user: User, **lookup) -> OrganizationMember:
        with transaction.atomic():
            invite = (
                OrganizationInvite.objects.select_for_update()
                .select_related("organization")
                .filter(**lookup)
                .first()
            )
            # An unknown token or id says nothing. The reason is only given to someone holding
            # the token or to the invited e-mail itself.
            if invite is None:
                raise _error("invite_invalid")
            invitee = invite.email.lower() == user.email.lower()
            if "token_hash" in lookup and not invitee:
                raise _error(
                    "invite_wrong_account",
                    MSG_INVITE_WRONG_ACCOUNT,
                    invited_email=_mask(invite.email),
                )
            if not invitee:
                raise _error("invite_invalid")
            if invite.status != Status.PENDING or not invite.organization.is_active:
                raise _error(
                    "invite_used",
                    MSG_INVITE_USED,
                    organization_id=str(invite.organization_id),
                )
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
                # The inviter may have left the organization since sending it.
                if (
                    invite.invited_by_id != user.pk
                    and invite.invited_by.is_active
                    and OrganizationMember.objects.filter(
                        organization=invite.organization, user_id=invite.invited_by_id
                    ).exists()
                ):
                    NotificationService.notify(
                        invite.invited_by,
                        str(MSG_INVITE_ACCEPTED),
                        invite.organization.name,
                        {
                            "event": "organization.invite_accepted",
                            "organization_id": str(invite.organization_id),
                            "invite_id": str(invite.pk),
                            "accepted_by_id": str(user.pk),
                        },
                    )
                return member
            # raising inside the block would roll this save back
            invite.status = Status.EXPIRED
            invite.save(update_fields=["status"])
        raise _error("invite_expired", MSG_INVITE_EXPIRED)

    @staticmethod
    def preview(token: str) -> dict:
        """What the e-mailed link is about, before logging in (token holders only)."""
        invite = (
            OrganizationInvite.objects.select_related("organization")
            .filter(token_hash=_hash(token))
            .first()
        )
        if invite is None:
            raise _error("invite_invalid")
        if invite.status != Status.PENDING or not invite.organization.is_active:
            raise _error("invite_used", MSG_INVITE_USED)
        if invite.expires_at <= timezone.now():
            raise _error("invite_expired", MSG_INVITE_EXPIRED)
        return {
            "organization_name": invite.organization.name,
            "role": invite.role,
            "email": invite.email,
            "expires_at": invite.expires_at,
            "has_account": User.objects.filter(
                email__iexact=invite.email, is_active=True
            ).exists(),
        }
