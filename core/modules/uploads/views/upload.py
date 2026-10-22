from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules.uploads.serializers.upload import (
    FileUploadResponseSerializer,
    FileUploadSerializer,
)
from core.modules.uploads.services.upload import UploadService


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
