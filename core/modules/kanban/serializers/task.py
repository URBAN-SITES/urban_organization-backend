from django.utils import timezone
from rest_framework import serializers

from core.models.user import User
from core.modules.kanban.models.resource_link import ResourceLink
from core.modules.kanban.models.task import ChecklistItem, Comment, Status, Task


class TaskSerializer(serializers.ModelSerializer):
    sector_id = serializers.UUIDField(read_only=True)
    status_id = serializers.UUIDField(read_only=True)
    parent_id = serializers.UUIDField(read_only=True)
    assignee_id = serializers.UUIDField(read_only=True)
    assignee_name = serializers.CharField(
        source="assignee.name", read_only=True, default=None
    )
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = (
            "id",
            "sector_id",
            "status_id",
            "parent_id",
            "title",
            "description",
            "priority",
            "due_date",
            "completed_at",
            "assignee_id",
            "assignee_name",
            "position",
            "is_overdue",
            "created_at",
        )
        read_only_fields = fields

    def get_is_overdue(self, task) -> bool:
        return bool(
            task.due_date
            and task.completed_at is None
            and task.due_date < timezone.localdate()
        )


class TaskUpdateSerializer(serializers.ModelSerializer):
    assignee = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True), allow_null=True, required=False
    )

    class Meta:
        model = Task
        fields = ("title", "description", "priority", "due_date", "assignee")


class TaskCreateSerializer(TaskUpdateSerializer):
    status = serializers.PrimaryKeyRelatedField(
        queryset=Status.objects.all(), required=False
    )
    parent = serializers.PrimaryKeyRelatedField(
        queryset=Task.objects.filter(is_active=True), required=False
    )

    class Meta(TaskUpdateSerializer.Meta):
        fields = (*TaskUpdateSerializer.Meta.fields, "status", "parent")


class TaskMoveSerializer(serializers.Serializer):
    status = serializers.PrimaryKeyRelatedField(queryset=Status.objects.all())
    position = serializers.IntegerField(min_value=0, required=False, default=None)


class ChecklistItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChecklistItem
        fields = ("id", "content", "is_done", "position")
        read_only_fields = ("id",)
        extra_kwargs = {"position": {"required": False}}


class CommentSerializer(serializers.ModelSerializer):
    author_id = serializers.UUIDField(read_only=True)
    author_name = serializers.CharField(source="author.name", read_only=True)

    class Meta:
        model = Comment
        fields = ("id", "author_id", "author_name", "content", "created_at")
        read_only_fields = ("id", "author_id", "author_name", "created_at")


class CommentWriteSerializer(serializers.Serializer):
    content = serializers.CharField()


class ResourceLinkSerializer(serializers.ModelSerializer):
    created_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ResourceLink
        fields = ("id", "title", "url", "created_by_id", "created_at")
        read_only_fields = ("id", "created_by_id", "created_at")
