from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.websockets.auth import create_ticket


@extend_schema(tags=["Conta e Sessões"])
class WebSocketTicketView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Create a one-use ticket to open the realtime socket",
        request=None,
        responses={
            201: {"type": "object", "properties": {"ticket": {"type": "string"}}}
        },
    )
    def post(self, request):
        return Response(
            {"ticket": create_ticket(request.user)}, status.HTTP_201_CREATED
        )
