from django.contrib.auth import get_user_model
from rest_framework import serializers

from core.modules.meetings.models.insight import MeetingInsight

User = get_user_model()


class InsightSerializer(serializers.ModelSerializer):
    """`summary.actions[i].task_id` tells which actions already became tasks."""

    summary = serializers.SerializerMethodField()

    class Meta:
        model = MeetingInsight
        fields = (
            "id",
            "status",
            "language",
            "audio_seconds",
            "segments",
            "summary",
            "transcribe_model",
            "summary_model",
            "transcribe_seconds",
            "summary_seconds",
            "attempts",
            "error",
            "updated_at",
            "finished_at",
        )

    def get_summary(self, insight) -> dict | None:
        if not insight.summary:
            return None
        tasks = self.context.get("tasks", {})
        actions = [
            {**action, "created": index in tasks, "task_id": tasks.get(index)}
            for index, action in enumerate(insight.summary.get("actions", []))
        ]
        return {**insight.summary, "actions": actions}


class ActionTaskItemSerializer(serializers.Serializer):
    index = serializers.IntegerField(min_value=0)
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(allow_blank=True, required=False, default="")
    # empty on purpose when the meeting named nobody: never guessed
    assignee = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True), allow_null=True, required=False
    )
    due_date = serializers.DateField(allow_null=True, required=False)


class ActionTasksSerializer(serializers.Serializer):
    items = ActionTaskItemSerializer(many=True, allow_empty=False, max_length=50)


class ActionTasksResultSerializer(serializers.Serializer):
    created = serializers.ListField(child=serializers.DictField())
    skipped = serializers.ListField(child=serializers.IntegerField())
