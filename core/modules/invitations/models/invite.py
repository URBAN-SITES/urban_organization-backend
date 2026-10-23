import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.modules.organizations.models.organization import (
    Organization,
    OrganizationMember,
)

INVITE_LIFETIME = timedelta(days=7)


def default_invite_expiry():
    return timezone.now() + INVITE_LIFETIME


# [P2-D] Store only the token hash (like OneTimeCode); the raw token goes by e-mail.
class OrganizationInvite(models.Model):
    sectors = models.ManyToManyField(
        "core.Sector", blank=True, related_name="organization_invites"
    )

    class Status(models.TextChoices):
        PENDING = "pending", _("pending")
        ACCEPTED = "accepted", _("accepted")
        REVOKED = "revoked", _("revoked")
        EXPIRED = "expired", _("expired")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="invites",
        verbose_name=_("organization"),
    )
    email = models.EmailField(_("e-mail"))
    role = models.CharField(
        _("role"),
        max_length=10,
        choices=OrganizationMember.Role,
        default=OrganizationMember.Role.MEMBER,
    )
    token_hash = models.CharField(_("token hash"), max_length=128, unique=True)
    status = models.CharField(
        _("status"), max_length=10, choices=Status, default=Status.PENDING
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_invites",
        verbose_name=_("invited by"),
    )
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_invites",
        verbose_name=_("accepted by"),
    )
    expires_at = models.DateTimeField(_("expires at"), default=default_invite_expiry)
    accepted_at = models.DateTimeField(_("accepted at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("organization invite")
        verbose_name_plural = _("organization invites")
        ordering = ["-created_at"]
        constraints = [
            # one pending invite per e-mail in each organization
            models.UniqueConstraint(
                Lower("email"),
                "organization",
                condition=models.Q(status="pending"),
                name="unique_pending_invite_per_email",
            ),
            models.CheckConstraint(
                condition=~models.Q(role="owner"), name="invite_role_not_owner"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.email} -> {self.organization} ({self.status})"
