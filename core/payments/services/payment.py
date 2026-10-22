import os
import re
from decimal import Decimal

import mercadopago
from rest_framework import exceptions

from core.payments.models.payment import Payment
from core.payments.response_messages import MSG_PAYMENT_PROVIDER_UNAVAILABLE

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")


def _sdk() -> mercadopago.SDK:
    return mercadopago.SDK(MP_ACCESS_TOKEN)


class PaymentService:
    @staticmethod
    def create_pix_payment(
        user, title: str, amount: Decimal, cpf: str, name: str, notification_url: str
    ) -> dict:
        """Creates a local Payment and generates a Mercado Pago PIX QR Code & Copia e Cola."""
        clean_cpf = re.sub(r"\D", "", cpf)
        parts = name.strip().split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else first_name

        payment = Payment.objects.create(
            user=user,
            title=title,
            amount=amount,
            payer_cpf=clean_cpf,
            payer_name=name.strip(),
        )

        payload = {
            "transaction_amount": float(amount),
            "description": title,
            "payment_method_id": "pix",
            "payer": {
                "email": user.email,
                "first_name": first_name,
                "last_name": last_name,
                "identification": {
                    "type": "CPF",
                    "number": clean_cpf,
                },
            },
            "external_reference": str(payment.id),
            "notification_url": notification_url,
        }

        result = _sdk().payment().create(payload)
        if result["status"] not in (200, 201):
            payment.delete()
            raise exceptions.APIException(MSG_PAYMENT_PROVIDER_UNAVAILABLE)

        data = result["response"]
        tx_data = data.get("point_of_interaction", {}).get("transaction_data", {})

        payment.provider_payment_id = str(data.get("id", ""))
        payment.status = data.get("status", Payment.Status.PENDING)
        payment.qr_code = tx_data.get("qr_code", "")
        payment.qr_code_base64 = tx_data.get("qr_code_base64", "")
        payment.ticket_url = tx_data.get("ticket_url", "")
        payment.save(
            update_fields=[
                "provider_payment_id",
                "status",
                "qr_code",
                "qr_code_base64",
                "ticket_url",
                "updated_at",
            ]
        )

        return {
            "payment_id": payment.id,
            "status": payment.status,
            "qr_code": payment.qr_code,
            "qr_code_base64": payment.qr_code_base64,
            "ticket_url": payment.ticket_url,
        }

    # Backward compatibility alias
    create_checkout = create_pix_payment

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
