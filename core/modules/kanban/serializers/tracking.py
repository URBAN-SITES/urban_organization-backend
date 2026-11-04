from rest_framework import serializers

from core.modules.kanban.models.time_entry import TimeEntry


class TimeEntrySerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(read_only=True)
    user_name = serializers.CharField(source="user.name", read_only=True, default=None)
    task_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = TimeEntry
        fields = (
            "id",
            "task_id",
            "user_id",
            "user_name",
            "started_at",
            "ended_at",
            "minutes",
            "note",
        )
        read_only_fields = fields


class RunningTimerSerializer(TimeEntrySerializer):
    task_title = serializers.CharField(source="task.title", read_only=True)
    sector_id = serializers.UUIDField(source="task.sector_id", read_only=True)

    class Meta(TimeEntrySerializer.Meta):
        fields = (*TimeEntrySerializer.Meta.fields, "task_title", "sector_id")
        read_only_fields = fields


class MyTimerSerializer(serializers.Serializer):
    timer = RunningTimerSerializer(allow_null=True)


class StoppedTimerSerializer(serializers.Serializer):
    stopped = TimeEntrySerializer(allow_null=True)


class TaskTimeSerializer(serializers.Serializer):
    total_minutes = serializers.IntegerField()
    entries = TimeEntrySerializer(many=True)


class ManualTimeSerializer(serializers.Serializer):
    minutes = serializers.IntegerField(min_value=1, max_value=24 * 60)
    date = serializers.DateField(required=False)
    note = serializers.CharField(max_length=255, allow_blank=True, required=False)


class WorkloadPersonSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    name = serializers.CharField()
    open = serializers.IntegerField()
    overdue = serializers.IntegerField()
    due_week = serializers.IntegerField()
    points = serializers.IntegerField()
    minutes_week = serializers.IntegerField()


class WorkloadSerializer(serializers.Serializer):
    people = WorkloadPersonSerializer(many=True)
    unassigned = serializers.IntegerField()
