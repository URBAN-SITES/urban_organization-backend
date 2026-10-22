from rest_framework import serializers

from core.modules.notifications.models.notification import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "title", "message", "data", "is_read", "created_at")
        read_only_fields = fields


class DeviceTokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512)


class SendPushSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512)
    title = serializers.CharField(max_length=255)
    body = serializers.CharField(allow_blank=True, default="")
