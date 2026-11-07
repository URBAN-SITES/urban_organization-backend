"""Project tools beyond tasks: documents (pages), meetings, labels and intake requests.

Every handler goes through the module's own service, so permissions and validation are
the same as in the app; the assistant never reaches the models directly.
"""

from rest_framework import serializers

from core.modules.kanban.serializers.planning import (
    IntakeAcceptSerializer,
    IntakeDeclineSerializer,
    IntakeSerializer,
    PageSerializer,
)
from core.modules.kanban.serializers.task import LabelSerializer
from core.modules.kanban.services.label import LabelService
from core.modules.kanban.services.planning import IntakeService, PageService
from core.modules.meetings.serializers.meeting import (
    MeetingListQuerySerializer,
    MeetingWriteSerializer,
)
from core.modules.meetings.services.meetings import MeetingService


class PageWrite(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    content = serializers.CharField(
        max_length=200_000, required=False, allow_blank=True
    )
    is_pinned = serializers.BooleanField(required=False)


class IntakeWrite(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(
        max_length=10_000, required=False, allow_blank=True
    )


def page_rows(user, sector_id):
    # the list leaves the content out: pages can be long; page_get reads one
    return PageService.list_for(user, sector_id).values(
        "id", "title", "is_pinned", "updated_at"
    )


def meeting_row(meeting):
    return {
        "id": meeting.id,
        "title": meeting.title,
        "description": meeting.description,
        "starts_at": meeting.starts_at,
        "ends_at": meeting.ends_at,
        "participants": [p.name for p in meeting.participants.all()],
        "recordings": getattr(meeting, "recording_count", 0),
    }


def meeting_list(user, sector_id, when="all"):
    rows, _role = MeetingService.list_for_project(
        user, sector_id, "" if when == "all" else when
    )
    return [meeting_row(m) for m in rows]


def register_project_actions(add):
    add(
        "page_list",
        page_rows,
        ids=("sector_id",),
        many=True,
        description="List the project's documents (title, pinned, updated_at).",
    )
    add("page_get", PageService.get, ids=("page_id",), output=PageSerializer)
    add(
        "page_create",
        lambda u, sector_id, **data: PageService.create(u, sector_id, data),
        ids=("sector_id",),
        input=PageWrite,
        output=PageSerializer,
        write=True,
        description="Create a project document. content is Markdown.",
    )
    add(
        "page_update",
        lambda u, page_id, **data: PageService.update(u, page_id, data),
        ids=("page_id",),
        input=PageWrite,
        output=PageSerializer,
        partial=True,
        write=True,
    )
    add("page_delete", PageService.delete, ids=("page_id",), write=True)

    add(
        "meeting_list",
        meeting_list,
        ids=("sector_id",),
        input=MeetingListQuerySerializer,
        many=True,
        description="Project video meetings (the app's own rooms). when: all|upcoming|past.",
    )
    add(
        "meeting_create",
        lambda u, sector_id, **data: meeting_row(
            MeetingService.create(u, sector_id, data)
        ),
        ids=("sector_id",),
        input=MeetingWriteSerializer,
        write=True,
        description="Schedule a video meeting in the project (the app's own room, not Google Meet). participants are user ids; times need an explicit offset.",
    )

    add(
        "label_list",
        LabelService.list_for,
        ids=("sector_id",),
        output=LabelSerializer,
        many=True,
    )
    add(
        "label_create",
        LabelService.create,
        ids=("sector_id",),
        input=LabelSerializer,
        output=LabelSerializer,
        write=True,
    )

    add(
        "intake_list",
        IntakeService.list_for,
        ids=("sector_id",),
        output=IntakeSerializer,
        many=True,
        description="Requests people sent to the project (Pedidos). state: pending|accepted|declined.",
    )
    add(
        "intake_create",
        lambda u, sector_id, **data: IntakeService.create(u, sector_id, data),
        ids=("sector_id",),
        input=IntakeWrite,
        output=IntakeSerializer,
        write=True,
    )
    add(
        "intake_accept",
        lambda u, request_id, **data: IntakeService.accept(u, request_id, data),
        ids=("request_id",),
        input=IntakeAcceptSerializer,
        output=IntakeSerializer,
        write=True,
        description="Accept a pending request: it becomes a task in the project.",
    )
    add(
        "intake_decline",
        lambda u, request_id, note="": IntakeService.decline(u, request_id, note),
        ids=("request_id",),
        input=IntakeDeclineSerializer,
        output=IntakeSerializer,
        write=True,
    )
