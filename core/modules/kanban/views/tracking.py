"""Timer and time entries, workload, and exports (Excel sheet, PDF report)."""

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.kanban.serializers.tracking import (
    ManualTimeSerializer,
    MyTimerSerializer,
    RunningTimerSerializer,
    StoppedTimerSerializer,
    TaskTimeSerializer,
    TimeEntrySerializer,
    WorkloadSerializer,
)
from core.modules.kanban.services.exports import ExportService
from core.modules.kanban.services.tracking import TimeService, WorkloadService
from core.modules.organizations.services.organization import OrganizationService


def _file(content: bytes, name: str, kind: str) -> HttpResponse:
    response = HttpResponse(content, content_type=kind)
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    response["Cache-Control"] = "no-store"
    return response


@extend_schema(tags=["Tarefas"])
class MyTimerView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="My running timer ({timer: null} when none)",
        responses={200: MyTimerSerializer},
    )
    def get(self, request):
        entry = TimeService.running(request.user)
        return Response(
            {"timer": RunningTimerSerializer(entry).data if entry else None}
        )

    @extend_schema(
        summary="Stop my running timer",
        request=None,
        responses={200: StoppedTimerSerializer},
    )
    def delete(self, request):
        entry = TimeService.stop(request.user)
        return Response({"stopped": TimeEntrySerializer(entry).data if entry else None})


@extend_schema(tags=["Tarefas"])
class TaskTimerView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Start a timer on this task (stops one running elsewhere; editor+)",
        request=None,
        responses={200: RunningTimerSerializer},
    )
    def post(self, request, task_id):
        entry = TimeService.start(request.user, task_id)
        return Response(RunningTimerSerializer(entry).data)


@extend_schema(tags=["Tarefas"])
class TaskTimeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Time logged on a task (total and the last 100 entries)",
        responses={200: TaskTimeSerializer},
    )
    def get(self, request, task_id):
        return Response(
            TaskTimeSerializer(TimeService.for_task(request.user, task_id)).data
        )

    @extend_schema(
        summary="Log time by hand (editor+)",
        request=ManualTimeSerializer,
        responses={201: TimeEntrySerializer},
    )
    def post(self, request, task_id):
        serializer = ManualTimeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = TimeService.add(request.user, task_id, serializer.validated_data)
        return Response(TimeEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Tarefas"])
class TimeEntryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Remove a time entry of mine", responses={204: None})
    def delete(self, request, entry_id):
        TimeService.delete(request.user, entry_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Tarefas"])
class WorkloadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Open work, deadlines and logged hours per person of a sector",
        responses={200: WorkloadSerializer},
    )
    def get(self, request, sector_id):
        return Response(WorkloadService.for_sector(request.user, sector_id))


@extend_schema(tags=["Tarefas"])
class TaskExportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Download a sector's tasks as an Excel sheet (.xlsx)",
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def get(self, request, sector_id):
        name, content = ExportService.tasks_xlsx(request.user, sector_id)
        return _file(
            content,
            name,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


@extend_schema(tags=["Setores"])
class ReportPdfView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Download the delivery report as PDF (7, 30 or 90 days)",
        parameters=[OpenApiParameter("days", int, required=False)],
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def get(self, request, organization_id):
        days = serializers.ChoiceField(choices=(7, 30, 90), default=30).run_validation(
            request.query_params.get("days") or serializers.empty
        )
        membership = OrganizationService.get_membership(request.user, organization_id)
        content = ExportService.report_pdf(
            request.user, organization_id, int(days), membership.organization.name
        )
        return _file(content, f"relatorio-{days}-dias.pdf", "application/pdf")
