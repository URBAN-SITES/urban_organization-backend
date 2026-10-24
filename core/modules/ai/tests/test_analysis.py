import json
import os
from io import BytesIO
from types import SimpleNamespace
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from google.genai import types
from google.genai.errors import APIError
from PIL import Image
from pypdf import PdfReader, PdfWriter
from rest_framework import exceptions
from rest_framework.test import APIClient

from core.modules.ai.serializers.analysis import AIAnalysisSerializer
from core.modules.ai.services.analysis import AIAnalysisService
from core.modules.ai.services.gemini import GeminiClient


def image_upload(name="image.png", image_format="PNG", **kwargs):
    output = BytesIO()
    Image.new("RGB", (16, 16), "white").save(output, format=image_format)
    return SimpleUploadedFile(name, output.getvalue(), **kwargs)


def pdf_upload(pages=1, password=None):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    if password:
        writer.encrypt(password)
    output = BytesIO()
    writer.write(output)
    return SimpleUploadedFile(
        "document.pdf", output.getvalue(), content_type="application/pdf"
    )


def analysis_result(**changes):
    return {
        "document_type": "Documento de organização",
        "summary": "Análise de ações, reunião e informações úteis.",
        "observations": ["A reunião está marcada para terça-feira."],
        "inferences": ["A equipe pode precisar organizar as ações."],
        "limitations": ["Não foi possível identificar o responsável."],
        **changes,
    }


def provider_response(payload=None, finish_reason=types.FinishReason.STOP):
    text = json.dumps(analysis_result() if payload is None else payload)
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(parts=[types.Part.from_text(text=text)]),
                finish_reason=finish_reason,
            )
        ]
    )


class AIAnalysisValidationTests(SimpleTestCase):
    def validate(self, files):
        serializer = AIAnalysisSerializer(data={"files": files})
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data["files"]

    def test_detects_image_content_independently_of_filename_and_claimed_type(self):
        for image_format, mime_type in (
            ("JPEG", "image/jpeg"),
            ("PNG", "image/png"),
            ("WEBP", "image/webp"),
        ):
            with self.subTest(image_format=image_format):
                upload = image_upload(
                    "wrong.pdf", image_format, content_type="application/pdf"
                )
                result = self.validate([upload])[0]
                self.assertEqual(result["mime_type"], mime_type)
                self.assertEqual(upload.tell(), 0)
                self.assertEqual(result["data"], upload.read())

    def test_accepts_pdf_with_no_extractable_text(self):
        result = self.validate([pdf_upload()])[0]
        self.assertEqual(result["mime_type"], "application/pdf")

    def test_rejects_missing_or_empty_file_list(self):
        for data in ({}, {"files": []}):
            with self.subTest(data=data):
                self.assertFalse(AIAnalysisSerializer(data=data).is_valid())

    def test_rejects_disguised_and_corrupt_files(self):
        for data in (
            b"not an image",
            b"%PDF-1.7\ninvalid\n%%EOF",
            b"\x89PNG\r\n\x1a\ninvalid",
            image_upload().read()[:40],
        ):
            with self.subTest(data=data[:20]):
                with self.assertRaises(exceptions.ValidationError):
                    self.validate(
                        [SimpleUploadedFile("fake.png", data, content_type="image/png")]
                    )

    def test_rejects_unsupported_image_format(self):
        with self.assertRaises(exceptions.ValidationError):
            self.validate([image_upload("image.gif", "GIF")])

    def test_rejects_encrypted_pdf(self):
        with self.assertRaisesMessage(exceptions.ValidationError, "Encrypted"):
            self.validate([pdf_upload(password="secret")])

    def test_rejects_pdf_without_pages(self):
        with self.assertRaises(exceptions.ValidationError):
            self.validate([pdf_upload(pages=0)])

    @mock.patch.dict(os.environ, {"AI_ANALYSIS_MAX_PDF_PAGES": "1"})
    def test_rejects_pdf_over_page_limit(self):
        with self.assertRaisesMessage(exceptions.ValidationError, "page limit"):
            self.validate([pdf_upload(pages=2)])

    @mock.patch.dict(os.environ, {"AI_ANALYSIS_MAX_FILES": "1"})
    def test_rejects_too_many_files_before_reading(self):
        uploads = [image_upload(), image_upload()]
        with mock.patch.object(uploads[0].file, "read") as read:
            with self.assertRaises(exceptions.ValidationError):
                self.validate(uploads)
            read.assert_not_called()

    @mock.patch.dict(os.environ, {"AI_ANALYSIS_MAX_FILE_BYTES": "1"})
    def test_rejects_large_file(self):
        with self.assertRaises(exceptions.ValidationError):
            self.validate([image_upload()])

    @mock.patch.dict(os.environ, {"AI_ANALYSIS_MAX_TOTAL_BYTES": "100"})
    def test_rejects_combined_size_limit(self):
        with self.assertRaises(exceptions.ValidationError):
            self.validate([image_upload(), image_upload()])

    @mock.patch.dict(os.environ, {"AI_ANALYSIS_MAX_IMAGE_PIXELS": "100"})
    def test_rejects_excessive_pixel_count(self):
        with self.assertRaisesMessage(exceptions.ValidationError, "pixel limit"):
            self.validate([image_upload()])

    def test_rejects_animated_png(self):
        output = BytesIO()
        Image.new("RGB", (16, 16), "white").save(
            output,
            format="PNG",
            save_all=True,
            append_images=[Image.new("RGB", (16, 16), "black")],
            duration=100,
        )
        with self.assertRaisesMessage(exceptions.ValidationError, "animated"):
            self.validate([SimpleUploadedFile("animation.png", output.getvalue())])


