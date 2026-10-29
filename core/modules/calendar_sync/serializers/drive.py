from rest_framework import serializers

from core.modules.calendar_sync.response_messages import MSG_DRIVE_FILE_TOO_LARGE
from core.modules.kanban.serializers.task import ResourceLinkSerializer

# Drive ids are URL-safe tokens; validating keeps odd input out of the request path
FILE_ID = r"^[A-Za-z0-9_-]{10,100}$"
# same ceiling as the proxy (client_max_body_size 20m in deployment/deploy/nginx.conf)
MAX_DRIVE_UPLOAD = 20 * 1024 * 1024


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

    def validate_file(self, value):
        if value.size > MAX_DRIVE_UPLOAD:
            raise serializers.ValidationError(MSG_DRIVE_FILE_TOO_LARGE)
        return value


class DriveUploadResultSerializer(serializers.Serializer):
    file = DriveFileSerializer()
    link = ResourceLinkSerializer(allow_null=True)


class DriveAttachSerializer(serializers.Serializer):
    task = serializers.UUIDField()
    file_id = serializers.RegexField(FILE_ID)
