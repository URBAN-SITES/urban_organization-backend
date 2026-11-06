from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.modules.payments.services.payment import PaymentService

PAYMENT_NOTIFICATION_URL = "https://3009.michalski.app/api/v1/payments/webhook/"


@extend_schema(tags=["Pagamentos"])
class PaymentWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    # its own generous bucket: the provider's few IPs must not share the anonymous limit
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "webhook"

    @extend_schema(summary="Mercado Pago webhook", request=None, responses={200: None})
    def post(self, request):
        topic = request.data.get("type") or request.query_params.get("type")
        provider_payment_id = request.data.get("data", {}).get(
            "id"
        ) or request.query_params.get("data.id")
        if topic == "payment" and provider_payment_id:
            try:
                PaymentService.sync_from_provider(str(provider_payment_id))
            except APIException:
                # Mercado Pago retries webhooks. A manual status refresh can also
                # reconcile the payment if this attempt fails.
                pass
        # Always return 200, otherwise Mercado Pago keeps retrying.
        return Response(status=status.HTTP_200_OK)
