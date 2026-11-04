from rest_framework import serializers

from core.modules.kanban.models.automation import AutomationRule
from core.modules.kanban.services.importer import SOURCES


class AutomationRuleSerializer(serializers.ModelSerializer):
    is_active = serializers.BooleanField(default=True)

    class Meta:
        model = AutomationRule
        fields = (
            "id",
            "name",
            "trigger",
            "trigger_value",
            "action",
            "action_value",
            "is_active",
            "run_count",
            "last_run_at",
            "created_at",
        )
        read_only_fields = ("id", "run_count", "last_run_at", "created_at")


class ImportSerializer(serializers.Serializer):
    source = serializers.ChoiceField(choices=SOURCES)
    file = serializers.FileField()
    dry_run = serializers.BooleanField(default=True)


class ImportResultSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    created = serializers.IntegerField()
    assigned = serializers.IntegerField()
    new_columns = serializers.ListField(child=serializers.CharField())
    new_labels = serializers.ListField(child=serializers.CharField())
    sample = serializers.ListField(child=serializers.CharField())


class PublicLinkSerializer(serializers.Serializer):
    token = serializers.CharField(allow_null=True)


class PublicStatusSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    category = serializers.CharField()
    color = serializers.CharField()


class PublicLabelSerializer(serializers.Serializer):
    name = serializers.CharField()
    color = serializers.CharField()


class PublicTaskSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    key = serializers.CharField(allow_null=True)
    title = serializers.CharField()
    status_id = serializers.UUIDField()
    priority = serializers.CharField()
    start_date = serializers.DateField(allow_null=True)
    due_date = serializers.DateField(allow_null=True)
    estimate = serializers.IntegerField(allow_null=True)
    completed = serializers.BooleanField()
    labels = PublicLabelSerializer(many=True)


class PublicBoardSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField()
    color = serializers.CharField()
    icon = serializers.CharField()
    organization = serializers.CharField()
    statuses = PublicStatusSerializer(many=True)
    tasks = PublicTaskSerializer(many=True)
