from django.utils import timezone
from rest_framework import serializers

from core.models.user import User
from core.modules.kanban.models.label import Label
from core.modules.kanban.models.resource_link import ResourceLink
from core.modules.kanban.models.task import ChecklistItem, Comment, Status, Task


class LabelSerializer(serializers.ModelSerializer):
    color = serializers.RegexField(
        r"^#[0-9a-fA-F]{6}$", max_length=7, required=False, allow_blank=True
    )

    class Meta:
        model = Label
        fields = ("id", "name", "color")
        read_only_fields = ("id",)


class PersonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    email = serializers.EmailField()


class TaskSerializer(serializers.ModelSerializer):
    sector_id = serializers.UUIDField(read_only=True)
    status_id = serializers.UUIDField(read_only=True)
    parent_id = serializers.UUIDField(read_only=True)
    assignee_id = serializers.UUIDField(read_only=True)
    assignee_name = serializers.CharField(
        source="assignee.name", read_only=True, default=None
    )
    created_by_name = serializers.CharField(
        source="owner.name", read_only=True, default=None
    )
    is_overdue = serializers.SerializerMethodField()
    checklist_total = serializers.SerializerMethodField()
    checklist_done = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    subtask_total = serializers.SerializerMethodField()
    subtask_done = serializers.SerializerMethodField()
    labels = LabelSerializer(many=True, read_only=True)

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
            "created_by_name",
            "is_overdue",
            "checklist_total",
            "checklist_done",
            "comment_count",
            "subtask_total",
            "subtask_done",
            "labels",
            "created_at",
        )
        read_only_fields = fields

    # the list view annotates these counts; single-task responses (create/move/detail)
    # fall back to one small query each
    def get_checklist_total(self, task) -> int:
        return getattr(task, "checklist_total", None) or task.checklist_items.count()

    def get_checklist_done(self, task) -> int:
        done = getattr(task, "checklist_done", None)
        return (
            task.checklist_items.filter(is_done=True).count() if done is None else done
        )

    def get_comment_count(self, task) -> int:
        count = getattr(task, "comment_count", None)
        return task.comments.count() if count is None else count

    def get_subtask_total(self, task) -> int:
        total = getattr(task, "subtask_total", None)
        return task.subtasks.filter(is_active=True).count() if total is None else total

    def get_subtask_done(self, task) -> int:
        done = getattr(task, "subtask_done", None)
        if done is None:
            return task.subtasks.filter(
                is_active=True, completed_at__isnull=False
            ).count()
        return done

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

    label_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, max_length=20
    )

    class Meta:
        model = Task
        fields = (
            "title",
            "description",
            "priority",
            "due_date",
            "assignee",
            "label_ids",
        )


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


class CommentMentionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class CommentSerializer(serializers.ModelSerializer):
    author_id = serializers.UUIDField(read_only=True)
    author_name = serializers.CharField(source="author.name", read_only=True)
    mentions = CommentMentionSerializer(many=True, read_only=True)

    class Meta:
        model = Comment
        fields = ("id", "author_id", "author_name", "content", "mentions", "created_at")
        read_only_fields = fields


class CommentWriteSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=5000)
    mentions = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list, max_length=20
    )


class ResourceLinkSerializer(serializers.ModelSerializer):
    created_by_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ResourceLink
        fields = ("id", "title", "url", "created_by_id", "created_at")
        read_only_fields = ("id", "created_by_id", "created_at")


class TaskActivitySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    action = serializers.CharField()
    changes = serializers.JSONField()
    actor_id = serializers.UUIDField(allow_null=True)
    actor_name = serializers.CharField(source="actor.name", default=None)
    created_at = serializers.DateTimeField()
