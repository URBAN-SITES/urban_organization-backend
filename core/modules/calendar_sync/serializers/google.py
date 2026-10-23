from rest_framework import serializers


class GoogleAuthorizeSerializer(serializers.Serializer):
    url = serializers.URLField()


class GoogleConnectSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=2048)
    state = serializers.CharField(max_length=2048)


class GoogleStatusSerializer(serializers.Serializer):
    connected = serializers.BooleanField()
    drive = serializers.BooleanField(
        help_text="True when the connection also allows Google Drive"
    )


class TaskCalendarStatusSerializer(serializers.Serializer):
    synced = serializers.BooleanField()
    last_synced_at = serializers.DateTimeField(allow_null=True)