@mock.patch("core.modules.ai.services.gemini._client")
class GeminiAnalysisClientTests(SimpleTestCase):
    def setUp(self):
        self.file = {
            "name": "image.png",
            "data": b"image bytes",
            "mime_type": "image/png",
        }

    @mock.patch.dict(
        os.environ,
        {"AI_ANALYSIS_MODEL": "configured-model", "AI_ANALYSIS_TIMEOUT_MS": "12345"},
    )
    def test_sends_original_bytes_with_independent_structured_prompt(self, client):
        client.return_value.models.generate_content.return_value = provider_response()
        self.assertEqual(GeminiClient.analyze(self.file), analysis_result())
        arguments = client.return_value.models.generate_content.call_args.kwargs
        self.assertEqual(arguments["model"], "configured-model")
        part = arguments["contents"][0]
        self.assertEqual(part.inline_data.data, b"image bytes")
        self.assertEqual(part.inline_data.mime_type, "image/png")
        config = arguments["config"]
        self.assertIn("untrusted data", config.system_instruction)
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertEqual(config.http_options.timeout, 12345)
        self.assertEqual(config.http_options.retry_options.attempts, 1)
        self.assertIsNone(config.tools)

    def test_quota_error_becomes_429(self, client):
        client.return_value.models.generate_content.side_effect = APIError(
            429, {"error": {"message": "Quota exceeded"}}
        )
        with self.assertRaises(exceptions.Throttled):
            GeminiClient.analyze(self.file)

    def test_provider_and_connection_errors_become_api_errors(self, client):
        for error in (
            APIError(503, {"error": {"message": "Unavailable"}}),
            TimeoutError("timeout"),
        ):
            with self.subTest(error=type(error)):
                client.return_value.models.generate_content.side_effect = error
                with self.assertRaises(exceptions.APIException):
                    GeminiClient.analyze(self.file)

    def test_rejects_absent_or_blocked_responses(self, client):
        for response in (
            None,
            types.GenerateContentResponse(),
            provider_response(finish_reason=types.FinishReason.SAFETY),
        ):
            with self.subTest(response=response):
                client.return_value.models.generate_content.return_value = response
                with self.assertRaises(exceptions.ValidationError):
                    GeminiClient.analyze(self.file)

    def test_rejects_truncated_output_even_when_json_is_valid(self, client):
        client.return_value.models.generate_content.return_value = provider_response(
            finish_reason=types.FinishReason.MAX_TOKENS
        )
        with self.assertRaises(exceptions.ValidationError):
            GeminiClient.analyze(self.file)

    def test_rejects_invalid_json(self, client):
        response = provider_response()
        response.candidates[0].content.parts[0].text = "not json"
        client.return_value.models.generate_content.return_value = response
        with self.assertRaises(exceptions.ValidationError):
            GeminiClient.analyze(self.file)

    def test_rejects_empty_output(self, client):
        response = provider_response()
        response.candidates[0].content.parts[0].text = ""
        client.return_value.models.generate_content.return_value = response
        with self.assertRaises(exceptions.ValidationError):
            GeminiClient.analyze(self.file)

    def test_rejects_missing_fields_wrong_types_and_excessive_content(self, client):
        payloads = [
            {},
            [],
            analysis_result(summary=123),
            analysis_result(observations=[123]),
            analysis_result(limitations=None),
            analysis_result(summary="x" * 6001),
            analysis_result(inferences=["x"] * 41),
            analysis_result(extra="unexpected"),
        ]
        for payload in payloads:
            with self.subTest(payload_type=type(payload)):
                client.return_value.models.generate_content.return_value = (
                    provider_response(payload)
                )
                with self.assertRaises(exceptions.ValidationError):
                    GeminiClient.analyze(self.file)

    def test_accepts_empty_categories(self, client):
        result = analysis_result(observations=[], inferences=[], limitations=[])
        client.return_value.models.generate_content.return_value = provider_response(
            result
        )
        self.assertEqual(GeminiClient.analyze(self.file), result)


