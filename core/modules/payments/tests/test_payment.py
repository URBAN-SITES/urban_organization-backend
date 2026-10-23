from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from core.models.user import User
from core.modules.payments.models.payment import Payment


class PaymentFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user("a@a.com", "S3cure-pass!", name="A")
        login = self.client.post(
            "/api/v1/login/", {"email": "a@a.com", "password": "S3cure-pass!"}
        )
        self.assertEqual(login.status_code, 200)
        self.sdk = (
            mock.patch("core.modules.payments.services.payment._sdk")
            .start()
            .return_value
        )
        self.addCleanup(mock.patch.stopall)

    def test_pix_creation_uses_fixed_amount_then_webhook_approves(self):
        self.sdk.payment().create.return_value = {
            "status": 201,
            "response": {
                "id": 99,
                "status": "pending",
                "point_of_interaction": {
                    "transaction_data": {
                        "qr_code": "00020126580014br.gov.bcb.pix...",
                        "qr_code_base64": "iVBORw0KGgo...",
                        "ticket_url": "https://mp.test/ticket/99",
                    }
                },
            },
        }
        response = self.client.post(
            "/api/v1/payments/",
            {
                "title": "Ticket",
                "cpf": "123.456.789-01",
                "name": "Maria Silva",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["qr_code"], "00020126580014br.gov.bcb.pix...")

        payment = Payment.objects.get()
        self.assertEqual(payment.amount, Decimal("9.99"))
        self.assertEqual(payment.payer_cpf, "12345678901")
        self.assertEqual(payment.payer_name, "Maria Silva")
        self.assertEqual(payment.provider_payment_id, "99")

        provider_payload = self.sdk.payment().create.call_args.args[0]
        request_options = self.sdk.payment().create.call_args.args[1]
        self.assertEqual(provider_payload["transaction_amount"], 9.99)
        self.assertEqual(provider_payload["payment_method_id"], "pix")
        self.assertEqual(
            request_options.custom_headers["x-idempotency-key"], str(payment.id)
        )

        self.sdk.payment().get.return_value = {
            "status": 200,
            "response": {
                "id": 99,
                "status": "approved",
                "external_reference": str(payment.id),
            },
        }
        self.client.post(
            "/api/v1/payments/webhook/",
            {"type": "payment", "data": {"id": "99"}},
            content_type="application/json",
        )

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.APPROVED)

    def test_card_creation_sends_required_mercado_pago_fields(self):
        self.sdk.payment().create.return_value = {
            "status": 201,
            "response": {
                "id": 123,
                "status": "approved",
                "status_detail": "accredited",
            },
        }

        response = self.client.post(
            "/api/v1/payments/card/",
            {
                "title": "Subscription",
                "cpf": "123.456.789-01",
                "email": "payer@example.com",
                "token": "card-token",
                "installments": 1,
                "payment_method_id": "visa",
                "issuer_id": 25,
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], Payment.Status.APPROVED)
        self.assertEqual(response.data["status_detail"], "accredited")

        payment = Payment.objects.get()
        self.assertEqual(payment.amount, Decimal("9.99"))
        self.assertEqual(payment.provider_payment_id, "123")

        provider_payload = self.sdk.payment().create.call_args.args[0]
        self.assertEqual(
            provider_payload,
            {
                "transaction_amount": 9.99,
                "token": "card-token",
                "description": "Subscription",
                "installments": 1,
                "payment_method_id": "visa",
                "payer": {
                    "email": "payer@example.com",
                    "identification": {
                        "type": "CPF",
                        "number": "12345678901",
                    },
                },
                "external_reference": str(payment.id),
                "notification_url": "http://testserver/api/v1/payments/webhook/",
                "issuer_id": 25,
            },
        )

    def test_card_creation_accepts_missing_optional_issuer(self):
        self.sdk.payment().create.return_value = {
            "status": 201,
            "response": {"id": 123, "status": "pending"},
        }

        response = self.client.post(
            "/api/v1/payments/card/",
            {
                "title": "Subscription",
                "cpf": "12345678901",
                "email": "payer@example.com",
                "token": "card-token",
                "installments": 1,
                "payment_method_id": "master",
            },
        )

        self.assertEqual(response.status_code, 201)
        provider_payload = self.sdk.payment().create.call_args.args[0]
        self.assertNotIn("issuer_id", provider_payload)

    def test_amount_from_request_is_rejected_for_pix_and_card(self):
        pix_response = self.client.post(
            "/api/v1/payments/",
            {
                "title": "Ticket",
                "amount": "0.01",
                "cpf": "12345678901",
                "name": "Maria Silva",
            },
        )
        card_response = self.client.post(
            "/api/v1/payments/card/",
            {
                "title": "Subscription",
                "amount": "0.01",
                "cpf": "12345678901",
                "email": "payer@example.com",
                "token": "card-token",
                "installments": 1,
                "payment_method_id": "visa",
            },
        )

        self.assertEqual(pix_response.status_code, 400)
        self.assertEqual(card_response.status_code, 400)
        self.assertIn("amount", pix_response.data)
        self.assertIn("amount", card_response.data)
        self.assertFalse(Payment.objects.exists())
        self.sdk.payment().create.assert_not_called()

    def test_invalid_cpf_fails(self):
        response = self.client.post(
            "/api/v1/payments/",
            {"title": "Ticket", "cpf": "123", "name": "Maria Silva"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.exists())

    def test_provider_failure_does_not_leave_payment(self):
        self.sdk.payment().create.return_value = {"status": 400, "response": {}}
        response = self.client.post(
            "/api/v1/payments/card/",
            {
                "title": "Subscription",
                "cpf": "12345678901",
                "email": "payer@example.com",
                "token": "card-token",
                "installments": 1,
                "payment_method_id": "visa",
            },
        )
        self.assertEqual(response.status_code, 500)
        self.assertFalse(Payment.objects.exists())
