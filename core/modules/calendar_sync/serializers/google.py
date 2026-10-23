from rest_framework import serializers


class GoogleAuthorizeSerializer(serializers.Serializer):
    url = serializers.URLField()


class GoogleConnectSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=2048)
    state = serializers.CharField(max_length=2048)


class GoogleStatusSerializer(serializers.Serializer):
    connected = serializers.BooleanField()
