import json
from urllib.parse import quote

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import ParseError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.modules.meetings.serializers.insight import (
    ActionTasksResultSerializer,
    ActionTasksSerializer,
    InsightSerializer,
)
from core.modules.meetings.serializers.meeting import (
    DownloadSerializer,
    JoinResultSerializer,
    JoinSerializer,
    MeetingListQuerySerializer,
    MeetingSerializer,
    MeetingWriteSerializer,
    RecordingSerializer,
)
from core.modules.meetings.services import livekit
from core.modules.meetings.services.insights import InsightService
from core.modules.meetings.services.meetings import (
    LiveKitWebhookService,
    MeetingService,
    RecordingService,
)


def _meeting(meeting_id, request):
    """Re-reads the meeting with what the serializer needs."""
    access = MeetingService.access(request.user, meeting_id)
    return MeetingSerializer(
        access.meeting, context={"user": request.user, "role": access.role}
    ).data


@extend_schema(tags=["Reuniões"])
class ProjectMeetingsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Meetings of a project",
        parameters=[MeetingListQuerySerializer],
        responses={200: MeetingSerializer(many=True)},
    )
    def get(self, request, sector_id):
        query = MeetingListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        meetings, role = MeetingService.list_for_project(
            request.user, sector_id, query.validated_data["when"]
        )
        return Response(
            MeetingSerializer(
                meetings, many=True, context={"user": request.user, "role": role}
            ).data
        )

    @extend_schema(
        summary="Schedule a meeting (editor)",
        request=MeetingWriteSerializer,
        responses={201: MeetingSerializer},
    )
    def post(self, request, sector_id):
        data = MeetingWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        meeting = MeetingService.create(request.user, sector_id, data.validated_data)
        return Response(_meeting(meeting.id, request), status=status.HTTP_201_CREATED)


@extend_schema(tags=["Reuniões"])
class MeetingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="One meeting", responses={200: MeetingSerializer})
    def get(self, request, meeting_id):
        return Response(_meeting(meeting_id, request))

    @extend_schema(
        summary="Edit a meeting (organizer or manager)",
        request=MeetingWriteSerializer,
        responses={200: MeetingSerializer},
    )
    def patch(self, request, meeting_id):
        data = MeetingWriteSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        MeetingService.update(request.user, meeting_id, data.validated_data)
        return Response(_meeting(meeting_id, request))

    @extend_schema(
        summary="Cancel a meeting and delete its recordings (organizer or manager)",
        responses={204: None},
    )
    def delete(self, request, meeting_id):
        MeetingService.delete(request.user, meeting_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Reuniões"])
class MeetingJoinView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Room token for an invited person who accepted the recording notice",
        request=JoinSerializer,
        responses={200: JoinResultSerializer},
    )
    def post(self, request, meeting_id):
        data = JoinSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(
            MeetingService.join(
                request.user, meeting_id, data.validated_data["consent"]
            )
        )


@extend_schema(tags=["Reuniões"])
class MeetingRecordingsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Recordings with signed URLs (download only for managers)",
        responses={200: RecordingSerializer(many=True)},
    )
    def get(self, request, meeting_id):
        access, recordings = RecordingService.list(request.user, meeting_id)
        recordings = list(recordings)
        links = {r.id: RecordingService.links(access, r) for r in recordings}
        return Response(
            RecordingSerializer(recordings, many=True, context={"links": links}).data
        )

    @extend_schema(
        summary="Start recording on the server (organizer or manager)",
        request=None,
        responses={201: RecordingSerializer},
    )
    def post(self, request, meeting_id):
        recording = RecordingService.start(request.user, meeting_id)
        return Response(
            RecordingSerializer(recording).data, status=status.HTTP_201_CREATED
        )


@extend_schema(tags=["Reuniões"])
class MeetingRecordingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Delete a recording and its file (organizer or manager)",
        responses={204: None},
    )
    def delete(self, request, meeting_id, recording_id):
        RecordingService.delete(request.user, meeting_id, recording_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Reuniões"])
class MeetingRecordingStopView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Stop a running recording",
        request=None,
        responses={200: RecordingSerializer},
    )
    def post(self, request, meeting_id, recording_id):
        recording = RecordingService.stop(request.user, meeting_id, recording_id)
        return Response(RecordingSerializer(recording).data)


@extend_schema(tags=["Reuniões"])
class MeetingRecordingDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Signed download URL (organizer or manager)",
        responses={200: DownloadSerializer},
    )
    def get(self, request, meeting_id, recording_id):
        url = RecordingService.download(request.user, meeting_id, recording_id)
        return Response({"url": url})


@extend_schema(tags=["Reuniões"])
class LiveKitWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    # its own generous bucket: the provider's few IPs must not share the anonymous limit
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "webhook"

    @extend_schema(
        summary="LiveKit webhook (JWT signed with the API secret)",
        request=None,
        responses={204: None},
    )
    def post(self, request):
        body = request.body  # the signature covers the raw bytes
        livekit.verify_webhook(body, request.headers.get("Authorization", ""))
        try:
            event = json.loads(body)
        except ValueError as error:
            raise ParseError() from error
        LiveKitWebhookService.handle(event)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _insight_data(insight) -> dict:
    return InsightSerializer(
        insight, context={"tasks": InsightService.created_tasks(insight)}
    ).data


@extend_schema(tags=["Reuniões"])
class MeetingInsightView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Transcript and summary of a recording (participants)",
        responses={200: InsightSerializer},
    )
    def get(self, request, meeting_id, recording_id):
        insight = InsightService.get(request.user, meeting_id, recording_id)
        return Response(_insight_data(insight))

    @extend_schema(
        summary="Start or retry transcription and summary (organizer or manager)",
        request=None,
        responses={202: InsightSerializer},
    )
    def post(self, request, meeting_id, recording_id):
        insight = InsightService.process(request.user, meeting_id, recording_id)
        return Response(_insight_data(insight), status=status.HTTP_202_ACCEPTED)


@extend_schema(tags=["Reuniões"])
class MeetingInsightExportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Summary and transcript as Markdown",
        responses={(200, "text/markdown"): str},
    )
    def get(self, request, meeting_id, recording_id):
        text, filename = InsightService.markdown(request.user, meeting_id, recording_id)
        response = HttpResponse(text, content_type="text/markdown; charset=utf-8")
        safe = filename.replace('"', "")
        response["Content-Disposition"] = (
            f'attachment; filename="{safe.encode("ascii", "ignore").decode()}"; '
            f"filename*=UTF-8''{quote(safe)}"
        )
        return response


@extend_schema(tags=["Reuniões"])
class MeetingInsightTasksView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Create reviewed actions as tasks (editor); never twice",
        request=ActionTasksSerializer,
        responses={201: ActionTasksResultSerializer},
    )
    def post(self, request, meeting_id, recording_id):
        body = ActionTasksSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        result = InsightService.create_tasks(
            request.user, meeting_id, recording_id, body.validated_data["items"]
        )
        return Response(result, status=status.HTTP_201_CREATED)
