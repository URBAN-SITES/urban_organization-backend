import os

import mercadopago
from rest_framework import exceptions

from core.modules.payments.models.payment import Payment
from core.modules.payments.response_messages import MSG_PAYMENT_PROVIDER_UNAVAILABLE

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")


def _sdk() -> mercadopago.SDK:
    return mercadopago.SDK(MP_ACCESS_TOKEN)


class PaymentService:
    """Mercado Pago para as cobranças das tarefas (crowdfunding). O plano pago da IA saiu."""

    @staticmethod
    def _request_options(payment: Payment) -> mercadopago.config.RequestOptions:
        request_options = mercadopago.config.RequestOptions()
        request_options.custom_headers = {"x-idempotency-key": str(payment.id)}
        return request_options

    @staticmethod
    def _create_at_provider(payment: Payment, payload: dict) -> dict:
        try:
            result = (
                _sdk()
                .payment()
                .create(payload, PaymentService._request_options(payment))
            )
        except Exception as error:
            payment.delete()
            raise exceptions.APIException(MSG_PAYMENT_PROVIDER_UNAVAILABLE) from error

        if result.get("status") not in (200, 201):
            payment.delete()
            raise exceptions.APIException(MSG_PAYMENT_PROVIDER_UNAVAILABLE)
        return result.get("response", {})

    @staticmethod
    def sync_payment(payment: Payment) -> bool:
        """Refresh one local payment using the authoritative provider response."""
        if not payment.provider_payment_id:
            return False

        try:
            result = _sdk().payment().get(payment.provider_payment_id)
        except Exception as error:
            raise exceptions.APIException(MSG_PAYMENT_PROVIDER_UNAVAILABLE) from error

        if result.get("status") != 200:
            raise exceptions.APIException(MSG_PAYMENT_PROVIDER_UNAVAILABLE)

        data = result.get("response", {})
        if (
            str(data.get("id", "")) != payment.provider_payment_id
            or str(data.get("external_reference", "")) != str(payment.id)
            or data.get("status") not in Payment.Status.values
        ):
            return False

        payment.status = data["status"]
        payment.save(update_fields=["status", "updated_at"])
        return True

    @staticmethod
    def sync_pending_for_user(user) -> None:
        pending = Payment.objects.filter(
            user=user,
            status__in=(Payment.Status.PENDING, Payment.Status.IN_PROCESS),
        ).exclude(provider_payment_id="")
        for payment in pending:
            PaymentService.sync_payment(payment)

    @staticmethod
    def sync_from_provider(provider_payment_id: str) -> bool:
        """Resolve a webhook ID locally, then verify it against Mercado Pago."""
        payment = Payment.objects.filter(
            provider_payment_id=provider_payment_id
        ).first()
        if payment is None:
            return False
        return PaymentService.sync_payment(payment)
