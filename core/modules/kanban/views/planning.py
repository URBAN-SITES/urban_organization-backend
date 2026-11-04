"""Epics, pages and the intake inbox of a project."""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.kanban.serializers.planning import (
    EpicSerializer,
    IntakeAcceptSerializer,
    IntakeDeclineSerializer,
    IntakeSerializer,
    PageListSerializer,
    PageSerializer,
)
from core.modules.kanban.services.planning import (
    EpicService,
    IntakeService,
    PageService,
)
from core.modules.kanban.views.workflow import _crud

EpicListCreateView, EpicDetailView = _crud(
    EpicService, EpicSerializer, "epics", "editor+"
)


@extend_schema(tags=["Tarefas"])
class PageListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="List a sector's pages (pinned first, then recent)",
        responses={200: PageListSerializer(many=True)},
    )
    def get(self, request, sector_id):
        rows = PageService.list_for(request.user, sector_id)
        return Response(PageListSerializer(rows, many=True).data)

    @extend_schema(
        summary="Create a page (editor+)",
        request=PageSerializer,
        responses={201: PageSerializer},
    )
    def post(self, request, sector_id):
        serializer = PageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        page = PageService.create(request.user, sector_id, serializer.validated_data)
        return Response(PageSerializer(page).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Tarefas"])
class PageDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Read a page", responses={200: PageSerializer})
    def get(self, request, pk):
        return Response(PageSerializer(PageService.get(request.user, pk)).data)

    @extend_schema(
        summary="Edit a page (editor+)",
        request=PageSerializer,
        responses={200: PageSerializer},
    )
    def patch(self, request, pk):
        serializer = PageSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        page = PageService.update(request.user, pk, serializer.validated_data)
        return Response(PageSerializer(page).data)

    @extend_schema(summary="Delete a page (editor+)", responses={204: None})
    def delete(self, request, pk):
        PageService.delete(request.user, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Tarefas"])
class IntakeListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Requests of a sector (editors see all, others only their own)",
        responses={200: IntakeSerializer(many=True)},
    )
    def get(self, request, sector_id):
        rows = IntakeService.list_for(request.user, sector_id)
        return Response(IntakeSerializer(rows, many=True).data)

    @extend_schema(
        summary="Send a request to a sector (anyone who sees it)",
        request=IntakeSerializer,
        responses={201: IntakeSerializer},
    )
    def post(self, request, sector_id):
        serializer = IntakeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = IntakeService.create(request.user, sector_id, serializer.validated_data)
        return Response(IntakeSerializer(row).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Tarefas"])
class IntakeAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Accept a request: it becomes a task (editor+)",
        request=IntakeAcceptSerializer,
        responses={200: IntakeSerializer},
    )
    def post(self, request, pk):
        serializer = IntakeAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = IntakeService.accept(request.user, pk, serializer.validated_data)
        return Response(IntakeSerializer(row).data)


@extend_schema(tags=["Tarefas"])
class IntakeDeclineView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Decline a request, with an optional note (editor+)",
        request=IntakeDeclineSerializer,
        responses={200: IntakeSerializer},
    )
    def post(self, request, pk):
        serializer = IntakeDeclineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = IntakeService.decline(
            request.user, pk, serializer.validated_data.get("note", "")
        )
        return Response(IntakeSerializer(row).data)
