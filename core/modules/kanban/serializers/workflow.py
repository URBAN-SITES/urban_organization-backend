from rest_framework import serializers

from core.models.user import User
from core.modules.kanban.models.custom_field import CustomField, CustomFieldOption
from core.modules.kanban.models.cycle import Cycle
from core.modules.kanban.models.epic import Epic
from core.modules.kanban.models.label import Label
from core.modules.kanban.models.saved_view import SavedView
from core.modules.kanban.models.task import Status, Task
from core.modules.kanban.models.template import TaskTemplate

MAX_JSON = 4000


def _small_json(value):
    if len(str(value)) > MAX_JSON:
        raise serializers.ValidationError("Too large.")
    return value


class SavedViewSerializer(serializers.ModelSerializer):
    owner_id = serializers.UUIDField(read_only=True)
    owner_name = serializers.CharField(
        source="owner.name", read_only=True, default=None
    )
    filters = serializers.DictField(required=False, validators=[_small_json])
    sort = serializers.ListField(required=False, max_length=5, validators=[_small_json])

    class Meta:
        model = SavedView
        fields = (
            "id",
            "name",
            "layout",
            "filters",
            "sort",
            "search",
            "is_shared",
            "position",
            "owner_id",
            "owner_name",
            "created_at",
        )
        read_only_fields = ("id", "owner_id", "owner_name", "created_at")


class CustomFieldOptionSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(required=False)
    color = serializers.RegexField(
        r"^#[0-9a-fA-F]{6}$", max_length=7, required=False, allow_blank=True
    )

    class Meta:
        model = CustomFieldOption
        fields = ("id", "name", "color")


class CustomFieldSerializer(serializers.ModelSerializer):
    options = CustomFieldOptionSerializer(many=True, required=False, max_length=50)

    class Meta:
        model = CustomField
        fields = ("id", "name", "type", "position", "options")
        read_only_fields = ("id", "position")


class FieldValueSerializer(serializers.Serializer):
    field_id = serializers.UUIDField(read_only=True)
    value = serializers.JSONField(allow_null=True)


class TaskTemplateSerializer(serializers.ModelSerializer):
    label_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, max_length=20
    )
    checklist = serializers.ListField(
        child=serializers.CharField(max_length=255), required=False, max_length=50
    )
    priority = serializers.ChoiceField(choices=Task.Priority, required=False)
    estimate = serializers.IntegerField(
        min_value=0, max_value=100, required=False, allow_null=True
    )

    class Meta:
        model = TaskTemplate
        fields = (
            "id",
            "name",
            "title",
            "description",
            "priority",
            "estimate",
            "label_ids",
            "checklist",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class BulkSerializer(serializers.Serializer):
    task_ids = serializers.ListField(
        child=serializers.UUIDField(), min_length=1, max_length=200
    )
    status = serializers.PrimaryKeyRelatedField(
        queryset=Status.objects.all(), required=False
    )
    assignee = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True), allow_null=True, required=False
    )
    cycle = serializers.PrimaryKeyRelatedField(
        queryset=Cycle.objects.all(), allow_null=True, required=False
    )
    epic = serializers.PrimaryKeyRelatedField(
        queryset=Epic.objects.all(), allow_null=True, required=False
    )
    priority = serializers.ChoiceField(choices=Task.Priority, required=False)
    due_date = serializers.DateField(allow_null=True, required=False)
    estimate = serializers.IntegerField(
        min_value=0, max_value=100, required=False, allow_null=True
    )
    add_label = serializers.PrimaryKeyRelatedField(
        queryset=Label.objects.all(), required=False
    )
    archive = serializers.BooleanField(required=False)
    delete = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if len(attrs) < 2:
            raise serializers.ValidationError("Nothing to change.")
        return attrs


class BulkResultSerializer(serializers.Serializer):
    updated = serializers.IntegerField()
