from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers


class RegistrationRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class RegistrationVerifySerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(max_length=6, min_length=6, required=True)


class RegistrationConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    code = serializers.CharField(max_length=6, min_length=6, required=True)
    name = serializers.CharField(required=True, max_length=255)
    password = serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}
    )

    def validate_password(self, value):
        validate_password(value)
        return value
