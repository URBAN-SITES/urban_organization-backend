from rest_framework import serializers

from core.modules.kanban.serializers.task import ResourceLinkSerializer

# Drive ids are URL-safe tokens; validating keeps odd input out of the request path
FILE_ID = r"^[A-Za-z0-9_-]{10,100}$"


class DriveFileSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    mime_type = serializers.CharField()
    size_bytes = serializers.IntegerField(allow_null=True)
    web_view_link = serializers.CharField()
    modified_at = serializers.CharField(allow_null=True)


class DriveUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    share_link = serializers.BooleanField(
        default=False, help_text="Anyone with the link can read the file"
    )
    task = serializers.UUIDField(
        required=False, help_text="Also attach the file to this task as a link"
    )


class DriveUploadResultSerializer(serializers.Serializer):
    file = DriveFileSerializer()
    link = ResourceLinkSerializer(allow_null=True)


class DriveAttachSerializer(serializers.Serializer):
    task = serializers.UUIDField()
    file_id = serializers.RegexField(FILE_ID)
