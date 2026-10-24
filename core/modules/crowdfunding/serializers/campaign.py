import re
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from core.modules.crowdfunding.models.campaign import Campaign
from core.modules.crowdfunding.response_messages import (
    MSG_CAMPAIGN_DEADLINE_PAST,
    MSG_CONTRIBUTION_TOO_SMALL,
    MSG_CPF_INVALID,
)

MIN_CONTRIBUTION = Decimal("1.00")


class CampaignSerializer(serializers.ModelSerializer):
    raised = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    contributors = serializers.IntegerField(read_only=True)

    class Meta:
        model = Campaign
        fields = (
            "id",
            "organization_id",
            "title",
            "description",
            "goal_amount",
            "raised",
            "contributors",
            "deadline",
            "status",
            "created_by_id",
            "created_at",
        )
        read_only_fields = fields


class CampaignCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    goal_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=MIN_CONTRIBUTION
    )
    deadline = serializers.DateField(required=False, allow_null=True)

    def validate_deadline(self, value):
        if value and value < timezone.localdate():
            raise serializers.ValidationError(MSG_CAMPAIGN_DEADLINE_PAST)
        return value


class CampaignUpdateSerializer(CampaignCreateSerializer):
    status = serializers.ChoiceField(choices=Campaign.Status.choices)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False


class ContributionCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=MIN_CONTRIBUTION
    )
    cpf = serializers.CharField(max_length=14)
    name = serializers.CharField(max_length=255)
    message = serializers.CharField(max_length=255, required=False, allow_blank=True)
    anonymous = serializers.BooleanField(required=False, default=False)

    def validate_amount(self, value):
        if value < MIN_CONTRIBUTION:
            raise serializers.ValidationError(MSG_CONTRIBUTION_TOO_SMALL)
        return value

    def validate_cpf(self, value):
        clean = re.sub(r"\D", "", value)
        if len(clean) != 11:
            raise serializers.ValidationError(MSG_CPF_INVALID)
        return clean


class ContributionResponseSerializer(serializers.Serializer):
    contribution_id = serializers.UUIDField()
    payment_id = serializers.UUIDField()
    status = serializers.CharField()
    qr_code = serializers.CharField()
    qr_code_base64 = serializers.CharField()
    ticket_url = serializers.URLField(allow_blank=True)


class ContributionSerializer(serializers.Serializer):
    """Approved contributions only; anonymous ones hide the contributor."""

    id = serializers.UUIDField()
    contributor_name = serializers.SerializerMethodField()
    amount = serializers.DecimalField(
        source="payment.amount", max_digits=10, decimal_places=2
    )
    message = serializers.CharField()
    created_at = serializers.DateTimeField()

    def get_contributor_name(self, obj) -> str | None:
        return None if obj.anonymous else obj.user.name
