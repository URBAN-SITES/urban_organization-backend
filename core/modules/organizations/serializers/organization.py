from rest_framework import serializers

from core.modules.organizations.models.organization import (
    Organization,
    OrganizationMember,
)


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = (
            "id",
            "name",
            "description",
            "logo_url",
            "is_personal",
            "created_at",
        )
        read_only_fields = ("id", "is_personal", "created_at")


class OrganizationMemberSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(source="user.name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = OrganizationMember
        fields = ("id", "user_id", "name", "email", "role", "joined_at")
        read_only_fields = fields


class OrganizationMemberAddSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=OrganizationMember.Role, default=OrganizationMember.Role.MEMBER
    )


class OrganizationMemberRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=OrganizationMember.Role)
