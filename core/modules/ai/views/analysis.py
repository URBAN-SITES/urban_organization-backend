from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.modules.ai.serializers.analysis import AIAnalysisSerializer
from core.modules.ai.services.analysis import AIAnalysisService


class AIAnalysisView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    @extend_schema(
        summary="Analyze images or PDFs and download a consolidated report",
        description="Upload one or more files using repeated multipart files fields. "
        "If validation or analysis fails for any file, no partial PDF is returned.",
        request={"multipart/form-data": AIAnalysisSerializer},
        responses={
            (200, "application/pdf"): OpenApiTypes.BINARY,
            400: OpenApiResponse(description="Invalid file or incomplete AI analysis."),
            401: OpenApiResponse(description="Authentication is required."),
            403: OpenApiResponse(
                description="Authentication or CSRF verification failed."
            ),
            429: OpenApiResponse(description="AI quota or request rate exceeded."),
            500: OpenApiResponse(
                description="AI provider or report generation unavailable."
            ),
        },
    )
    def post(self, request):
        serializer = AIAnalysisSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = AIAnalysisService.analyze(serializer.validated_data["files"])
        response = HttpResponse(report, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="analysis-report.pdf"'
        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
