from unittest import mock

from django.test import TestCase

from core.models.user import User
from payments.models.payment import Payment


class PaymentFlowTests(TestCase):
    def setUp(self):
        User.objects.create_user("a@a.com", "S3cure-pass!", name="A")
        self.client.post(
            "/api/login/", {"email": "a@a.com", "password": "S3cure-pass!"}
        )
        self.sdk = mock.patch("payments.services.payment._sdk").start().return_value
        self.addCleanup(mock.patch.stopall)

    def test_checkout_then_webhook_approves_payment(self):
        self.sdk.preference().create.return_value = {
            "status": 201,
            "response": {"id": "pref-1", "init_point": "https://mp.test/checkout"},
        }
        response = self.client.post(
            "/api/payments/", {"title": "Ticket", "amount": "10.00"}
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["checkout_url"], "https://mp.test/checkout")

        payment = Payment.objects.get()
        self.sdk.payment().get.return_value = {
            "status": 200,
            "response": {
                "id": 99,
                "status": "approved",
                "external_reference": str(payment.id),
            },
        }
        self.client.post(
            "/api/payments/webhook/",
            {"type": "payment", "data": {"id": "99"}},
            content_type="application/json",
        )

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.APPROVED)
        self.assertEqual(payment.provider_payment_id, "99")

    def test_provider_failure_does_not_leave_payment(self):
        self.sdk.preference().create.return_value = {"status": 400, "response": {}}
        response = self.client.post(
            "/api/payments/", {"title": "Ticket", "amount": "10.00"}
        )
        self.assertEqual(response.status_code, 500)
        self.assertFalse(Payment.objects.exists())
