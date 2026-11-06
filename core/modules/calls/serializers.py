from rest_framework import serializers

from core.modules.calls.models.call import Call


class CallStartSerializer(serializers.Serializer):
    channel_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=Call.Kind.choices, default=Call.Kind.AUDIO)


class SignalSerializer(serializers.Serializer):
    to_user_id = serializers.UUIDField()
    data = serializers.DictField(help_text='{"sdp": {...}} or {"candidate": {...}}')


class MediaSerializer(serializers.Serializer):
    muted = serializers.BooleanField(required=False)
    video_off = serializers.BooleanField(required=False)
    screen_sharing = serializers.BooleanField(required=False)
