from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models.base import BaseModel
from core.modules.organizations.models.organization import Organization


# [P1] The sector is the "project" of the challenge: it holds the Kanban board.
class Sector(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="sectors",
        verbose_name=_("organization"),
    )
    name = models.CharField(_("name"), max_length=255)
    description = models.TextField(_("description"), blank=True)
    icon = models.CharField(_("icon"), max_length=50, blank=True)
    color = models.CharField(_("color"), max_length=20, blank=True)
    is_private = models.BooleanField(
        _("private"),
        default=True,
        help_text=_(
            "True: only participants see it. "
            "False: every organization member sees it as viewer."
        ),
    )
    archived_at = models.DateTimeField(_("archived at"), null=True, blank=True)
    # short key that prefixes task codes (DEV-12); task_counter numbers the tasks
    identifier = models.CharField(_("identifier"), max_length=6, blank=True)
    task_counter = models.PositiveIntegerField(_("task counter"), default=0)
    # done tasks leave the board after this many days (null: never)
    auto_archive_days = models.PositiveSmallIntegerField(
        _("auto archive after (days)"), null=True, blank=True
    )

    class Meta(BaseModel.Meta):
        verbose_name = _("sector")
        verbose_name_plural = _("sectors")

    def __str__(self) -> str:
        return self.name


# [P1]
class SectorMember(models.Model):
    class Role(models.TextChoices):
        MANAGER = "manager", _("manager")
        EDITOR = "editor", _("editor")
        VIEWER = "viewer", _("viewer")

    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        related_name="members",
        verbose_name=_("sector"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sector_memberships",
        verbose_name=_("user"),
    )
    role = models.CharField(_("role"), max_length=10, choices=Role, default=Role.EDITOR)

    class Meta:
        verbose_name = _("sector member")
        verbose_name_plural = _("sector members")
        constraints = [
            models.UniqueConstraint(
                fields=["sector", "user"], name="unique_sector_member"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.sector} ({self.role})"


class SectorFavorite(models.Model):
    """A sector the user pinned; shown first in the sidebar and on the dashboard."""

    sector = models.ForeignKey(
        Sector,
        on_delete=models.CASCADE,
        related_name="favorites",
        verbose_name=_("sector"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorite_sectors",
        verbose_name=_("user"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("favorite sector")
        verbose_name_plural = _("favorite sectors")
        constraints = [
            models.UniqueConstraint(
                fields=["sector", "user"], name="unique_sector_favorite"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.sector_id}"
