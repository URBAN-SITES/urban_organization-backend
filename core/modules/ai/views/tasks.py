from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.ai.permissions import IsSubscriber
from core.modules.ai.response_messages import MSG_AI_BUSY
from core.modules.ai.serializers.ask import (
    AITaskCreateSerializer,
    AITaskOptionsQuerySerializer,
)
from core.modules.ai.services.quick_task import (
    create_from_draft,
    person_dict,
    sector_people,
)
from core.modules.kanban.services.sector import Role, SectorService

REQUEST_TTL = 86400


@extend_schema(tags=["IA"])
class AITaskOptionsView(APIView):
    """People who can be assigned in a sector; feeds the draft card selectors."""

    permission_classes = [IsAuthenticated, IsSubscriber]

    @extend_schema(
        summary="List assignable people of a sector",
        parameters=[AITaskOptionsQuerySerializer],
    )
    def get(self, request):
        query = AITaskOptionsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        sector, _role = SectorService.get_sector(
            request.user, query.validated_data["sector_id"], Role.EDITOR
        )
        _everyone, in_sector = sector_people(sector)
        response = Response({"people": [person_dict(u) for u in in_sector]})
        response["Cache-Control"] = "no-store"
        return response


@extend_schema(tags=["IA"])
class AITaskCreateView(APIView):
    """Create the task the user confirmed in the draft card (no model involved)."""

    permission_classes = [IsAuthenticated, IsSubscriber]

    @extend_schema(
        summary="Create a task from a confirmed assistant draft",
        request=AITaskCreateSerializer,
    )
    def post(self, request):
        serializer = AITaskCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        request_key = f"ai:task:{request.user.pk}:{data.pop('request_id')}"
        # A double click or a retry returns the same task instead of a second one.
        previous = cache.get(request_key)
        if previous:
            return Response(previous, status.HTTP_200_OK)
        if not cache.add(request_key + ":lock", True, timeout=60):
            raise exceptions.Throttled(detail=MSG_AI_BUSY)
        try:
            sector_id = data.pop("sector_id")
            task = create_from_draft(request.user, sector_id, **data)
            cache.set(request_key, task, REQUEST_TTL)
        finally:
            cache.delete(request_key + ":lock")
        response = Response(task, status.HTTP_201_CREATED)
        response["Cache-Control"] = "no-store"
        return response
