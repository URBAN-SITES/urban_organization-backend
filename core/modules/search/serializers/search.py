from rest_framework import serializers

from core.modules.kanban.models.task import Task
from core.modules.organizations.models.organization import OrganizationMember
from core.modules.uploads.models.attachment import Attachment


class SearchTaskSerializer(serializers.ModelSerializer):
    sector_id = serializers.UUIDField(read_only=True)
    sector_name = serializers.CharField(source="sector.name", read_only=True)
    status = serializers.CharField(source="status.name", read_only=True)

    class Meta:
        model = Task
        fields = (
            "id",
            "title",
            "sector_id",
            "sector_name",
            "status",
            "priority",
            "due_date",
        )
        read_only_fields = fields


class SearchPersonSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="user_id", read_only=True)
    name = serializers.CharField(source="user.name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = OrganizationMember
        fields = ("id", "name", "email", "role")
        read_only_fields = fields


class SearchFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = ("id", "file_name", "mime_type", "size_bytes", "url", "created_at")
        read_only_fields = fields


class SearchResultSerializer(serializers.Serializer):
    tasks = SearchTaskSerializer(many=True)
    people = SearchPersonSerializer(many=True)
    files = SearchFileSerializer(many=True)
