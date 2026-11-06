from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.kanban.serializers.task import (
    BurndownSerializer,
    FollowSerializer,
    TaskSerializer,
    TrashedTaskSerializer,
)
from core.modules.kanban.services.cycle import CycleService
from core.modules.kanban.services.follow import FollowService
from core.modules.kanban.services.task import TaskService


@extend_schema(tags=["Tarefas"])
class TrashListView(ListAPIView):
    """Tasks deleted in the last 30 days (editor+), newest first."""

    permission_classes = [IsAuthenticated]
    serializer_class = TrashedTaskSerializer

    @extend_schema(summary="List a sector's deleted tasks (trash)")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return TaskService.trash(self.request.user, self.kwargs["sector_id"]).annotate(
            subtask_count=Count(
                "subtasks", filter=Q(subtasks__is_active=False), distinct=True
            )
        )


@extend_schema(tags=["Tarefas"])
class TaskRestoreView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Bring a deleted task (and its subtasks) back (editor+)",
        request=None,
        responses={200: TaskSerializer},
    )
    def post(self, request, task_id):
        task = TaskService.restore(request.user, task_id)
        return Response(TaskSerializer(task).data)


@extend_schema(tags=["Tarefas"])
class TaskArchiveView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Archive a task: it leaves the board (editor+)",
        request=None,
        responses={200: TaskSerializer},
    )
    def put(self, request, task_id):
        return Response(
            TaskSerializer(TaskService.set_archived(request.user, task_id, True)).data
        )

    @extend_schema(
        summary="Unarchive a task (editor+)",
        request=None,
        responses={200: TaskSerializer},
    )
    def delete(self, request, task_id):
        return Response(
            TaskSerializer(TaskService.set_archived(request.user, task_id, False)).data
        )


@extend_schema(tags=["Tarefas"])
class TaskFollowView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Whether you follow a task", responses={200: FollowSerializer}
    )
    def get(self, request, task_id):
        return Response(FollowService.state(request.user, task_id))

    @extend_schema(
        summary="Follow a task: comments and status changes notify you",
        request=None,
        responses={200: FollowSerializer},
    )
    def put(self, request, task_id):
        return Response(FollowService.set(request.user, task_id, True))

    @extend_schema(
        summary="Stop following a task", request=None, responses={200: FollowSerializer}
    )
    def delete(self, request, task_id):
        return Response(FollowService.set(request.user, task_id, False))


@extend_schema(tags=["Tarefas"])
class CycleBurndownView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Open tasks and points at the end of each cycle day",
        responses={200: BurndownSerializer},
    )
    def get(self, request, cycle_id):
        return Response(
            BurndownSerializer(CycleService.burndown(request.user, cycle_id)).data
        )
