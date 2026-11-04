"""Automation rules, file imports and the read-only public link of a project."""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.modules.kanban.serializers.automation import (
    AutomationRuleSerializer,
    ImportResultSerializer,
    ImportSerializer,
    PublicBoardSerializer,
    PublicLinkSerializer,
)
from core.modules.kanban.services.automation import AutomationService
from core.modules.kanban.services.importer import ImportService
from core.modules.kanban.services.sharing import PublicLinkService
from core.modules.kanban.views.workflow import _crud

AutomationListCreateView, AutomationDetailView = _crud(
    AutomationService, AutomationRuleSerializer, "automations", "manager"
)


@extend_schema(tags=["Tarefas"])
class TaskImportView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        summary="Import tasks from a Trello (JSON) or Jira/Asana/Plane (CSV) export; "
        "dry_run=true only previews (editor+)",
        request={"multipart/form-data": ImportSerializer},
        responses={200: ImportResultSerializer},
    )
    def post(self, request, sector_id):
        serializer = ImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = ImportService.run(
            request.user, sector_id, data["source"], data["file"], data["dry_run"]
        )
        return Response(ImportResultSerializer(result).data)


@extend_schema(tags=["Setores"])
class PublicLinkView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="The project's public link token (manager)",
        responses={200: PublicLinkSerializer},
    )
    def get(self, request, sector_id):
        return Response({"token": PublicLinkService.get(request.user, sector_id)})

    @extend_schema(
        summary="Turn the read-only public link on (manager)",
        request=None,
        responses={200: PublicLinkSerializer},
    )
    def post(self, request, sector_id):
        return Response({"token": PublicLinkService.enable(request.user, sector_id)})

    @extend_schema(summary="Turn the public link off (manager)", responses={204: None})
    def delete(self, request, sector_id):
        PublicLinkService.disable(request.user, sector_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Setores"])
class PublicBoardView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public"

    @extend_schema(
        summary="Read-only board behind a public link (no login)",
        responses={200: PublicBoardSerializer},
    )
    def get(self, request, token):
        return Response(PublicBoardSerializer(PublicLinkService.board(token)).data)
