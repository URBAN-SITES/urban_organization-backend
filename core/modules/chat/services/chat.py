import logging
from datetime import UTC, datetime

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import (
    NotFound,
    PermissionDenied,
    ValidationError,
)

from core.models.user import User
from core.modules.chat import presence
from core.modules.chat.models.chat import (
    ChatChannel,
    ChatChannelMember,
    ChatChannelTeam,
    ChatMessage,
)
from core.modules.chat.response_messages import (
    MSG_CHAT_DIRECT_WITH_SELF,
    MSG_CHAT_EMPTY,
    MSG_CHAT_MESSAGE_DELETED,
    MSG_CHAT_MESSAGE_FORBIDDEN,
    MSG_CHAT_REPLY_INVALID,
    MSG_CHAT_TASK_INVALID,
    MSG_CHAT_TEAMS_INVALID,
    MSG_CHAT_TEAMS_NOT_ALLOWED,
    MSG_CHAT_USER_NOT_IN_ORGANIZATION,
)
from core.modules.kanban.models.sector import Sector
from core.modules.kanban.services.sector import SectorService
from core.modules.kanban.services.task import TaskService
from core.modules.notifications.services.notification import NotificationService
from core.modules.organizations.models.organization import (
    Organization,
    OrganizationMember,
)
from core.modules.organizations.services.organization import OrganizationService
from core.modules.teams.models.team import Team, TeamMember
from core.modules.uploads.services.attachment import AttachmentService
from core.websockets.consumers import send_to_user

logger = logging.getLogger(__name__)
EPOCH = datetime.fromtimestamp(0, tz=UTC)
Kind = ChatChannel.Kind
ORG_ADMINS = (OrganizationMember.Role.OWNER, OrganizationMember.Role.ADMIN)


