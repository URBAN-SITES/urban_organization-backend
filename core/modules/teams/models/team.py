from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models.base import BaseModel
from core.modules.kanban.models.sector import Sector, SectorMember
from core.modules.organizations.models.organization import Organization


# [P2-A] One level only, no sub-teams. `owner` is the DBML `created_by`.
class Team(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="teams",
        verbose_name=_("organization"),
    )
    name = models.CharField(_("name"), max_length=255)
    description = models.TextField(_("description"), blank=True)

    class Meta(BaseModel.Meta):
        verbose_name = _("team")
        verbose_name_plural = _("teams")
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="unique_team_name_per_org"
            )
        ]

    def __str__(self) -> str:
        return self.name


# [P2-A]
class TeamMember(models.Model):
    class Role(models.TextChoices):
        LEAD = "lead", _("lead")
        MEMBER = "member", _("member")

    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="members",
        verbose_name=_("team"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="team_memberships",
        verbose_name=_("user"),
    )
    role = models.CharField(_("role"), max_length=10, choices=Role, default=Role.MEMBER)
    joined_at = models.DateTimeField(_("joined at"), auto_now_add=True)

    class Meta:
        verbose_name = _("team member")
        verbose_name_plural = _("team members")
        constraints = [
            models.UniqueConstraint(fields=["team", "user"], name="unique_team_member")
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.team} ({self.role})"


# [P2-A] Gives a whole team access to a sector. Teams carry a sector role only.
class SectorTeam(models.Model):
    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        related_name="teams",
        verbose_name=_("sector"),
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="sectors",
        verbose_name=_("team"),
    )
    role = models.CharField(
        _("role"),
        max_length=10,
        choices=SectorMember.Role,
        default=SectorMember.Role.EDITOR,
    )

    class Meta:
        verbose_name = _("sector team")
        verbose_name_plural = _("sector teams")
        constraints = [
            models.UniqueConstraint(
                fields=["sector", "team"], name="unique_sector_team"
            )
        ]

    def __str__(self) -> str:
        return f"{self.team} -> {self.sector} ({self.role})"
