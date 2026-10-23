import re

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from core.modules.payments.models.payment import Payment


class FixedAmountPaymentSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)

    def validate(self, attrs):
        initial_data = getattr(self, "initial_data", None) or {}
        if "amount" in initial_data:
            raise serializers.ValidationError(
                {"amount": _("The payment amount is defined by the server.")}
            )
        return attrs

    def validate_cpf(self, value):
        clean = re.sub(r"\D", "", value)
        if len(clean) != 11:
            raise serializers.ValidationError(_("CPF must have 11 digits."))
        return clean


class PaymentPixCreateSerializer(FixedAmountPaymentSerializer):
    cpf = serializers.CharField(max_length=14, required=True)
    name = serializers.CharField(max_length=255, required=True)


class PixPaymentResponseSerializer(serializers.Serializer):
    payment_id = serializers.UUIDField()
    status = serializers.CharField()
    qr_code = serializers.CharField()
    qr_code_base64 = serializers.CharField()
    ticket_url = serializers.URLField(allow_blank=True)


class PaymentCardCreateSerializer(FixedAmountPaymentSerializer):
    cpf = serializers.CharField(max_length=14, required=True)
    email = serializers.EmailField(required=True)
    token = serializers.CharField(max_length=255, required=True, write_only=True)
    installments = serializers.IntegerField(min_value=1, required=True)
    payment_method_id = serializers.CharField(max_length=50, required=True)
    issuer_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class CardPaymentResponseSerializer(serializers.Serializer):
    payment_id = serializers.UUIDField()
    status = serializers.CharField()
    status_detail = serializers.CharField(allow_blank=True)


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


# Backward-compatible names used by earlier versions of this module.
PaymentCreateSerializer = PaymentPixCreateSerializer
CheckoutCreateSerializer = PaymentPixCreateSerializer
CheckoutResponseSerializer = PixPaymentResponseSerializer
CheckoutPixCreateSerializer = PaymentPixCreateSerializer
CheckoutPixResponseSerializer = PixPaymentResponseSerializer
CheckoutCardCreateSerializer = PaymentCardCreateSerializer
CheckoutCardResponseSerializer = CardPaymentResponseSerializer
PaymentPixSerializer = PaymentSerializer
PaymentCardSerializer = PaymentSerializer
