from rest_framework import serializers

from core.models.user import User, UserSession


class BaseUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = "__all__"


class UserListRetrieveSerializer(BaseUserSerializer):
    class Meta(BaseUserSerializer.Meta):
        fields = ("id", "name", "email", "bio", "avatar_url", "created_at")


class UserMeSerializer(UserListRetrieveSerializer):
    is_subscriber = serializers.BooleanField(read_only=True)
    subscription_price = serializers.SerializerMethodField()

    class Meta(UserListRetrieveSerializer.Meta):
        fields = (
            *UserListRetrieveSerializer.Meta.fields,
            "is_subscriber",
            "subscription_price",
        )
        read_only_fields = fields

    def get_subscription_price(self, obj):
        from core.modules.payments.services.payment import PAYMENT_AMOUNT

        return str(PAYMENT_AMOUNT)


class UserUpdateSelfSerializer(BaseUserSerializer):
    class Meta(BaseUserSerializer.Meta):
        fields = ("name", "bio", "avatar_url")

    def validate(self, attrs):
        forbidden_fields = {
            "email",
            "password",
            "is_active",
            "is_staff",
            "is_superuser",
            "is_subscriber",
            "subscription_price",
        }
        received_fields = set(self.initial_data.keys())

        if forbidden_fields.intersection(received_fields):
            raise serializers.ValidationError(
                {"detail": "It is not possible to change these fields directly."}
            )

        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(write_only=True, required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )


class LogoutSerializer(serializers.Serializer):
    pass


class UserSessionSerializer(serializers.ModelSerializer):
    device = serializers.CharField(source="device_name", read_only=True)
    ip = serializers.CharField(source="ip_address", read_only=True)
    current = serializers.BooleanField(read_only=True)

    class Meta:
        model = UserSession
        fields = [
            "id",
            "device",
            "ip",
            "location",
            "created_at",
            "last_activity",
            "current",
        ]
