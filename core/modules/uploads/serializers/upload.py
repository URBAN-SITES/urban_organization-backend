from rest_framework import serializers

from core.modules.uploads.response_messages import MSG_FILE_TOO_LARGE

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


class FileUploadSerializer(serializers.Serializer):
    file = serializers.FileField(required=True)

    def validate_file(self, value):
        if value.size > MAX_UPLOAD_SIZE:
            raise serializers.ValidationError(MSG_FILE_TOO_LARGE)
        return value


class FileUploadResponseSerializer(serializers.Serializer):
    url = serializers.URLField()
    public_id = serializers.CharField()
