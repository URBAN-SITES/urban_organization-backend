from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.response_messages import MSG_QRCODE_DATA_INVALID
from core.utils.qrcode import make_qrcode_png

MAX_QRCODE_DATA_LENGTH = 1000


@extend_schema(tags=["Utilitários"])
class QRCodeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Generate a QR code PNG",
        parameters=[OpenApiParameter("data", str, required=True)],
        responses={(200, "image/png"): OpenApiTypes.BINARY},
    )
    def get(self, request):
        data = request.query_params.get("data", "")
        if not data or len(data) > MAX_QRCODE_DATA_LENGTH:
            raise ValidationError({"data": MSG_QRCODE_DATA_INVALID})
        return HttpResponse(make_qrcode_png(data), content_type="image/png")
