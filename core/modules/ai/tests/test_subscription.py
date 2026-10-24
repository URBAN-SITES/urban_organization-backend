from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models.user import User
from core.modules.payments.models.payment import Payment
from core.modules.payments.services.payment import PAYMENT_AMOUNT, PaymentService
from core.serializers.user import UserUpdateSelfSerializer


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SubscriberAccessTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("subscriber@test.com", "test-password")
        self.other = User.objects.create_user("other@test.com", "test-password")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def payment(self, **kwargs):
        data = dict(
            user=self.user,
            title="Pro",
            amount=PAYMENT_AMOUNT,
            status="approved",
            provider_payment_id="123",
        )
        data.update(kwargs)
        return Payment.objects.create(**data)

    def test_flag_is_read_only_and_only_in_own_profile(self):
        response = self.client.get("/api/v1/users/me/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_subscriber"])
        self.assertEqual(response.data["subscription_price"], str(PAYMENT_AMOUNT))
        serializer = UserUpdateSelfSerializer(
            self.user, data={"is_subscriber": True}, partial=True
        )
        self.assertFalse(serializer.is_valid())
        self.assertFalse(self.user.is_subscriber)

    @patch("core.modules.ai.views.ask.AssistantService.ask")
    @patch("core.modules.ai.views.analysis.AIAnalysisService.analyze")
    def test_free_user_cannot_call_any_ai_endpoint(self, analyze, ask):
        for url in ("ask", "analyze"):
            response = self.client.post(f"/api/v1/ai/{url}/", {}, format="json")
            self.assertEqual(response.status_code, 403)
        analyze.assert_not_called()
        ask.assert_not_called()

    @patch.dict("os.environ", {"AI_TEMPORARY_ACCESS_EMAILS": "subscriber@test.com"})
    @patch("core.modules.ai.views.ask.AssistantService.ask")
    @patch("core.modules.ai.views.analysis.AIAnalysisService.analyze")
    def test_temporary_access_is_limited_to_the_named_user_and_assistant(
        self, analyze, ask
    ):
        ask.return_value = {"answer": "OK", "actions": []}
        self.assertEqual(
            self.client.post("/api/v1/ai/ask/", {"prompt": "hello"}).status_code,
            200,
        )
        self.assertEqual(
            self.client.post("/api/v1/ai/analyze/", {}, format="multipart").status_code,
            403,
        )
        other = APIClient()
        other.force_authenticate(self.other)
        self.assertEqual(
            other.post("/api/v1/ai/ask/", {"prompt": "hello"}).status_code, 403
        )
        ask.assert_called_once()
        analyze.assert_not_called()

    def test_only_confirmed_own_payment_grants_access(self):
        payment = self.payment(status="pending")
        for status in ("pending", "in_process", "rejected", "cancelled", "refunded"):
            Payment.objects.filter(pk=payment.pk).update(status=status)
            self.assertFalse(self.user.is_subscriber)
        self.payment(user=self.other)
        self.assertFalse(self.user.is_subscriber)
        Payment.objects.filter(pk=payment.pk).update(status="approved")
        self.assertTrue(self.user.is_subscriber)
        self.assertTrue(self.client.get("/api/v1/users/me/").data["is_subscriber"])

    def test_invalid_price_or_missing_provider_id_does_not_grant_access(self):
        self.payment(amount="0.01")
        self.payment(provider_payment_id="")
        self.assertFalse(self.user.is_subscriber)

    @patch("core.modules.payments.services.payment._sdk")
    def test_webhook_sync_grants_and_refund_revokes_without_stale_flag(self, sdk):
        payment = self.payment(status="pending")
        for status in ("approved", "approved", "refunded"):
            sdk.return_value.payment.return_value.get.return_value = {
                "status": 200,
                "response": {
                    "id": 123,
                    "status": status,
                    "external_reference": str(payment.pk),
                },
            }
            PaymentService.sync_from_provider("123")
            self.assertEqual(self.user.is_subscriber, status == "approved")
        self.assertEqual(Payment.objects.count(), 1)

    @patch("core.modules.ai.views.ask.AssistantService.ask")
    def test_approved_user_calls_ai_and_refund_blocks_next_request(self, ask):
        payment = self.payment()
        ask.return_value = {"answer": "OK", "actions": []}
        self.assertEqual(
            self.client.post("/api/v1/ai/ask/", {"prompt": "hello"}).status_code, 200
        )
        Payment.objects.filter(pk=payment.pk).update(status="refunded")
        self.assertEqual(
            self.client.post("/api/v1/ai/ask/", {"prompt": "hello"}).status_code, 403
        )
        ask.assert_called_once()
