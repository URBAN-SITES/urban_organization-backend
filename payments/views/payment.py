from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.views import APIView

from payments.models.payment import Payment
from payments.serializers.payment import (
    CheckoutCreateSerializer,
    CheckoutResponseSerializer,
    PaymentSerializer,
)
from payments.services.payment import PaymentService


class PaymentListCreateView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user)

    @extend_schema(summary="List my payments")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Create a Mercado Pago checkout",
        description="Returns `checkout_url`; redirect the user there. In a real flow compute `amount` server-side from your product instead of trusting the client.",
        request=CheckoutCreateSerializer,
        responses={201: CheckoutResponseSerializer},
    )
    def post(self, request):
        serializer = CheckoutCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = PaymentService.create_checkout(
            user=request.user,
            title=serializer.validated_data["title"],
            amount=serializer.validated_data["amount"],
            notification_url=request.build_absolute_uri(reverse("payments:webhook")),
        )
        return Response(result, status.HTTP_201_CREATED)


class PaymentWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(summary="Mercado Pago webhook", request=None, responses={200: None})
    def post(self, request):
        topic = request.data.get("type") or request.query_params.get("type")
        provider_payment_id = request.data.get("data", {}).get(
            "id"
        ) or request.query_params.get("data.id")
        if topic == "payment" and provider_payment_id:
            PaymentService.sync_from_provider(str(provider_payment_id))
        # always 200, otherwise Mercado Pago keeps retrying
        return Response(status=status.HTTP_200_OK)
