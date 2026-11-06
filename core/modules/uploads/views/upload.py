from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.uploads.models.stored_file import StoredFile
from core.modules.uploads.serializers.upload import (
    FileUploadResponseSerializer,
    FileUploadSerializer,
)
from core.modules.uploads.services.upload import UploadService


@extend_schema(tags=["Arquivos"])
class FileUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    @extend_schema(
        summary="Upload a file to Cloudinary",
        request={"multipart/form-data": FileUploadSerializer},
        responses={201: FileUploadResponseSerializer},
    )
    def post(self, request):
        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = UploadService.upload(
            serializer.validated_data["file"], folder=f"users/{request.user.pk}"
        )
        return Response(result, status.HTTP_201_CREATED)


# shown in the page; anything else downloads
INLINE_TYPES = ("image/", "audio/", "video/", "application/pdf")


@extend_schema(tags=["Arquivos"])
class StoredFileView(APIView):
    """Files kept in the database when Cloudinary is off. Like a Cloudinary URL, the
    link itself is the key: anyone with the random id can read it."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(summary="Download a stored upload", responses={200: None})
    def get(self, request, file_id):
        stored = get_object_or_404(StoredFile, pk=file_id)
        response = HttpResponse(bytes(stored.content), content_type=stored.mime_type)
        disposition = (
            "inline" if stored.mime_type.startswith(INLINE_TYPES) else "attachment"
        )
        name = stored.file_name.replace('"', "")
        response["Content-Disposition"] = f'{disposition}; filename="{name}"'
        response["Content-Security-Policy"] = "sandbox"  # never runs as a page
        response["Cache-Control"] = "private, max-age=31536000, immutable"
        return response
