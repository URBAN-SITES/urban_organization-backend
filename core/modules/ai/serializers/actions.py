from rest_framework import serializers

from core.modules.ai.response_messages import MSG_AI_INVALID_ARGUMENTS
from core.modules.chat.serializers.chat import ChatMessageWriteSerializer


def validate_input(serializer_class, data, *, partial=False):
    """Reject unknown/read-only fields instead of silently ignoring model arguments."""
    serializer = serializer_class(data=data, partial=partial)
    writable = {
        name for name, field in serializer.fields.items() if not field.read_only
    }
    if not isinstance(data, dict) or set(data) - writable:
        raise serializers.ValidationError(MSG_AI_INVALID_ARGUMENTS)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


class PageSerializer(serializers.Serializer):
    offset = serializers.IntegerField(min_value=0, max_value=10000, default=0)
    limit = serializers.IntegerField(min_value=1, max_value=50, default=20)


class SearchSerializer(serializers.Serializer):
    query = serializers.CharField(min_length=2, max_length=200)


class ReportSerializer(serializers.Serializer):
    days = serializers.ChoiceField(choices=(7, 30, 90), default=30)


class DateRangeSerializer(serializers.Serializer):
    start = serializers.DateField()
    end = serializers.DateField()

    def validate(self, data):
        if not 0 <= (data["end"] - data["start"]).days <= 62:
            raise serializers.ValidationError(MSG_AI_INVALID_ARGUMENTS)
        return data


class MessageSerializer(ChatMessageWriteSerializer):
    # Binary uploads use the existing upload endpoint, never invented model bytes.
    files = None


class DriveSearchSerializer(serializers.Serializer):
    search = serializers.CharField(max_length=200, default="", allow_blank=True)
