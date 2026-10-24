"""Explicit application capabilities. The authenticated actor never comes from Gemini."""

import json
from dataclasses import dataclass
from functools import cache

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.utils.encoders import JSONEncoder

from core.modules.ai.response_messages import (
    MSG_AI_INVALID_ARGUMENTS,
    MSG_AI_UNKNOWN_ACTION,
)
from core.modules.ai.serializers.actions import (
    DateRangeSerializer,
    DraftTaskSerializer,
    DriveSearchSerializer,
    MessageSerializer,
    PageSerializer,
    ReportSerializer,
    SearchSerializer,
    validate_input,
)
from core.modules.ai.services.quick_task import draft_task
from core.modules.calendar_sync.serializers.drive import DriveAttachSerializer
from core.modules.calendar_sync.services.drive import GoogleDriveService
from core.modules.calendar_sync.services.google import GoogleCalendarService
from core.modules.calendar_sync.services.tasks import TaskCalendarService
from core.modules.chat.serializers.chat import (
    ChatChannelSerializer,
    ChatDirectOpenSerializer,
    ChatMessageEditSerializer,
    ChatMessageSerializer,
    ChatTeamsChannelSerializer,
)
from core.modules.chat.services.chat import ChatService
from core.modules.invitations.serializers.invite import (
    InviteAcceptedSerializer,
    InviteAcceptSerializer,
    InviteCreateSerializer,
    InviteSerializer,
)
from core.modules.invitations.services.invite import InviteService
from core.modules.kanban.serializers.sector import (
    SectorMemberAddSerializer,
    SectorMemberRoleSerializer,
    SectorMemberSerializer,
    SectorSerializer,
    SectorTeamAddSerializer,
    SectorTeamSerializer,
    StatusSerializer,
)
from core.modules.kanban.serializers.task import (
    ChecklistItemSerializer,
    CommentSerializer,
    CommentWriteSerializer,
    ResourceLinkSerializer,
    TaskCreateSerializer,
    TaskMoveSerializer,
    TaskSerializer,
    TaskUpdateSerializer,
)
from core.modules.kanban.services.calendar import CalendarService
from core.modules.kanban.services.dashboard import DashboardService
from core.modules.kanban.services.files import FileService
from core.modules.kanban.services.item import (
    ChecklistService,
    CommentService,
    LinkService,
)
from core.modules.kanban.services.reports import ReportService
from core.modules.kanban.services.sector import SectorService
from core.modules.kanban.services.status import StatusService
from core.modules.kanban.services.task import TaskService
from core.modules.organizations.serializers.organization import (
    OrganizationMemberAddSerializer,
    OrganizationMemberRoleSerializer,
    OrganizationMemberSerializer,
    OrganizationSerializer,
)
from core.modules.organizations.services.organization import OrganizationService
from core.modules.search.serializers.search import SearchResultSerializer
from core.modules.search.services.search import SearchService
from core.modules.teams.serializers.team import (
    TeamMemberAddSerializer,
    TeamMemberRoleSerializer,
    TeamMemberSerializer,
    TeamSerializer,
)
from core.modules.teams.services.team import TeamService
from core.modules.user_settings.serializers.user_settings import UserSettingsSerializer
from core.modules.user_settings.services.user_settings import UserSettingsService


def json_value(value):
    return json.loads(json.dumps(value, cls=JSONEncoder))


