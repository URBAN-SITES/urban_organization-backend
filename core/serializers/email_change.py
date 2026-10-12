from rest_framework import serializers


class EmailChangeRequestSerializer(serializers.Serializer):
    new_email = serializers.EmailField(required=True)


class EmailChangeVerifySerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6, min_length=6, required=True)


class EmailChangeConfirmSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6, min_length=6, required=True)
    password = serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}
    )
