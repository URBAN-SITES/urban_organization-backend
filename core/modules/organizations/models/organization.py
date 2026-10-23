from uuid import uuid4

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models.base import BaseModel


def default_organization_slug():
    return f"workspace-{uuid4().hex}"


# [P1] `owner` (from BaseModel) is the DBML `created_by`.
class Organization(BaseModel):
    class TeamSize(models.TextChoices):
        SOLO = "1", _("Just me")
        SMALL = "2-10", _("2 to 10 people")
        MEDIUM = "11-50", _("11 to 50 people")
        LARGE = "51-200", _("51 to 200 people")
        ENTERPRISE = "201+", _("More than 200 people")

    slug = models.SlugField(
        max_length=63,
        unique=True,
        default=default_organization_slug,
        validators=[
            RegexValidator(
                r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
                "Use lowercase letters, numbers and single hyphens.",
            )
        ],
    )
    team_size = models.CharField(
        _("team size"), max_length=10, choices=TeamSize, blank=True, default=""
    )
    name = models.CharField(_("name"), max_length=255)
    description = models.TextField(_("description"), blank=True)
    logo_url = models.URLField(_("logo url"), blank=True)
    is_personal = models.BooleanField(
        _("personal"),
        default=False,
        help_text=_("Created automatically for each user on registration."),
    )

    class Meta(BaseModel.Meta):
        verbose_name = _("organization")
        verbose_name_plural = _("organizations")

    def __str__(self) -> str:
        return self.name


# [P1]
class OrganizationMember(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", _("owner")
        ADMIN = "admin", _("admin")
        MEMBER = "member", _("member")
        VIEWER = "viewer", _("viewer")

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="members",
        verbose_name=_("organization"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organization_memberships",
        verbose_name=_("user"),
    )
    role = models.CharField(_("role"), max_length=10, choices=Role, default=Role.MEMBER)
    joined_at = models.DateTimeField(_("joined at"), auto_now_add=True)

    class Meta:
        verbose_name = _("organization member")
        verbose_name_plural = _("organization members")
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"], name="unique_organization_member"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.organization} ({self.role})"
