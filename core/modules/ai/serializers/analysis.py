import os
import warnings
from io import BytesIO

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PyPdfError
from rest_framework import serializers

from core.modules.ai.response_messages import (
    MSG_AI_FILE_TOO_LARGE,
    MSG_AI_IMAGE_LIMIT,
    MSG_AI_INVALID_ANALYSIS,
    MSG_AI_INVALID_FILE,
    MSG_AI_PDF_ENCRYPTED,
    MSG_AI_PDF_PAGE_LIMIT,
    MSG_AI_TOO_MANY_FILES,
    MSG_AI_TOTAL_TOO_LARGE,
)


@extend_schema_field(OpenApiTypes.BINARY)
class AIAnalysisUploadField(serializers.FileField):
    """Describe multipart bytes correctly without changing global schema settings."""


class AIAnalysisSerializer(serializers.Serializer):
    files = serializers.ListField(
        child=AIAnalysisUploadField(),
        allow_empty=False,
        help_text="Repeat the files multipart field for each JPEG, PNG, WebP or PDF.",
    )

    def validate_files(self, files):
        max_files = int(os.getenv("AI_ANALYSIS_MAX_FILES", "5"))
        max_bytes = int(os.getenv("AI_ANALYSIS_MAX_FILE_BYTES", str(5 * 1024 * 1024)))
        max_total = int(os.getenv("AI_ANALYSIS_MAX_TOTAL_BYTES", str(15 * 1024 * 1024)))
        if len(files) > max_files:
            raise serializers.ValidationError(MSG_AI_TOO_MANY_FILES)
        if any(file.size > max_bytes for file in files):
            raise serializers.ValidationError(MSG_AI_FILE_TOO_LARGE)
        if sum(file.size for file in files) > max_total:
            raise serializers.ValidationError(MSG_AI_TOTAL_TOO_LARGE)

        prepared = []
        total = 0
        for index, file in enumerate(files, start=1):
            try:
                file.seek(0)
                data = file.read(max_bytes + 1)
            finally:
                file.seek(0)
            total += len(data)
            if len(data) > max_bytes:
                raise serializers.ValidationError(MSG_AI_FILE_TOO_LARGE)
            if total > max_total:
                raise serializers.ValidationError(MSG_AI_TOTAL_TOO_LARGE)
            try:
                mime_type = self._validate_content(data)
            except serializers.ValidationError as error:
                raise serializers.ValidationError(
                    {"index": index, "file": file.name, "detail": error.detail}
                ) from error
            prepared.append({"name": file.name, "data": data, "mime_type": mime_type})
        return prepared

    @staticmethod
    def _validate_content(data):
        if data.startswith(b"%PDF-"):
            try:
                reader = PdfReader(BytesIO(data), strict=True)
                if reader.is_encrypted:
                    raise serializers.ValidationError(MSG_AI_PDF_ENCRYPTED)
                page_limit = int(os.getenv("AI_ANALYSIS_MAX_PDF_PAGES", "30"))
                for index, page in enumerate(reader.pages, start=1):
                    if index > page_limit:
                        raise serializers.ValidationError(MSG_AI_PDF_PAGE_LIMIT)
                    # Validate page structure without assuming that it contains text.
                    if page.mediabox.width <= 0 or page.mediabox.height <= 0:
                        raise serializers.ValidationError(MSG_AI_INVALID_FILE)
                if not reader.pages:
                    raise serializers.ValidationError(MSG_AI_INVALID_FILE)
            except (
                PyPdfError,
                ValueError,
                TypeError,
                KeyError,
                IndexError,
                RecursionError,
            ) as error:
                raise serializers.ValidationError(MSG_AI_INVALID_FILE) from error
            return "application/pdf"

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as image:
                    mime_type = {
                        "JPEG": "image/jpeg",
                        "PNG": "image/png",
                        "WEBP": "image/webp",
                    }.get(image.format)
                    if mime_type is None:
                        raise serializers.ValidationError(MSG_AI_INVALID_FILE)
                    max_pixels = int(
                        os.getenv("AI_ANALYSIS_MAX_IMAGE_PIXELS", "20000000")
                    )
                    if image.width * image.height > max_pixels or getattr(
                        image, "is_animated", False
                    ):
                        raise serializers.ValidationError(MSG_AI_IMAGE_LIMIT)
                    image.verify()
                # verify() alone does not decode every image format.
                with Image.open(BytesIO(data)) as image:
                    image.load()
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
            raise serializers.ValidationError(MSG_AI_IMAGE_LIMIT) from error
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as error:
            raise serializers.ValidationError(MSG_AI_INVALID_FILE) from error
        return mime_type


class AIFileAnalysisSerializer(serializers.Serializer):
    document_type = serializers.CharField(max_length=200)
    summary = serializers.CharField(max_length=6000)
    observations = serializers.ListField(
        child=serializers.CharField(max_length=2000), max_length=80
    )
    inferences = serializers.ListField(
        child=serializers.CharField(max_length=2000), max_length=40
    )
    limitations = serializers.ListField(
        child=serializers.CharField(max_length=2000), max_length=40
    )

    def to_internal_value(self, data):
        # DRF CharField coerces numbers to strings; provider output must be strict.
        if not isinstance(data, dict) or set(data) != set(self.fields):
            raise serializers.ValidationError(MSG_AI_INVALID_ANALYSIS)
        for name in ("document_type", "summary"):
            if not isinstance(data[name], str):
                raise serializers.ValidationError(MSG_AI_INVALID_ANALYSIS)
        for name in ("observations", "inferences", "limitations"):
            if not isinstance(data[name], list) or any(
                not isinstance(item, str) for item in data[name]
            ):
                raise serializers.ValidationError(MSG_AI_INVALID_ANALYSIS)
        return super().to_internal_value(data)

    @classmethod
    def json_schema(cls):
        properties = {}
        for name, field in cls().fields.items():
            if isinstance(field, serializers.ListField):
                properties[name] = {
                    "type": "array",
                    "items": {"type": "string", "maxLength": field.child.max_length},
                    "maxItems": field.max_length,
                }
            else:
                properties[name] = {"type": "string", "maxLength": field.max_length}
        return {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        }
