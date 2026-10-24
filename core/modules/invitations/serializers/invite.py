from rest_framework import serializers

from core.modules.invitations.models.invite import OrganizationInvite
from core.modules.organizations.models.organization import OrganizationMember
from core.modules.organizations.serializers.organization import (
    OrganizationMemberSerializer,
)


class InviteSerializer(serializers.ModelSerializer):
    sector_ids = serializers.PrimaryKeyRelatedField(
        source="sectors", many=True, read_only=True
    )
    organization_id = serializers.UUIDField(read_only=True)
    organization_name = serializers.CharField(
        source="organization.name", read_only=True
    )

    class Meta:
        model = OrganizationInvite
        fields = (
            "id",
            "organization_id",
            "organization_name",
            "email",
            "role",
            "sector_ids",
            "status",
            "expires_at",
            "created_at",
        )
        read_only_fields = fields


class InviteCreateSerializer(serializers.Serializer):
    sector_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=[
            (value, label)
            for value, label in OrganizationMember.Role.choices
            if value != OrganizationMember.Role.OWNER
        ],
        default=OrganizationMember.Role.MEMBER,
    )


class InviteAcceptSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=128)


class InviteAcceptedSerializer(OrganizationMemberSerializer):
    organization_id = serializers.UUIDField(read_only=True)

    class Meta(OrganizationMemberSerializer.Meta):
        fields = ("organization_id", *OrganizationMemberSerializer.Meta.fields)
        read_only_fields = fields


class InvitePreviewSerializer(serializers.Serializer):
    organization_name = serializers.CharField()
    role = serializers.CharField()
    email = serializers.EmailField()
    expires_at = serializers.DateTimeField()
    has_account = serializers.BooleanField()
