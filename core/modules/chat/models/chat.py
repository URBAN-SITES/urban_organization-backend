import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.modules.organizations.models.organization import Organization
from core.modules.teams.models.team import Team


# [P2-H] Depends on P2-A. The org "General" channel and each team channel are
# created by services (organization/team create), not by triggers.
class ChatChannel(models.Model):
    class Kind(models.TextChoices):
        ORGANIZATION = "organization", _("organization")
        TEAM = "team", _("team")
        DIRECT = "direct", _("direct")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="chat_channels",
        verbose_name=_("organization"),
    )
    kind = models.CharField(_("kind"), max_length=15, choices=Kind)
    team = models.OneToOneField(
        Team,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="chat_channel",
        verbose_name=_("team"),
    )
    direct_key = models.CharField(
        _("direct key"),
        max_length=100,
        blank=True,
        help_text=_("Direct only: 'smallerUserId:largerUserId'."),
    )
    name = models.CharField(_("name"), max_length=255, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("chat channel")
        verbose_name_plural = _("chat channels")
        constraints = [
            models.CheckConstraint(
                name="chat_channel_team_only_for_team_kind",
                condition=models.Q(kind="team", team__isnull=False)
                | models.Q(~models.Q(kind="team"), team__isnull=True),
            ),
            models.CheckConstraint(
                name="chat_channel_direct_key_only_for_direct_kind",
                condition=models.Q(kind="direct", direct_key__gt="")
                | models.Q(~models.Q(kind="direct"), direct_key=""),
            ),
            models.UniqueConstraint(
                fields=["organization"],
                condition=models.Q(kind="organization"),
                name="unique_org_channel_per_org",
            ),
            models.UniqueConstraint(
                fields=["organization", "direct_key"],
                condition=models.Q(kind="direct"),
                name="unique_direct_channel_per_pair",
            ),
        ]

    def __str__(self) -> str:
        return self.name or f"{self.kind} channel"


# [P2-H] Participants and unread tracking (`last_read_at`).
class ChatChannelMember(models.Model):
    channel = models.ForeignKey(
        ChatChannel,
        on_delete=models.CASCADE,
        related_name="members",
        verbose_name=_("channel"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_memberships",
        verbose_name=_("user"),
    )
    last_read_at = models.DateTimeField(_("last read at"), null=True, blank=True)
    joined_at = models.DateTimeField(_("joined at"), auto_now_add=True)

    class Meta:
        verbose_name = _("chat channel member")
        verbose_name_plural = _("chat channel members")
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "user"], name="unique_chat_channel_member"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} in {self.channel}"


# [P2-H] Soft delete via `deleted_at`.
class ChatMessage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel = models.ForeignKey(
        ChatChannel,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name=_("channel"),
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_messages",
        verbose_name=_("author"),
    )
    content = models.TextField(_("content"), blank=True)
    reply_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
        verbose_name=_("reply to"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    edited_at = models.DateTimeField(_("edited at"), null=True, blank=True)
    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True)

    class Meta:
        verbose_name = _("chat message")
        verbose_name_plural = _("chat messages")
        ordering = ["created_at"]
        indexes = [models.Index(fields=["channel", "created_at"])]

    def __str__(self) -> str:
        return f"{self.author}: {self.content[:30]}"
