import re
from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from core.modules.payments.models.payment import Payment


class PaymentCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.01")
    )
    cpf = serializers.CharField(max_length=14, required=True)
    name = serializers.CharField(max_length=255, required=True)

    def validate_cpf(self, value):
        clean = re.sub(r"\D", "", value)
        if len(clean) != 11:
            raise serializers.ValidationError(_("CPF must have 11 digits."))
        return clean


# Alias for backward compatibility if referenced elsewhere
CheckoutCreateSerializer = PaymentCreateSerializer


class PixPaymentResponseSerializer(serializers.Serializer):
    payment_id = serializers.UUIDField()
    status = serializers.CharField()
    qr_code = serializers.CharField()
    qr_code_base64 = serializers.CharField()
    ticket_url = serializers.URLField(allow_blank=True)


CheckoutResponseSerializer = PixPaymentResponseSerializer


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            "id",
            "title",
            "amount",
            "status",
            "payer_name",
            "payer_cpf",
            "qr_code",
            "qr_code_base64",
            "ticket_url",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
