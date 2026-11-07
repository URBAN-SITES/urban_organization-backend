from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.ai.serializers.ask import (
    AIAnswerSerializer,
    AIAskSerializer,
    AIThreadDetailSerializer,
    AIThreadSerializer,
)
from core.modules.ai.services.assistant import AssistantService
from core.modules.ai.services.threads import ThreadService
from core.modules.kanban.services.sector import SectorService


@extend_schema(tags=["IA"])
class AIAskView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "ai"

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
        data = dict(serializer.validated_data)
        thread_id = data.pop("thread_id", None)
        if thread_id:
            # a saved conversation keeps its context after the short cache expires
            data["fallback_history"] = ThreadService.history(request.user, thread_id)

        result = AssistantService.ask(request.user, **data)
        if thread_id:
            ThreadService.record(
                request.user,
                thread_id,
                (data.get("context") or {}).get("sector_id"),
                data["prompt"],
                result,
                data.get("request_id"),
            )
        response = Response(result, status.HTTP_200_OK)
        response["Cache-Control"] = "no-store"
        return response


@extend_schema(tags=["IA"])
class AIThreadListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Saved assistant conversations (general, or one project's with ?sector=)",
        parameters=[OpenApiParameter("sector", str, required=False)],
        responses={200: AIThreadSerializer(many=True)},
    )
    def get(self, request):
        sector_id = request.query_params.get("sector") or None
        if sector_id:
            sector_id = serializers.UUIDField().run_validation(sector_id)
            SectorService.get_sector(request.user, sector_id)
        rows = ThreadService.list_for(request.user, sector_id)
        return Response(AIThreadSerializer(rows, many=True).data)


@extend_schema(tags=["IA"])
class AIThreadDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="One saved conversation with its messages",
        responses={200: AIThreadDetailSerializer},
    )
    def get(self, request, thread_id):
        thread = ThreadService.get(request.user, thread_id)
        return Response(AIThreadDetailSerializer(thread).data)

    @extend_schema(summary="Delete a saved conversation", responses={204: None})
    def delete(self, request, thread_id):
        ThreadService.delete(request.user, thread_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