class ChatService:
    """Access is derived from membership: organization -> General, team -> its team
    channel, teams -> any linked team, sector -> anyone with sector access, direct ->
    its two participants. No separate ACL."""

    # channels -----------------------------------------------------------

    @staticmethod
    def list_channels(user: User, organization_id) -> list[dict]:
        organization = OrganizationService.get_membership(
            user, organization_id
        ).organization
        channels = [ChatService._organization_channel(organization)]
        channels += [
            ChatService._sector_channel(sector)
            for sector in SectorService.list_for(user, organization_id)
        ]
        teams = Team.objects.filter(
            organization=organization, is_active=True, members__user=user
        ).order_by("name")
        channels += [ChatService._team_channel(team) for team in teams]
        channels += list(
            ChatChannel.objects.filter(
                organization=organization,
                kind=Kind.TEAMS,
                linked_teams__team__is_active=True,
                linked_teams__team__members__user=user,
            ).distinct()
        )
        channels += list(
            ChatChannel.objects.filter(
                organization=organization,
                kind=Kind.DIRECT,
                members__user=user,
            )
        )
        described = [ChatService._describe(user, channel) for channel in channels]
        # most recent activity first; channels without messages last
        described.sort(
            key=lambda c: (
                c["last_message"]["created_at"] if c["last_message"] else EPOCH
            ),
            reverse=True,
        )
        return described

    @staticmethod
    def open_direct(user: User, organization_id, other_id) -> dict:
        organization = OrganizationService.get_membership(
            user, organization_id
        ).organization
        if str(other_id) == str(user.pk):
            raise ValidationError(MSG_CHAT_DIRECT_WITH_SELF)
        if not OrganizationMember.objects.filter(
            organization=organization, user_id=other_id
        ).exists():
            raise ValidationError(MSG_CHAT_USER_NOT_IN_ORGANIZATION)
        key = ":".join(sorted([str(user.pk), str(other_id)]))
        with transaction.atomic():
            channel, _created = ChatChannel.objects.get_or_create(
                organization=organization, kind=Kind.DIRECT, direct_key=key
            )
            for user_id in (user.pk, other_id):
                ChatChannelMember.objects.get_or_create(
                    channel=channel, user_id=user_id
                )
        return ChatService._describe(user, channel)

    @staticmethod
    @transaction.atomic
    def create_teams_channel(
        user: User, organization_id, team_ids: list, name: str = ""
    ) -> dict:
        """A conversation shared by two or more teams (members = union of theirs)."""
        membership = OrganizationService.get_membership(user, organization_id)
        teams = list(
            Team.objects.filter(
                id__in=set(team_ids),
                organization_id=organization_id,
                is_active=True,
            )
        )
        if len(teams) < 2 or len(teams) != len(set(team_ids)):
            raise ValidationError(MSG_CHAT_TEAMS_INVALID)
        is_admin = membership.role in ORG_ADMINS
        if (
            not is_admin
            and not TeamMember.objects.filter(team__in=teams, user=user).exists()
        ):
            raise PermissionDenied(MSG_CHAT_TEAMS_NOT_ALLOWED)
        channel = ChatChannel.objects.create(
            organization_id=organization_id,
            kind=Kind.TEAMS,
            name=name or " & ".join(sorted(team.name for team in teams))[:255],
        )
        ChatChannelTeam.objects.bulk_create(
            ChatChannelTeam(channel=channel, team=team) for team in teams
        )
        return ChatService._describe(user, channel)

    @staticmethod
    def mark_read(user: User, channel_id) -> None:
        channel = ChatService.get_channel(user, channel_id)
        ChatChannelMember.objects.update_or_create(
            channel=channel, user=user, defaults={"last_read_at": timezone.now()}
        )

    @staticmethod
    def get_channel(user: User, channel_id) -> ChatChannel:
        channel = (
            ChatChannel.objects.select_related("organization", "team", "sector")
            .filter(id=channel_id, organization__is_active=True)
            .first()
        )
        if channel is None or not ChatService.can_access(user, channel):
            raise NotFound()
        return channel

    @staticmethod
    def can_access(user: User, channel: ChatChannel) -> bool:
        if not OrganizationMember.objects.filter(
            organization_id=channel.organization_id, user=user
        ).exists():
            return False
        if channel.kind == Kind.ORGANIZATION:
            return True
        if channel.kind == Kind.SECTOR:
            return channel.sector.is_active and (
                SectorService.effective_role(user, channel.sector) is not None
            )
        if channel.kind == Kind.TEAM:
            return TeamMember.objects.filter(
                team_id=channel.team_id, team__is_active=True, user=user
            ).exists()
        if channel.kind == Kind.TEAMS:
            return TeamMember.objects.filter(
                team__chat_links__channel=channel, team__is_active=True, user=user
            ).exists()
        return ChatChannelMember.objects.filter(channel=channel, user=user).exists()

    @staticmethod
    def accessible_channel_ids(user: User, organization_id) -> list:
        """Existing channels of the organization the user can open (for search)."""
        channels = ChatChannel.objects.filter(
            organization_id=organization_id
        ).select_related("sector")
        return [c.pk for c in channels if ChatService.can_access(user, c)]

    @staticmethod
    def online_members(user: User, organization_id) -> list:
        OrganizationService.get_membership(user, organization_id)
        member_ids = OrganizationMember.objects.filter(
            organization_id=organization_id
        ).values_list("user_id", flat=True)
        return presence.online_ids(list(member_ids))

    @staticmethod
    def typing_recipients(user: User, channel_id) -> list:
        """Who should see "<user> is typing"; empty when the user has no access."""
        try:
            channel = ChatService.get_channel(user, channel_id)
        except NotFound, DjangoValidationError:  # unknown or malformed id
            return []
        return [uid for uid in ChatService._recipients(channel) if uid != user.pk]

    # messages -----------------------------------------------------------

    @staticmethod
    def list_messages(user: User, channel_id, after=None):
        channel = ChatService.get_channel(user, channel_id)
        messages = (
            ChatMessage.objects.filter(channel=channel)
            .select_related("author", "task__status")
            .prefetch_related("mentions", "attachments")
        )
        if after is not None:
            messages = messages.filter(created_at__gt=after)
        return messages.order_by("-created_at", "-id")

    @staticmethod
    def send(
        user: User,
        channel_id,
        content: str = "",
        reply_to_id=None,
        task_id=None,
        mention_ids=(),
        files=(),
    ) -> ChatMessage:
        channel = ChatService.get_channel(user, channel_id)
        if not content.strip() and not files:
            raise ValidationError(MSG_CHAT_EMPTY)
        reply_to = None
        if reply_to_id:
            reply_to = ChatMessage.objects.filter(
                id=reply_to_id, channel=channel
            ).first()
            if reply_to is None:
                raise ValidationError(MSG_CHAT_REPLY_INVALID)
        task = ChatService._citable_task(user, task_id)
        mentioned = ChatService._mentionable(user, channel, mention_ids)
        AttachmentService.validate(files)
        stored = AttachmentService.upload_all(
            files, folder=f"chat/{channel.organization_id}"
        )
        try:
            with transaction.atomic():
                message = ChatMessage.objects.create(
                    channel=channel,
                    author=user,
                    content=content,
                    reply_to=reply_to,
                    task=task,
                )
                message.mentions.set(mentioned)
                AttachmentService.create_for_message(user, message, stored)
                ChatChannelMember.objects.update_or_create(
                    channel=channel,
                    user=user,
                    defaults={"last_read_at": timezone.now()},
                )
                ChatService._broadcast(channel, "chat.message", message)
        except Exception:
            AttachmentService.discard(stored)
            raise
        ChatService._notify_recipients(user, channel, message, mentioned)
        return message

    @staticmethod
    def edit(user: User, message_id, content: str) -> ChatMessage:
        message, channel = ChatService._get_message(user, message_id)
        if message.author_id != user.pk:
            raise PermissionDenied(MSG_CHAT_MESSAGE_FORBIDDEN)
        if message.deleted_at:
            raise ValidationError(MSG_CHAT_MESSAGE_DELETED)
        message.content = content
        message.edited_at = timezone.now()
        message.save(update_fields=["content", "edited_at"])
        ChatService._broadcast(channel, "chat.message_updated", message)
        return message

    @staticmethod
    def delete(user: User, message_id) -> None:
        """Soft delete; the author, or an org owner/admin (not in direct chats)."""
        message, channel = ChatService._get_message(user, message_id)
        if message.author_id != user.pk:
            is_moderator = channel.kind != Kind.DIRECT and (
                OrganizationMember.objects.filter(
                    organization_id=channel.organization_id,
                    user=user,
                    role__in=ORG_ADMINS,
                ).exists()
            )
            if not is_moderator:
                raise PermissionDenied(MSG_CHAT_MESSAGE_FORBIDDEN)
        if message.deleted_at:
            return
        message.content = ""
        message.deleted_at = timezone.now()
        message.save(update_fields=["content", "deleted_at"])
        AttachmentService.delete_for_message(message)
        ChatService._broadcast(channel, "chat.message_deleted", message)

    # helpers ------------------------------------------------------------

    @staticmethod
    def _citable_task(user: User, task_id):
        if not task_id:
            return None
        try:
            task, _sector, _role = TaskService.get_task(user, task_id)
        except NotFound, PermissionDenied:
            raise ValidationError(MSG_CHAT_TASK_INVALID)
        return task

    @staticmethod
    def _mentionable(user: User, channel: ChatChannel, mention_ids) -> list[User]:
        """Only people who can read the channel are mentioned; others are ignored."""
        if not mention_ids:
            return []
        users = User.objects.filter(id__in=set(mention_ids), is_active=True).exclude(
            pk=user.pk
        )
        return [u for u in users if ChatService.can_access(u, channel)]

    @staticmethod
    def _notify_recipients(user, channel, message, mentioned) -> None:
        mentioned_ids = {target.pk for target in mentioned}
        recipients = User.objects.filter(
            id__in=ChatService._recipients(channel), is_active=True
        ).exclude(pk=user.pk)
        for target in recipients:
            NotificationService.notify(
                target,
                (
                    f"{user.get_short_name()} mentioned you"
                    if target.pk in mentioned_ids
                    else f"{user.get_short_name()} sent a message"
                ),
                message.content[:200],
                {
                    "event": "chat.mentioned",
                    "channel_id": str(channel.pk),
                    "message_id": str(message.pk),
                    "organization_id": str(channel.organization_id),
                },
            )

    @staticmethod
    def _get_message(user: User, message_id):
        message = (
            ChatMessage.objects.select_related(
                "channel__organization", "channel__team", "channel__sector", "author"
            )
            .filter(id=message_id)
            .first()
        )
        if message is None or not ChatService.can_access(user, message.channel):
            raise NotFound()
        return message, message.channel

    @staticmethod
    def _organization_channel(organization: Organization) -> ChatChannel:
        channel, _created = ChatChannel.objects.get_or_create(
            organization=organization,
            kind=Kind.ORGANIZATION,
            defaults={"name": "General"},
        )
        return channel

    @staticmethod
    def _sector_channel(sector: Sector) -> ChatChannel:
        channel, _created = ChatChannel.objects.get_or_create(
            sector=sector,
            defaults={
                "organization_id": sector.organization_id,
                "kind": Kind.SECTOR,
                "name": sector.name,
            },
        )
        if channel.name != sector.name:  # follow sector renames
            channel.name = sector.name
            channel.save(update_fields=["name"])
        return channel

    @staticmethod
    def _team_channel(team: Team) -> ChatChannel:
        channel, _created = ChatChannel.objects.get_or_create(
            team=team,
            defaults={
                "organization_id": team.organization_id,
                "kind": Kind.TEAM,
                "name": team.name,
            },
        )
        return channel

    @staticmethod
    def _describe(user: User, channel: ChatChannel) -> dict:
        read = ChatChannelMember.objects.filter(channel=channel, user=user).first()
        visible = ChatMessage.objects.filter(channel=channel, deleted_at__isnull=True)
        unread = visible.exclude(author=user)
        if read and read.last_read_at:
            unread = unread.filter(created_at__gt=read.last_read_at)
        last = visible.select_related("author").order_by("-created_at").first()
        name, online = channel.name, None
        if channel.kind == Kind.DIRECT:
            other = (
                ChatChannelMember.objects.filter(channel=channel)
                .exclude(user=user)
                .select_related("user")
                .first()
            )
            name = other.user.name if other else ""
            online = presence.is_online(other.user_id) if other else False
        return {
            "id": channel.id,
            "kind": channel.kind,
            "name": name,
            "team_id": channel.team_id,
            "team_ids": list(channel.linked_teams.values_list("team_id", flat=True)),
            "sector_id": channel.sector_id,
            "unread_count": unread.count(),
            "member_count": len(ChatService._recipients(channel)),
            "online": online,
            "last_message": None
            if last is None
            else {
                "id": last.id,
                "author_name": last.author.name,
                "content": last.content,
                "has_attachments": last.attachments.exists(),
                "created_at": last.created_at,
            },
        }

    @staticmethod
    def _recipients(channel: ChatChannel) -> list:
        if channel.kind == Kind.ORGANIZATION:
            members = OrganizationMember.objects.filter(
                organization_id=channel.organization_id
            )
        elif channel.kind == Kind.SECTOR:
            return list(SectorService.participant_ids(channel.sector))
        elif channel.kind == Kind.TEAM:
            members = TeamMember.objects.filter(team_id=channel.team_id)
        elif channel.kind == Kind.TEAMS:
            members = TeamMember.objects.filter(
                team__chat_links__channel=channel, team__is_active=True
            )
        else:
            members = ChatChannelMember.objects.filter(channel=channel)
        return list(set(members.values_list("user_id", flat=True)))

    @staticmethod
    def _broadcast(channel: ChatChannel, event: str, message: ChatMessage) -> None:
        """Real-time push to every participant once the transaction commits."""
        from core.modules.chat.serializers.chat import ChatMessageSerializer

        payload = {
            "type": event,
            "channel_id": str(channel.pk),
            "message": ChatMessageSerializer(message).data,
        }
        recipients = ChatService._recipients(channel)

        def push():
            for user_id in recipients:
                try:
                    send_to_user(user_id, payload)
                except Exception:  # best-effort: the message is already saved
                    logger.exception("chat push failed")

        transaction.on_commit(push)