class AIAnalysisReportTests(SimpleTestCase):
    def test_consolidates_files_and_preserves_portuguese_accents(self):
        results = [
            {"name": name, "analysis": analysis_result()}
            for name in ("reunião.png", "ações.pdf")
        ]
        report = AIAnalysisService._generate_pdf(results)
        reader = PdfReader(BytesIO(report))
        self.assertGreaterEqual(len(reader.pages), 2)
        text = "\n".join(page.extract_text() for page in reader.pages)
        for value in (
            "reunião.png",
            "ações.pdf",
            "Análise de ações",
            "terça-feira",
            "Files analyzed: 2",
            "Observed information",
            "Interpretations and inferences",
            "Observations and limitations",
            "Generated at",
        ):
            self.assertIn(value, text)

    def test_treats_generated_markup_and_filenames_as_literal_text(self):
        report = AIAnalysisService._generate_pdf(
            [
                {
                    "name": '<img src="file:///etc/passwd"/>.png',
                    "analysis": analysis_result(summary="<b>ação</b> & informação"),
                }
            ]
        )
        text = PdfReader(BytesIO(report)).pages[0].extract_text()
        self.assertIn("<b>ação</b> & informação", text)
        self.assertIn("file:///etc/passwd", text)

    def test_long_content_flows_across_pages(self):
        report = AIAnalysisService._generate_pdf(
            [
                {
                    "name": "long.pdf",
                    "analysis": analysis_result(
                        observations=["Observação detalhada. " * 80] * 20
                    ),
                }
            ]
        )
        self.assertGreater(len(PdfReader(BytesIO(report)).pages), 2)

    @mock.patch("core.modules.ai.services.analysis.GeminiClient.analyze")
    def test_stops_on_first_failure_and_never_generates_partial_report(self, analyze):
        analyze.side_effect = [analysis_result(), exceptions.Throttled(detail="Busy")]
        files = [{"name": name} for name in ("first.png", "second.pdf", "third.png")]
        with mock.patch.object(AIAnalysisService, "_generate_pdf") as generate:
            with self.assertRaises(exceptions.Throttled) as raised:
                AIAnalysisService.analyze(files)
        self.assertEqual(analyze.call_count, 2)
        generate.assert_not_called()
        self.assertEqual(raised.exception.detail["file"], "second.pdf")
        self.assertIn("no partial report", str(raised.exception.detail["detail"]))


@override_settings(ALLOWED_HOSTS=["testserver"])
@mock.patch("core.modules.ai.services.gemini._client")
class AIAnalysisEndpointTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(
            user=SimpleNamespace(
                is_authenticated=True, is_subscriber=True, pk="analysis-test-user"
            )
        )
        self.url = "/api/v1/ai/analyze/"

    def test_multipart_upload_returns_consolidated_pdf(self, client):
        client.return_value.models.generate_content.return_value = provider_response()
        response = self.client.post(
            self.url, {"files": [image_upload(), pdf_upload()]}, format="multipart"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(client.return_value.models.generate_content.call_count, 2)
        self.assertEqual(len(PdfReader(BytesIO(response.content)).pages), 2)

    def test_single_file_is_accepted(self, client):
        client.return_value.models.generate_content.return_value = provider_response()
        response = self.client.post(
            self.url, {"files": image_upload()}, format="multipart"
        )
        self.assertEqual(response.status_code, 200)
        client.return_value.models.generate_content.assert_called_once()

    def test_authentication_is_required(self, client):
        response = APIClient().post(
            self.url, {"files": image_upload()}, format="multipart"
        )
        self.assertEqual(response.status_code, 401)
        client.assert_not_called()

    def test_validates_entire_batch_before_calling_gemini(self, client):
        response = self.client.post(
            self.url,
            {"files": [image_upload(), SimpleUploadedFile("bad.pdf", b"bad")]},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        client.assert_not_called()

    def test_partial_provider_failure_returns_identified_error(self, client):
        client.return_value.models.generate_content.side_effect = [
            provider_response(),
            APIError(429, {"error": {"message": "Busy"}}),
        ]
        response = self.client.post(
            self.url, {"files": [image_upload(), pdf_upload()]}, format="multipart"
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["file"], "document.pdf")
        self.assertNotEqual(response["Content-Type"], "application/pdf")

    def test_idempotency_header_does_not_break_pdf_response(self, client):
        client.return_value.models.generate_content.return_value = provider_response()
        response = self.client.post(
            self.url,
            {"files": image_upload()},
            format="multipart",
            HTTP_IDEMPOTENCY_KEY="analysis-report-test",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF-"))

    def test_report_generation_error_is_not_returned_as_pdf(self, client):
        client.return_value.models.generate_content.return_value = provider_response()
        with mock.patch.object(
            AIAnalysisService, "_generate_pdf", side_effect=ValueError("failed")
        ):
            response = self.client.post(
                self.url, {"files": image_upload()}, format="multipart"
            )
        self.assertEqual(response.status_code, 500)
        self.assertIn("detail", response.data)

    def test_rejects_json_requests(self, client):
        response = self.client.post(self.url, {"files": []}, format="json")
        self.assertEqual(response.status_code, 415)
        client.assert_not_called()
