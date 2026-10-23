import logging
from functools import cache
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
from rest_framework import exceptions

from core.modules.ai.response_messages import (
    MSG_AI_ANALYSIS_FAILED,
    MSG_AI_REPORT_COUNT,
    MSG_AI_REPORT_EMPTY,
    MSG_AI_REPORT_FAILED,
    MSG_AI_REPORT_GENERATED,
    MSG_AI_REPORT_INFERENCES,
    MSG_AI_REPORT_LIMITATIONS,
    MSG_AI_REPORT_OBSERVATIONS,
    MSG_AI_REPORT_REVIEW,
    MSG_AI_REPORT_SUMMARY,
    MSG_AI_REPORT_TITLE,
    MSG_AI_REPORT_TYPE,
)
from core.modules.ai.services.gemini import GeminiClient

logger = logging.getLogger(__name__)


@cache
def _register_fonts():
    # ReportLab bundles these fonts; deployment needs no system font packages.
    font_dir = Path(reportlab.__file__).parent / "fonts"
    pdfmetrics.registerFont(TTFont("AIReport", str(font_dir / "Vera.ttf")))
    pdfmetrics.registerFont(TTFont("AIReportBold", str(font_dir / "VeraBd.ttf")))


class AIAnalysisService:
    @classmethod
    def analyze(cls, files):
        results = []
        for index, file in enumerate(files, start=1):
            try:
                analysis = GeminiClient.analyze(file)
            except exceptions.APIException as error:
                error.detail = {
                    "detail": MSG_AI_ANALYSIS_FAILED,
                    "index": index,
                    "file": file["name"],
                    "reason": error.detail,
                }
                raise
            results.append({"name": file["name"], "analysis": analysis})
        try:
            return cls._generate_pdf(results)
        except Exception as error:
            logger.warning("AI report generation failed (%s)", type(error).__name__)
            raise exceptions.APIException(MSG_AI_REPORT_FAILED) from error

    @staticmethod
    def _generate_pdf(results):
        _register_fonts()
        output = BytesIO()
        styles = getSampleStyleSheet()
        for name in ("Normal", "Title", "Heading1", "Heading2"):
            styles[name].fontName = "AIReport" if name == "Normal" else "AIReportBold"
        styles["Normal"].leading = 15
        styles["Normal"].spaceAfter = 8
        note_style = ParagraphStyle(
            "AnalysisNote",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#555555"),
        )

        def paragraph(value, style="Normal"):
            text = "".join(char for char in str(value) if char >= " " or char == "\n")
            return Paragraph(escape(text).replace("\n", "<br/>"), styles[style])

        generated_at = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S %Z")
        story = [
            paragraph(MSG_AI_REPORT_TITLE, "Title"),
            paragraph(f"{MSG_AI_REPORT_GENERATED}: {generated_at}"),
            paragraph(f"{MSG_AI_REPORT_COUNT}: {len(results)}"),
            Paragraph(escape(str(MSG_AI_REPORT_REVIEW)), note_style),
            Spacer(1, 0.5 * cm),
        ]
        for index, result in enumerate(results, start=1):
            if index > 1:
                story.append(PageBreak())
            analysis = result["analysis"]
            story.extend(
                [
                    paragraph(f"{index}. {result['name']}", "Heading1"),
                    paragraph(f"{MSG_AI_REPORT_TYPE}: {analysis['document_type']}"),
                    paragraph(MSG_AI_REPORT_SUMMARY, "Heading2"),
                    paragraph(analysis["summary"]),
                ]
            )
            for key, title in (
                ("observations", MSG_AI_REPORT_OBSERVATIONS),
                ("inferences", MSG_AI_REPORT_INFERENCES),
                ("limitations", MSG_AI_REPORT_LIMITATIONS),
            ):
                story.append(paragraph(title, "Heading2"))
                for item in analysis[key] or [MSG_AI_REPORT_EMPTY]:
                    story.append(paragraph(item))

        def footer(canvas, document):
            canvas.saveState()
            canvas.setFont("AIReport", 9)
            canvas.drawRightString(A4[0] - 2 * cm, cm, str(document.page))
            canvas.restoreState()

        SimpleDocTemplate(
            output,
            pagesize=A4,
            title=str(MSG_AI_REPORT_TITLE),
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        ).build(story, onFirstPage=footer, onLaterPages=footer)
        return output.getvalue()
