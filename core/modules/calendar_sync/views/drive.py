from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.calendar_sync.serializers.drive import (
    DriveAttachSerializer,
    DriveFileSerializer,
    DriveUploadResultSerializer,
    DriveUploadSerializer,
)
from core.modules.calendar_sync.services.drive import GoogleDriveService
from core.modules.kanban.serializers.task import ResourceLinkSerializer


class DriveFilesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Files this app saved in my Google Drive (folder Inceptum)",
        parameters=[OpenApiParameter("q", str, description="Part of the file name")],
        responses={200: DriveFileSerializer(many=True)},
    )
    def get(self, request):
        files = GoogleDriveService.list_files(
            request.user, request.query_params.get("q", "")
        )
        return Response(DriveFileSerializer(files, many=True).data)


class DriveUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        summary="Send a file to my Google Drive (and optionally attach it to a task)",
        request={"multipart/form-data": DriveUploadSerializer},
        responses={201: DriveUploadResultSerializer},
    )
    def post(self, request):
        serializer = DriveUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        link = None
        if "task" in data:
            uploaded, link = GoogleDriveService.upload_to_task(
                request.user, data["task"], data["file"], data["share_link"]
            )
        else:
            uploaded = GoogleDriveService.upload(
                request.user, data["file"], data["share_link"]
            )
        return Response(
            {
                "file": uploaded,
                "link": ResourceLinkSerializer(link).data if link else None,
            },
            status=status.HTTP_201_CREATED,
        )


class DriveAttachView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Attach a file already in my Drive (saved by this app) to a task as a link",
        request=DriveAttachSerializer,
        responses={201: ResourceLinkSerializer},
    )
    def post(self, request):
        serializer = DriveAttachSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        link = GoogleDriveService.attach_to_task(
            request.user,
            serializer.validated_data["task"],
            serializer.validated_data["file_id"],
        )
        return Response(
            ResourceLinkSerializer(link).data, status=status.HTTP_201_CREATED
        )