def field_schema(field):
    if isinstance(field, serializers.ListField):
        schema = {"type": "array", "items": field_schema(field.child)}
    elif isinstance(field, serializers.BooleanField):
        schema = {"type": "boolean"}
    elif isinstance(field, serializers.IntegerField):
        schema = {"type": "integer"}
    elif isinstance(field, (serializers.FloatField, serializers.DecimalField)):
        schema = {"type": "number"}
    else:
        schema = {"type": "string"}
    if isinstance(field, serializers.ChoiceField):
        schema["enum"] = list(field.choices)
        if all(isinstance(choice, int) for choice in field.choices):
            schema["type"] = "integer"
    if isinstance(field, (serializers.UUIDField, serializers.PrimaryKeyRelatedField)):
        schema["description"] = (
            "Existing resource UUID; resolve through list/search first."
        )
    elif isinstance(field, serializers.DateTimeField):
        schema["description"] = "ISO 8601 date-time with explicit UTC offset."
    elif isinstance(field, serializers.DateField):
        schema["description"] = "YYYY-MM-DD"
    if field.help_text:
        schema["description"] = str(field.help_text)
    for attr, key in (
        ("max_length", "maxItems" if schema["type"] == "array" else "maxLength"),
        ("min_value", "minimum"),
        ("max_value", "maximum"),
    ):
        value = getattr(field, attr, None)
        if value is not None:
            schema[key] = value
    if field.allow_null:
        schema["type"] = [schema["type"], "null"]
    return schema


def input_schema(serializer_class, partial=False):
    fields = serializer_class().fields
    return {
        "type": "object",
        "properties": {
            n: field_schema(f) for n, f in fields.items() if not f.read_only
        },
        "required": [
            n
            for n, f in fields.items()
            if f.required and not f.read_only and not partial
        ],
        "additionalProperties": False,
    }


@dataclass(frozen=True)
class Action:
    name: str
    description: str
    handler: object
    ids: tuple = ()
    input: object = None
    output: object = None
    many: bool = False
    write: bool = False
    partial: bool = False

    def id_field(self, key):
        # Memberships and sector/team joins use integer PKs; domain entities use UUIDs.
        if key == "member_id" or (
            self.name == "sector_team_remove" and key == "link_id"
        ):
            return serializers.IntegerField(min_value=1)
        return serializers.UUIDField()

    def describe(self):
        properties = {key: field_schema(self.id_field(key)) for key in self.ids}
        required = list(self.ids)
        if self.input:
            properties["data"] = input_schema(self.input, self.partial)
            required.append("data")
        if self.many:
            properties["page"] = input_schema(PageSerializer)
        return {
            "name": self.name,
            "description": self.description,
            "writes": self.write,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        }

    def execute(self, user, arguments):
        allowed = (
            set(self.ids)
            | ({"data"} if self.input else set())
            | ({"page"} if self.many else set())
        )
        if not isinstance(arguments, dict) or set(arguments) - allowed:
            raise ValidationError(MSG_AI_INVALID_ARGUMENTS)
        ids = []
        for key in self.ids:
            try:
                ids.append(self.id_field(key).run_validation(arguments.get(key)))
            except ValidationError as error:
                # Name the field so the model can fix the argument instead of looping.
                raise ValidationError({key: error.detail}) from None
        data = (
            validate_input(self.input, arguments.get("data", {}), partial=self.partial)
            if self.input
            else {}
        )
        page = (
            validate_input(PageSerializer, arguments.get("page", {}))
            if self.many
            else None
        )
        value = self.handler(user, *ids, **data)
        if self.many:
            offset, limit = page["offset"], page["limit"]
            rows = list(value[offset : offset + limit + 1])
            more = len(rows) > limit
            rows = rows[:limit]
            value = {
                "results": self.output(rows, many=True).data if self.output else rows,
                "next_offset": offset + limit if more else None,
            }
        elif self.output:
            value = self.output(value).data
        elif value is None:
            value = {"completed": True}
        return json_value(value)


def organization_detail(user, organization_id):
    membership = OrganizationService.get_membership(user, organization_id)
    membership.organization.current_role = membership.role
    return membership.organization


def send_message(user, channel_id, **data):
    return ChatService.send(
        user,
        channel_id,
        data.get("content", ""),
        reply_to_id=data.get("reply_to"),
        task_id=data.get("task"),
        mention_ids=data.get("mentions", []),
    )


