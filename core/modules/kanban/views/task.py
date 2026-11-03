import django_filters
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.kanban.models.task import Task
from core.modules.kanban.serializers.task import (
    TaskActivitySerializer,
    TaskCreateSerializer,
    TaskMoveSerializer,
    TaskSerializer,
    TaskUpdateSerializer,
)
from core.modules.kanban.services.activity import ActivityService
from core.modules.kanban.services.sector import Role
from core.modules.kanban.services.task import TaskService


class TaskFilter(django_filters.FilterSet):
    due_before = django_filters.DateFilter("due_date", lookup_expr="lte")
    due_after = django_filters.DateFilter("due_date", lookup_expr="gte")
    overdue = django_filters.BooleanFilter(method="filter_overdue")
    completed = django_filters.BooleanFilter(method="filter_completed")
    # without this filter archived tasks are left out (see get_queryset)
    archived = django_filters.BooleanFilter(method="filter_archived")
    key = django_filters.CharFilter(method="filter_key")
    label = django_filters.UUIDFilter(field_name="labels__id", distinct=True)

    class Meta:
        model = Task
        fields = {
            "status": ["exact"],
            "assignee": ["exact", "isnull"],
            "priority": ["exact", "in"],
            "due_date": ["isnull"],
            "parent": ["exact", "isnull"],
            "cycle": ["exact", "isnull"],
        }

    def filter_overdue(self, queryset, name, value):
        overdue = queryset.overdue()
        return overdue if value else queryset.exclude(pk__in=overdue.values("pk"))

    def filter_completed(self, queryset, name, value):
        return queryset.filter(completed_at__isnull=not value)

    def filter_archived(self, queryset, name, value):
        return queryset.filter(archived_at__isnull=not value)

    def filter_key(self, queryset, name, value):
        # "DEV-12" or just "12"
        number = value.rsplit("-", 1)[-1]
        return queryset.filter(sequence=number) if number.isdigit() else queryset.none()


@extend_schema(tags=["Tarefas"])
class TaskListCreateView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TaskSerializer
    filter_backends = [
        django_filters.rest_framework.DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]
    filterset_class = TaskFilter
    search_fields = ("title", "description")
    ordering_fields = (
        "position",
        "start_date",
        "due_date",
        "priority",
        "created_at",
        "completed_at",
    )

    @extend_schema(
        summary="List/search/filter the tasks of a sector",
        description=(
            "Filters: status, assignee, assignee__isnull, priority, priority__in "
            "(comma separated), label, parent, parent__isnull, cycle, cycle__isnull, "
            "due_date__isnull, archived (default: hidden), key (DEV-12), "
            "due_before, due_after, overdue, completed. `search` matches title and "
            "description."
        ),
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        tasks = TaskService.list_for(self.request.user, self.kwargs["sector_id"])
        if "archived" not in self.request.query_params:
            tasks = tasks.filter(archived_at__isnull=True)
        return tasks

    @extend_schema(
        summary="Create a task (editor+); defaults to the first to-do column",
        request=TaskCreateSerializer,
        responses={201: TaskSerializer},
    )
    def post(self, request, sector_id):
        serializer = TaskCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = TaskService.create(
            request.user, sector_id, dict(serializer.validated_data)
        )
        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Tarefas"])
class TaskDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Get a task", responses={200: TaskSerializer})
    def get(self, request, task_id):
        task, _sector, _role = TaskService.get_task(request.user, task_id, Role.VIEWER)
        return Response(TaskSerializer(task).data)

    @extend_schema(
        summary="Update a task (editor+). Use /move/ to change its column",
        request=TaskUpdateSerializer,
        responses={200: TaskSerializer},
    )
    def patch(self, request, task_id):
        serializer = TaskUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        task = TaskService.update(request.user, task_id, serializer.validated_data)
        return Response(TaskSerializer(task).data)

    @extend_schema(
        summary="Delete a task and its subtasks (editor+)", responses={204: None}
    )
    def delete(self, request, task_id):
        TaskService.delete(request.user, task_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Tarefas"])
class TaskMoveView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Move a task to a column/position (editor+)",
        request=TaskMoveSerializer,
        responses={200: TaskSerializer},
    )
    def post(self, request, task_id):
        serializer = TaskMoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = TaskService.move(
            request.user,
            task_id,
            serializer.validated_data["status"],
            serializer.validated_data["position"],
        )
        return Response(TaskSerializer(task).data)


@extend_schema(tags=["Tarefas"])
class TaskActivityListView(ListAPIView):
    """History of a task, newest first (paginated)."""

    permission_classes = [IsAuthenticated]
    serializer_class = TaskActivitySerializer

    @extend_schema(summary="List a task's change history")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        task, _sector, _role = TaskService.get_task(
            self.request.user, self.kwargs["task_id"]
        )
        return ActivityService.for_task(task)
