from unittest import mock

from django.test import TestCase

from core.models.user import User
from core.payments.models.payment import Payment


class PaymentFlowTests(TestCase):
    def setUp(self):
        User.objects.create_user("a@a.com", "S3cure-pass!", name="A")
        self.client.post(
            "/api/v1/login/", {"email": "a@a.com", "password": "S3cure-pass!"}
        )
        self.sdk = (
            mock.patch("core.payments.services.payment._sdk").start().return_value
        )
        self.addCleanup(mock.patch.stopall)

    def test_pix_creation_then_webhook_approves(self):
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
                "amount": "10.00",
                "cpf": "123.456.789-01",
                "name": "Maria Silva",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["qr_code"], "00020126580014br.gov.bcb.pix...")
        self.assertEqual(response.data["qr_code_base64"], "iVBORw0KGgo...")

        payment = Payment.objects.get()
        self.assertEqual(payment.payer_cpf, "12345678901")
        self.assertEqual(payment.payer_name, "Maria Silva")
        self.assertEqual(payment.provider_payment_id, "99")

        # Simulate webhook approval
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

    def test_invalid_cpf_fails(self):
        response = self.client.post(
            "/api/v1/payments/",
            {
                "title": "Ticket",
                "amount": "10.00",
                "cpf": "123",
                "name": "Maria Silva",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.exists())

    def test_provider_failure_does_not_leave_payment(self):
        self.sdk.payment().create.return_value = {"status": 400, "response": {}}
        response = self.client.post(
            "/api/v1/payments/",
            {
                "title": "Ticket",
                "amount": "10.00",
                "cpf": "12345678901",
                "name": "Maria Silva",
            },
        )
        self.assertEqual(response.status_code, 500)
        self.assertFalse(Payment.objects.exists())
