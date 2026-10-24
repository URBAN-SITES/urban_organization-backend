from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.ai.permissions import IsSubscriber
from core.modules.ai.serializers.ask import AIAnswerSerializer, AIAskSerializer
from core.modules.ai.services.assistant import AssistantService


@extend_schema(tags=["IA"])
class AIAskView(APIView):
    permission_classes = [IsAuthenticated, IsSubscriber]

    # Documentation
    @extend_schema(
        summary="Ask the assistant to operate the workspace (excluding payments)",
        request=AIAskSerializer,
        responses={200: AIAnswerSerializer},
    )

    # Chat
    def post(self, request):
        serializer = AIAskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = AssistantService.ask(request.user, **serializer.validated_data)
        response = Response(result, status.HTTP_200_OK)
        response["Cache-Control"] = "no-store"
        return response
