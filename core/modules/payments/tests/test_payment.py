from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from core.models.user import User
from core.modules.payments.models.payment import Payment


class PaymentWebhookTests(TestCase):
    """O que sobrou de pagamentos: o retorno do Mercado Pago das cobranças das tarefas."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("a@a.com", "S3cure-pass!", name="A")
        self.sdk = (
            mock.patch("core.modules.payments.services.payment._sdk")
            .start()
            .return_value
        )
        self.addCleanup(mock.patch.stopall)
        self.payment = Payment.objects.create(
            user=self.user,
            title="Cobrança",
            amount=Decimal("25.00"),
            status=Payment.Status.PENDING,
            provider_payment_id="456",
        )

    def _provider_says(self, status, reference=None):
        self.sdk.payment().get.return_value = {
            "status": 200,
            "response": {
                "id": 456,
                "status": status,
                "external_reference": reference or str(self.payment.id),
            },
        }

    def _webhook(self):
        return self.client.post(
            "/api/v1/payments/webhook/",
            {"type": "payment", "data": {"id": "456"}},
            content_type="application/json",
        )

    def test_webhook_approves_after_checking_the_provider(self):
        self._provider_says("approved")
        self.assertEqual(self._webhook().status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.APPROVED)

    def test_webhook_ignores_mismatched_external_reference(self):
        self._provider_says("approved", reference="another-payment")
        self.assertEqual(self._webhook().status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    def test_webhook_answers_200_when_provider_is_down(self):
        self.sdk.payment().get.side_effect = RuntimeError("offline")
        self.assertEqual(self._webhook().status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)


class PlanCheckoutRemovedTests(TestCase):
    """A IA deixou de ser paga: não existe mais compra de plano."""

    def setUp(self):
        cache.clear()
        User.objects.create_user("a@a.com", "S3cure-pass!", name="A")
        login = self.client.post(
            "/api/v1/login/", {"email": "a@a.com", "password": "S3cure-pass!"}
        )
        self.assertEqual(login.status_code, 200)

    def test_plan_endpoints_are_gone(self):
        self.assertEqual(self.client.get("/api/v1/payments/").status_code, 404)
        self.assertEqual(self.client.post("/api/v1/payments/card/").status_code, 404)

    def test_me_has_no_subscription_fields(self):
        me = self.client.get("/api/v1/users/me/").data
        for field in ("is_subscriber", "has_assistant_access", "subscription_price"):
            self.assertNotIn(field, me)
