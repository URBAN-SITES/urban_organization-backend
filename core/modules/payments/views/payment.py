from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.views import APIView

from core.modules.payments.models.payment import Payment
from core.modules.payments.serializers.payment import (
    PaymentCreateSerializer,
    PaymentSerializer,
    PixPaymentResponseSerializer,
)
from core.modules.payments.services.payment import PaymentService


class PaymentListCreateView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user)

    @extend_schema(summary="List my payments")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Create a Mercado Pago PIX payment",
        description="Generates a PIX QR Code & Copia e Cola with payer CPF and full name.",
        request=PaymentCreateSerializer,
        responses={201: PixPaymentResponseSerializer},
    )
    def post(self, request):
        serializer = PaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = PaymentService.create_pix_payment(
            user=request.user,
            title=serializer.validated_data["title"],
            amount=serializer.validated_data["amount"],
            cpf=serializer.validated_data["cpf"],
            name=serializer.validated_data["name"],
            notification_url=request.build_absolute_uri(reverse("v1:payments:webhook")),
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
