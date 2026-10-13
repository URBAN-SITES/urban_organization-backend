from decimal import Decimal

from rest_framework import serializers

from payments.models.payment import Payment


class CheckoutCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.01")
    )


class CheckoutResponseSerializer(serializers.Serializer):
    payment_id = serializers.UUIDField()
    checkout_url = serializers.URLField()


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ("id", "title", "amount", "status", "created_at", "updated_at")
        read_only_fields = fields
