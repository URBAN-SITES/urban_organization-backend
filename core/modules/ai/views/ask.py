from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.ai.serializers.ask import AIAnswerSerializer, AIAskSerializer
from core.modules.ai.services.ask import AIService


@extend_schema(tags=["IA"])
class AIAskView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Ask the AI (Gemini)",
        request=AIAskSerializer,
        responses={200: AIAnswerSerializer},
    )
    def post(self, request):
        serializer = AIAskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        answer = AIService.ask(serializer.validated_data["prompt"])
        return Response({"answer": answer}, status.HTTP_200_OK)
