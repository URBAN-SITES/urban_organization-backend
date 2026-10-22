from rest_framework import serializers


class AIAskSerializer(serializers.Serializer):
    prompt = serializers.CharField(max_length=10000)


class AIAnswerSerializer(serializers.Serializer):
    answer = serializers.CharField()
