from rest_framework import serializers


class GoogleLoginSerializer(serializers.Serializer):
    credential = serializers.CharField(write_only=True, required=True)
