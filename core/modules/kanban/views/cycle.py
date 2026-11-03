from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.kanban.serializers.task import (
    CycleSerializer,
    TaskRelationsSerializer,
    TaskRelationWriteSerializer,
)
from core.modules.kanban.services.cycle import CycleService
from core.modules.kanban.services.relation import RelationService


@extend_schema(tags=["Tarefas"])
class CycleListCreateView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CycleSerializer

    @extend_schema(summary="List a sector's cycles (sprints) with progress")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return CycleService.list_for(self.request.user, self.kwargs["sector_id"])

    @extend_schema(
        summary="Create a cycle (editor+)",
        request=CycleSerializer,
        responses={201: CycleSerializer},
    )
    def post(self, request, sector_id):
        serializer = CycleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cycle = CycleService.create(request.user, sector_id, serializer.validated_data)
        return Response(CycleSerializer(cycle).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Tarefas"])
class CycleDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Rename or reschedule a cycle (editor+)",
        request=CycleSerializer,
        responses={200: CycleSerializer},
    )
    def patch(self, request, cycle_id):
        serializer = CycleSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        cycle = CycleService.update(request.user, cycle_id, serializer.validated_data)
        return Response(CycleSerializer(cycle).data)

    @extend_schema(
        summary="Delete a cycle; its tasks stay in the project (editor+)",
        responses={204: None},
    )
    def delete(self, request, cycle_id):
        CycleService.delete(request.user, cycle_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Tarefas"])
class TaskRelationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Tasks that block this one and tasks it blocks",
        responses={200: TaskRelationsSerializer},
    )
    def get(self, request, task_id):
        return Response(RelationService.for_task(request.user, task_id))

    @extend_schema(
        summary="Mark another task of the project as blocking/blocked by this one",
        request=TaskRelationWriteSerializer,
        responses={201: TaskRelationsSerializer},
    )
    def post(self, request, task_id):
        serializer = TaskRelationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = RelationService.add(
            request.user,
            task_id,
            serializer.validated_data["kind"],
            serializer.validated_data["task"],
        )
        return Response(data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Tarefas"])
class TaskRelationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Remove the link between two tasks", responses={204: None})
    def delete(self, request, task_id, other_id):
        RelationService.remove(request.user, task_id, other_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
