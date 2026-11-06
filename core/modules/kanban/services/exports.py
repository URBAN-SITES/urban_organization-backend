"""Files to take the data out: tasks as an Excel sheet and the report as PDF."""

import zipfile
from functools import cache
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.models.user import User
from core.modules.kanban.models.task import Task
from core.modules.kanban.services.reports import ReportService
from core.modules.kanban.services.sector import SectorService

PRIORITY = {"low": "Baixa", "medium": "Média", "high": "Alta", "urgent": "Urgente"}
HEADER = (
    "Código",
    "Título",
    "Status",
    "Prioridade",
    "Responsável",
    "Início",
    "Prazo",
    "Concluída em",
    "Estimativa",
    "Ciclo",
    "Épico",
    "Etiquetas",
    "Criada em",
)


@cache
def _register_fonts():
    # fonts bundled with ReportLab (accents work; no system packages needed)
    font_dir = Path(reportlab.__file__).parent / "fonts"
    pdfmetrics.registerFont(TTFont("Export", str(font_dir / "Vera.ttf")))
    pdfmetrics.registerFont(TTFont("ExportBold", str(font_dir / "VeraBd.ttf")))


def _column(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        name = chr(65 + rest) + name
    return name


def _cell(ref: str, value, style: int = 0) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
    text = escape(str(value)[:32000])
    return (
        f'<c r="{ref}" t="inlineStr" s="{style}"><is><t xml:space="preserve">{text}'
        "</t></is></c>"
    )


def build_xlsx(header, rows) -> bytes:
    """A minimal, valid .xlsx (one sheet, bold header) with the standard library."""
    lines = []
    for r, values in enumerate([header, *rows], start=1):
        style = 1 if r == 1 else 0
        cells = "".join(
            _cell(f"{_column(c)}{r}", value, style) for c, value in enumerate(values)
        )
        lines.append(f'<row r="{r}">{cells}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
        'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        f"<sheetData>{''.join(lines)}</sheetData></worksheet>"
    )
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Tarefas" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>"
        ),
        "xl/styles.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
            "</styleSheet>"
        ),
        "xl/worksheets/sheet1.xml": sheet,
    }
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def _date(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "astimezone"):
        value = timezone.localtime(value).date()
    return value.strftime("%d/%m/%Y")


class ExportService:
    @staticmethod
    def tasks_xlsx(user: User, sector_id) -> tuple[str, bytes]:
        sector, _role = SectorService.get_sector(user, sector_id)
        tasks = (
            Task.objects.filter(sector=sector, is_active=True)
            .select_related("status", "assignee", "cycle", "epic")
            .prefetch_related("labels")
            .order_by("sequence", "created_at")
        )
        prefix = sector.identifier or "PRJ"
        rows = [
            (
                f"{prefix}-{task.sequence}" if task.sequence else "",
                task.title,
                task.status.name if task.status_id else "",
                PRIORITY.get(task.priority, task.priority),
                task.assignee.name if task.assignee_id else "",
                _date(task.start_date),
                _date(task.due_date),
                _date(task.completed_at),
                task.estimate,
                task.cycle.name if task.cycle_id else "",
                task.epic.name if task.epic_id else "",
                ", ".join(label.name for label in task.labels.all()),
                _date(task.created_at),
            )
            for task in tasks
        ]
        return f"{prefix.lower()}-tarefas.xlsx", build_xlsx(HEADER, rows)

    @staticmethod
    def report_pdf(user: User, organization_id, days: int, org_name: str) -> bytes:
        data = ReportService.summary(user, organization_id, days)
        _register_fonts()
        output = BytesIO()
        doc = SimpleDocTemplate(
            output,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            title=f"Relatório de entregas · {org_name}",
        )
        title = ParagraphStyle("t", fontName="ExportBold", fontSize=18, leading=22)
        sub = ParagraphStyle(
            "s", fontName="Export", fontSize=10, leading=14, textColor=colors.grey
        )
        h2 = ParagraphStyle(
            "h", fontName="ExportBold", fontSize=12, leading=16, spaceBefore=14
        )
        body = ParagraphStyle("b", fontName="Export", fontSize=10, leading=14)

        def pct(value):
            return "—" if value is None else f"{value}%"

        def table(rows, widths):
            grid = Table(rows, colWidths=widths, hAlign="LEFT")
            grid.setStyle(
                TableStyle(
                    [
                        ("FONT", (0, 0), (-1, -1), "Export", 9),
                        ("FONT", (0, 0), (-1, 0), "ExportBold", 9),
                        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
                        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey),
                        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            return grid

        story = [
            Paragraph(escape(f"Relatório de entregas · {org_name}"), title),
            Paragraph(
                f"Últimos {days} dias, gerado em "
                f"{timezone.localtime().strftime('%d/%m/%Y %H:%M')}",
                sub,
            ),
            Spacer(1, 10),
            table(
                [
                    ["Indicador", "Período", "Período anterior"],
                    [
                        "Tarefas concluídas",
                        data["completed"],
                        data["completed_previous"],
                    ],
                    [
                        "Dias até concluir (média)",
                        data["avg_days_to_complete"] or "—",
                        data["avg_days_previous"] or "—",
                    ],
                    [
                        "Entregues no prazo",
                        pct(data["on_time_pct"]),
                        pct(data["on_time_pct_previous"]),
                    ],
                    ["Abertas agora", data["open"], ""],
                    ["Atrasadas agora", data["overdue"], ""],
                ],
                [8 * cm, 4 * cm, 4 * cm],
            ),
        ]
        if data["people"]:
            story += [
                Paragraph("Pessoas", h2),
                table(
                    [["Pessoa", "Concluídas", "No prazo", "Abertas", "Atrasadas"]]
                    + [
                        [
                            Paragraph(escape(row["name"] or "—"), body),
                            row["completed"],
                            pct(row["on_time_pct"]),
                            row["open"],
                            row["overdue"],
                        ]
                        for row in data["people"]
                    ],
                    [6 * cm, 2.6 * cm, 2.6 * cm, 2.4 * cm, 2.4 * cm],
                ),
            ]
        if data["overdue_by_sector"]:
            story += [
                Paragraph("Atrasadas por projeto", h2),
                table(
                    [["Projeto", "Atrasadas"]]
                    + [
                        [Paragraph(escape(row["sector"]), body), row["overdue"]]
                        for row in data["overdue_by_sector"]
                    ],
                    [12 * cm, 4 * cm],
                ),
            ]
        doc.build(story)
        return output.getvalue()
