"""Saved views, custom fields, task templates and bulk edits of a project."""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.kanban.serializers.workflow import (
    BulkResultSerializer,
    BulkSerializer,
    CustomFieldSerializer,
    FieldValueSerializer,
    SavedViewSerializer,
    TaskTemplateSerializer,
)
from core.modules.kanban.services.workflow import (
    BulkService,
    CustomFieldService,
    SavedViewService,
    TemplateService,
)


def _crud(service, serializer_class, name: str, who: str):
    """List/create under a sector and patch/delete by id, short and alike."""

    @extend_schema(tags=["Tarefas"])
    class ListCreate(APIView):
        permission_classes = [IsAuthenticated]

        @extend_schema(
            summary=f"List a sector's {name}",
            responses={200: serializer_class(many=True)},
        )
        def get(self, request, sector_id):
            rows = service.list_for(request.user, sector_id)
            return Response(serializer_class(rows, many=True).data)

        @extend_schema(
            summary=f"Create a {name[:-1]} ({who})",
            request=serializer_class,
            responses={201: serializer_class},
        )
        def post(self, request, sector_id):
            serializer = serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)
            row = service.create(request.user, sector_id, serializer.validated_data)
            return Response(serializer_class(row).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=["Tarefas"])
    class Detail(APIView):
        permission_classes = [IsAuthenticated]

        @extend_schema(
            summary=f"Change a {name[:-1]} ({who})",
            request=serializer_class,
            responses={200: serializer_class},
        )
        def patch(self, request, pk):
            serializer = serializer_class(data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            row = service.update(request.user, pk, serializer.validated_data)
            return Response(serializer_class(row).data)

        @extend_schema(summary=f"Delete a {name[:-1]} ({who})", responses={204: None})
        def delete(self, request, pk):
            service.delete(request.user, pk)
            return Response(status=status.HTTP_204_NO_CONTENT)

    ListCreate.__name__ = f"{serializer_class.__name__}ListCreateView"
    Detail.__name__ = f"{serializer_class.__name__}DetailView"
    return ListCreate, Detail


SavedViewListCreateView, SavedViewDetailView = _crud(
    SavedViewService, SavedViewSerializer, "saved views", "owner or manager"
)
CustomFieldListCreateView, CustomFieldDetailView = _crud(
    CustomFieldService, CustomFieldSerializer, "custom fields", "manager"
)
TemplateListCreateView, TemplateDetailView = _crud(
    TemplateService, TaskTemplateSerializer, "task templates", "editor+"
)


@extend_schema(tags=["Tarefas"])
class TaskFieldValuesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Custom field values of a task",
        responses={200: FieldValueSerializer(many=True)},
    )
    def get(self, request, task_id):
        return Response(CustomFieldService.values_for(request.user, task_id))


@extend_schema(tags=["Tarefas"])
class TaskFieldValueView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Set (or clear, with null) a custom field of a task (editor+)",
        request=FieldValueSerializer,
        responses={200: FieldValueSerializer},
    )
    def put(self, request, task_id, field_id):
        serializer = FieldValueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = CustomFieldService.set_value(
            request.user, task_id, field_id, serializer.validated_data["value"]
        )
        return Response(FieldValueSerializer(data).data)


@extend_schema(tags=["Tarefas"])
class TaskBulkView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Change, archive or delete many tasks at once (editor+)",
        request=BulkSerializer,
        responses={200: BulkResultSerializer},
    )
    def post(self, request, sector_id):
        serializer = BulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        task_ids = data.pop("task_ids")
        count = BulkService.apply(request.user, sector_id, task_ids, data)
        return Response({"updated": count})
