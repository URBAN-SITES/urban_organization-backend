import os
from decimal import Decimal

import mercadopago
from rest_framework import exceptions

from payments.models.payment import Payment
from payments.response_messages import MSG_PAYMENT_PROVIDER_UNAVAILABLE

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "")


def _sdk() -> mercadopago.SDK:
    return mercadopago.SDK(MP_ACCESS_TOKEN)


class PaymentService:
    @staticmethod
    def create_checkout(
        user, title: str, amount: Decimal, notification_url: str
    ) -> dict:
        """Creates a local Payment and a Mercado Pago Checkout Pro link to pay it."""
        payment = Payment.objects.create(user=user, title=title, amount=amount)
        preference = {
            "items": [
                {
                    "title": title,
                    "quantity": 1,
                    "unit_price": float(amount),
                    "currency_id": "BRL",
                }
            ],
            "payer": {"email": user.email},
            "external_reference": str(payment.id),
            "notification_url": notification_url,
        }
        if FRONTEND_URL:
            preference["back_urls"] = {
                "success": f"{FRONTEND_URL}/payments/success",
                "failure": f"{FRONTEND_URL}/payments/failure",
                "pending": f"{FRONTEND_URL}/payments/pending",
            }
            preference["auto_return"] = "approved"

        result = _sdk().preference().create(preference)
        if result["status"] != 201:
            payment.delete()
            raise exceptions.APIException(MSG_PAYMENT_PROVIDER_UNAVAILABLE)

        payment.preference_id = result["response"]["id"]
        payment.save(update_fields=["preference_id", "updated_at"])
        return {
            "payment_id": payment.id,
            "checkout_url": result["response"]["init_point"],
        }

    @staticmethod
    def sync_from_provider(provider_payment_id: str) -> None:
        """Webhook handler: trusts only what the Mercado Pago API returns, never the request body."""
        result = _sdk().payment().get(provider_payment_id)
        if result["status"] != 200:
            return
        data = result["response"]
        Payment.objects.filter(id=data.get("external_reference")).update(
            status=data["status"], provider_payment_id=str(data["id"])
        )
