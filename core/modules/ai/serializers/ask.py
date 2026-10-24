from rest_framework import serializers

from core.modules.ai.response_messages import MSG_AI_INVALID_ARGUMENTS


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError(
                {"non_field_errors": [MSG_AI_INVALID_ARGUMENTS]}
            )
        return super().to_internal_value(data)


class AIContextSerializer(StrictSerializer):
    organization_id = serializers.UUIDField(required=False)
    sector_id = serializers.UUIDField(required=False)
    task_id = serializers.UUIDField(required=False)


class AIAskSerializer(StrictSerializer):
    prompt = serializers.CharField(max_length=10000)
    context = AIContextSerializer(required=False)
    conversation_id = serializers.UUIDField(required=False)
    request_id = serializers.UUIDField(required=False)
    confirmation_token = serializers.UUIDField(required=False)


class AIAnswerSerializer(serializers.Serializer):
    answer = serializers.CharField()
    actions = serializers.ListField(child=serializers.DictField(), required=False)
    conversation_id = serializers.UUIDField(required=False, allow_null=True)
    interrupted = serializers.BooleanField(required=False)
    confirmation_token = serializers.UUIDField(required=False, allow_null=True)
    choices = serializers.ListField(child=serializers.CharField(), required=False)
    unverified = serializers.BooleanField(required=False)
