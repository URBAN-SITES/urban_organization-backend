import re

from rest_framework import serializers

from core.models.user import User
from core.modules.kanban.models.epic import Epic
from core.modules.kanban.models.intake import IntakeRequest
from core.modules.kanban.models.page import Page
from core.modules.kanban.models.task import Status, Task


class EpicSerializer(serializers.ModelSerializer):
    lead = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True),
        allow_null=True,
        required=False,
        write_only=True,
    )
    lead_id = serializers.UUIDField(read_only=True)
    lead_name = serializers.CharField(source="lead.name", read_only=True, default=None)
    color = serializers.RegexField(
        r"^#[0-9a-fA-F]{6}$", max_length=7, required=False, allow_blank=True
    )
    task_total = serializers.IntegerField(read_only=True, default=0)
    task_done = serializers.IntegerField(read_only=True, default=0)
    points_total = serializers.IntegerField(read_only=True, default=0)
    points_done = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Epic
        fields = (
            "id",
            "name",
            "description",
            "state",
            "lead",
            "lead_id",
            "lead_name",
            "color",
            "start_date",
            "target_date",
            "task_total",
            "task_done",
            "points_total",
            "points_done",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class PageListSerializer(serializers.ModelSerializer):
    updated_by_name = serializers.CharField(
        source="updated_by.name", read_only=True, default=None
    )
    excerpt = serializers.SerializerMethodField()

    class Meta:
        model = Page
        fields = (
            "id",
            "title",
            "is_pinned",
            "excerpt",
            "updated_by_name",
            "updated_at",
        )
        read_only_fields = fields

    def get_excerpt(self, page) -> str:
        # list preview without the Markdown marks
        return " ".join(re.sub(r"[#*_>`\[\]]", "", page.content).split())[:160]


class PageSerializer(serializers.ModelSerializer):
    content = serializers.CharField(
        max_length=200_000, allow_blank=True, required=False
    )
    created_by_name = serializers.CharField(
        source="created_by.name", read_only=True, default=None
    )
    updated_by_name = serializers.CharField(
        source="updated_by.name", read_only=True, default=None
    )

    class Meta:
        model = Page
        fields = (
            "id",
            "title",
            "content",
            "is_pinned",
            "created_by_name",
            "updated_by_name",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "created_by_name",
            "updated_by_name",
            "created_at",
            "updated_at",
        )


class IntakeSerializer(serializers.ModelSerializer):
    requester_name = serializers.CharField(
        source="requester.name", read_only=True, default=None
    )
    decided_by_name = serializers.CharField(
        source="decided_by.name", read_only=True, default=None
    )
    task_id = serializers.UUIDField(read_only=True)
    task_key = serializers.SerializerMethodField()

    class Meta:
        model = IntakeRequest
        fields = (
            "id",
            "title",
            "description",
            "state",
            "requester_name",
            "decided_by_name",
            "decision_note",
            "decided_at",
            "task_id",
            "task_key",
            "created_at",
        )
        read_only_fields = (
            "id",
            "state",
            "requester_name",
            "decided_by_name",
            "decision_note",
            "decided_at",
            "task_id",
            "task_key",
            "created_at",
        )
        extra_kwargs = {"description": {"max_length": 10_000}}

    def get_task_key(self, request) -> str | None:
        task = request.task
        if task is None or not task.sequence:
            return None
        return f"{task.sector.identifier or 'PRJ'}-{task.sequence}"


class IntakeAcceptSerializer(serializers.Serializer):
    status = serializers.PrimaryKeyRelatedField(
        queryset=Status.objects.all(), required=False
    )
    priority = serializers.ChoiceField(choices=Task.Priority, required=False)
    assignee = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True), allow_null=True, required=False
    )


class IntakeDeclineSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=500, allow_blank=True, required=False)