def start_meet(user, channel_id):
    channel = ChatService.get_channel(user, channel_id)
    link = GoogleCalendarService.create_meet(user, channel.name or "Meet")
    # Return the created Meet even if posting to chat fails; never create it again.
    try:
        message = ChatService.send(user, channel_id, f"Join the meeting: {link}")
    except Exception:
        return {"url": link, "posted": False}
    return {"url": link, "posted": True, "message": ChatMessageSerializer(message).data}


def calendar_status(event):
    return {
        "synced": event is not None,
        "last_synced_at": event.last_synced_at if event else None,
    }


@cache
def registry():
    actions = {}

    def add(
        name,
        handler,
        *,
        ids=(),
        input=None,
        output=None,
        many=False,
        write=False,
        partial=False,
        description="",
    ):
        actions[name] = Action(
            name,
            description or name.replace("_", " "),
            handler,
            tuple(ids),
            input,
            output,
            many,
            write,
            partial,
        )

    def crud(
        domain,
        service,
        serializer,
        parents=(),
        key=None,
        create_input=None,
        update_input=None,
        create_dict=False,
        get=None,
    ):
        key = key or f"{domain}_id"
        add(
            f"{domain}_list",
            service.list_for,
            ids=parents,
            output=serializer,
            many=True,
        )
        if get:
            add(f"{domain}_get", get, ids=(*parents, key), output=serializer)
        create = (
            (lambda user, *ids, **data: service.create(user, *ids, data))
            if create_dict
            else service.create
        )
        add(
            f"{domain}_create",
            create,
            ids=parents,
            input=create_input or serializer,
            output=serializer,
            write=True,
        )
        add(
            f"{domain}_update",
            lambda user, *ids, **data: service.update(user, *ids, data),
            ids=(*parents, key),
            input=update_input or serializer,
            output=serializer,
            write=True,
            partial=True,
        )
        add(
            f"{domain}_delete",
            service.delete,
            ids=(*parents, key),
            write=True,
            description=f"Delete {domain}. May also delete its children; use only when explicitly requested.",
        )

    crud(
        "organization",
        OrganizationService,
        OrganizationSerializer,
        get=organization_detail,
    )
    crud("sector", SectorService, SectorSerializer, ("organization_id",))
    # Sector and task detail services use their own IDs, not their parents.
    for operation in ("update", "delete"):
        spec = actions[f"sector_{operation}"]
        actions[spec.name] = Action(
            spec.name,
            spec.description,
            spec.handler,
            ("sector_id",),
            spec.input,
            spec.output,
            spec.many,
            spec.write,
            spec.partial,
        )
    add(
        "sector_get",
        lambda u, sector_id: SectorService.get_sector(u, sector_id)[0],
        ids=("sector_id",),
        output=SectorSerializer,
    )
    add("sector_progress", SectorService.progress, ids=("sector_id",))
    crud("team", TeamService, TeamSerializer, ("organization_id",), get=TeamService.get)
    crud("status", StatusService, StatusSerializer, ("sector_id",))
    crud(
        "task",
        TaskService,
        TaskSerializer,
        ("sector_id",),
        create_input=TaskCreateSerializer,
        update_input=TaskUpdateSerializer,
        create_dict=True,
    )
    for operation in ("update", "delete"):
        spec = actions[f"task_{operation}"]
        actions[spec.name] = Action(
            spec.name,
            spec.description,
            spec.handler,
            ("task_id",),
            spec.input,
            spec.output,
            spec.many,
            spec.write,
            spec.partial,
        )
    add(
        "task_get",
        lambda u, task_id: TaskService.get_task(u, task_id)[0],
        ids=("task_id",),
        output=TaskSerializer,
    )
    add(
        "task_draft",
        lambda u, **data: draft_task(u, **data),
        input=DraftTaskSerializer,
        description="ALWAYS use this to create a task: it writes nothing and returns a draft card the user adjusts and confirms. Pass title, priority, due_date, due_time (HH:MM), sector_id (from workspace_snapshot) and assignees as plain names.",
    )
    add(
        "task_move",
        TaskService.move,
        ids=("task_id",),
        input=TaskMoveSerializer,
        output=TaskSerializer,
        write=True,
        description="Move or complete/reopen a task by choosing a column; preserves WIP and completion rules.",
    )
    crud(
        "checklist",
        ChecklistService,
        ChecklistItemSerializer,
        ("task_id",),
        key="item_id",
        create_dict=True,
    )

    for domain, service, parents, out, create, role, change in (
        (
            "organization_member",
            OrganizationService,
            ("organization_id",),
            OrganizationMemberSerializer,
            OrganizationMemberAddSerializer,
            OrganizationMemberRoleSerializer,
            OrganizationService.change_role,
        ),
        (
            "sector_member",
            SectorService,
            ("sector_id",),
            SectorMemberSerializer,
            SectorMemberAddSerializer,
            SectorMemberRoleSerializer,
            SectorService.change_member_role,
        ),
        (
            "team_member",
            TeamService,
            ("organization_id", "team_id"),
            TeamMemberSerializer,
            TeamMemberAddSerializer,
            TeamMemberRoleSerializer,
            TeamService.change_role,
        ),
    ):
        add(f"{domain}_list", service.list_members, ids=parents, output=out, many=True)
        add(
            f"{domain}_add",
            service.add_member,
            ids=parents,
            input=create,
            output=out,
            write=True,
        )
        add(
            f"{domain}_role",
            change,
            ids=(*parents, "member_id"),
            input=role,
            output=out,
            write=True,
        )
        add(
            f"{domain}_remove",
            service.remove_member,
            ids=(*parents, "member_id"),
            write=True,
        )
    add(
        "sector_team_list",
        SectorService.list_teams,
        ids=("sector_id",),
        output=SectorTeamSerializer,
        many=True,
    )
    add(
        "sector_team_add",
        SectorService.add_team,
        ids=("sector_id",),
        input=SectorTeamAddSerializer,
        output=SectorTeamSerializer,
        write=True,
    )
    add(
        "sector_team_remove",
        SectorService.remove_team,
        ids=("sector_id", "link_id"),
        write=True,
    )
    add(
        "invitation_list",
        InviteService.list_for_organization,
        ids=("organization_id",),
        output=InviteSerializer,
        many=True,
    )
    add("invitation_mine", InviteService.list_mine, output=InviteSerializer, many=True)
    add(
        "invitation_create",
        InviteService.create,
        ids=("organization_id",),
        input=InviteCreateSerializer,
        output=InviteSerializer,
        write=True,
        description="Invite an email to an organization, optionally sectors. Sends the invitation email.",
    )
    add(
        "invitation_revoke",
        InviteService.revoke,
        ids=("organization_id", "invite_id"),
        write=True,
    )
    add(
        "invitation_accept",
        InviteService.accept,
        input=InviteAcceptSerializer,
        output=InviteAcceptedSerializer,
        write=True,
    )
    add(
        "comment_list",
        CommentService.list_for,
        ids=("task_id",),
        output=CommentSerializer,
        many=True,
    )
    add(
        "comment_create",
        CommentService.create,
        ids=("task_id",),
        input=CommentWriteSerializer,
        output=CommentSerializer,
        write=True,
    )
    add(
        "comment_update",
        CommentService.update,
        ids=("task_id", "comment_id"),
        input=CommentWriteSerializer,
        output=CommentSerializer,
        write=True,
    )
    add(
        "comment_delete",
        CommentService.delete,
        ids=("task_id", "comment_id"),
        write=True,
    )
    for target, listing, creation in (
        ("task", LinkService.list_for_task, LinkService.create_for_task),
        ("sector", LinkService.list_for_sector, LinkService.create_for_sector),
        (
            "organization",
            LinkService.list_for_organization,
            LinkService.create_for_organization,
        ),
    ):
        add(
            f"link_{target}_list",
            listing,
            ids=(f"{target}_id",),
            output=ResourceLinkSerializer,
            many=True,
        )
        add(
            f"link_{target}_create",
            lambda u, target_id, _create=creation, **data: _create(u, target_id, data),
            ids=(f"{target}_id",),
            input=ResourceLinkSerializer,
            output=ResourceLinkSerializer,
            write=True,
        )
    add("link_delete", LinkService.delete, ids=("link_id",), write=True)
    add(
        "workspace_search",
        SearchService.search,
        ids=("organization_id",),
        input=SearchSerializer,
        output=SearchResultSerializer,
    )
    add("workspace_dashboard", DashboardService.summary, ids=("organization_id",))
    add(
        "workspace_report",
        ReportService.summary,
        ids=("organization_id",),
        input=ReportSerializer,
    )
    add("workspace_files", FileService.list_for, ids=("organization_id",), many=True)
    add(
        "agenda_deliveries",
        CalendarService.items,
        ids=("organization_id",),
        input=DateRangeSerializer,
        many=True,
        description="Read the local agenda of task due dates (max 62 days). Edit it through task_create/task_update/task_delete.",
    )
    add(
        "task_calendar_get",
        lambda u, task_id: calendar_status(TaskCalendarService.get(u, task_id)),
        ids=("task_id",),
    )
    add(
        "task_calendar_sync",
        lambda u, task_id: calendar_status(TaskCalendarService.sync(u, task_id)),
        ids=("task_id",),
        write=True,
    )
    add(
        "task_calendar_remove", TaskCalendarService.unsync, ids=("task_id",), write=True
    )
    add(
        "chat_channels",
        ChatService.list_channels,
        ids=("organization_id",),
        output=ChatChannelSerializer,
        many=True,
    )
    add(
        "chat_direct",
        lambda u, organization_id, user_id: ChatService.open_direct(
            u, organization_id, user_id
        ),
        ids=("organization_id",),
        input=ChatDirectOpenSerializer,
        output=ChatChannelSerializer,
        write=True,
    )
    add(
        "chat_teams",
        ChatService.create_teams_channel,
        ids=("organization_id",),
        input=ChatTeamsChannelSerializer,
        output=ChatChannelSerializer,
        write=True,
    )
    add(
        "chat_messages",
        ChatService.list_messages,
        ids=("channel_id",),
        output=ChatMessageSerializer,
        many=True,
    )
    add(
        "chat_send",
        send_message,
        ids=("channel_id",),
        input=MessageSerializer,
        output=ChatMessageSerializer,
        write=True,
    )
    add(
        "chat_edit",
        ChatService.edit,
        ids=("message_id",),
        input=ChatMessageEditSerializer,
        output=ChatMessageSerializer,
        write=True,
    )
    add("chat_delete", ChatService.delete, ids=("message_id",), write=True)
    add("chat_read", ChatService.mark_read, ids=("channel_id",), write=True)
    add(
        "meet_start",
        start_meet,
        ids=("channel_id",),
        write=True,
        description="Create a Meet starting now for one hour and share it in this channel. Requires connected Google. For scheduled meetings use event_create with meet=true.",
    )
    add("preferences_get", UserSettingsService.get, output=UserSettingsSerializer)
    add(
        "preferences_update",
        lambda u, **data: UserSettingsService.update(u, data),
        input=UserSettingsSerializer,
        output=UserSettingsSerializer,
        partial=True,
        write=True,
    )
    add(
        "drive_list",
        GoogleDriveService.list_files,
        input=DriveSearchSerializer,
        many=True,
    )
    add(
        "drive_attach",
        lambda u, task, file_id: GoogleDriveService.attach_to_task(u, task, file_id),
        input=DriveAttachSerializer,
        output=ResourceLinkSerializer,
        write=True,
    )
    # Payment/auth/device-token APIs and financial notifications are deliberately absent.
    from core.modules.ai.services.calendar import register_calendar_actions

    register_calendar_actions(add)
    return actions


def get_action(name):
    action = registry().get(name)
    if action is None:
        raise ValidationError(MSG_AI_UNKNOWN_ACTION)
    return action
