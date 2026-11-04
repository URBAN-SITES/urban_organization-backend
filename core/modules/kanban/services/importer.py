"""Import tasks from files exported by Trello (JSON), Jira, Asana and Plane (CSV).

Everything happens from the uploaded file: no account, no token and no call to
those services. Columns are matched by name (case-insensitive) and the missing
ones are created; labels too. People are matched by e-mail, only among those who
already see the project. A preview (dry run) shows what would happen first.
"""

import csv
import io
import json
import re
from datetime import date, datetime

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core.models.user import User
from core.modules.kanban.models.activity import TaskActivity
from core.modules.kanban.models.label import Label
from core.modules.kanban.models.sector import Sector
from core.modules.kanban.models.task import ChecklistItem, Status, Task
from core.modules.kanban.response_messages import (
    MSG_IMPORT_EMPTY,
    MSG_IMPORT_FILE_INVALID,
    MSG_IMPORT_TOO_LARGE,
)
from core.modules.kanban.services.activity import ActivityService
from core.modules.kanban.services.sector import Role, SectorService

MAX_BYTES = 5 * 1024 * 1024
MAX_TASKS = 2000
SOURCES = ("trello", "jira", "asana", "plane", "csv")

# header aliases (lowercase) of each field across the supported exports
ALIASES = {
    "title": ("summary", "name", "title", "task name", "nome", "título", "titulo"),
    "description": ("description", "notes", "descrição", "descricao", "desc"),
    "status": ("status", "state", "section/column", "section", "column", "list"),
    "priority": ("priority", "prioridade"),
    "due": ("due date", "due", "due_date", "target date", "target_date", "prazo"),
    "start": ("start date", "start_date", "início", "inicio"),
    "labels": ("labels", "label", "tags", "etiquetas"),
    "assignee": ("assignee email", "assignee", "assignees", "responsável"),
    "done": ("completed at", "completed", "resolved", "resolution date"),
    "estimate": ("story points", "estimate", "story point estimate", "points"),
}
PRIORITY_MAP = {
    "highest": "urgent",
    "urgent": "urgent",
    "urgente": "urgent",
    "critical": "urgent",
    "blocker": "urgent",
    "high": "high",
    "alta": "high",
    "medium": "medium",
    "média": "medium",
    "media": "medium",
    "normal": "medium",
    "low": "low",
    "baixa": "low",
    "lowest": "low",
    "minor": "low",
    "trivial": "low",
}
DONE_WORDS = (
    "done",
    "closed",
    "resolved",
    "complete",
    "concluído",
    "concluido",
    "feito",
)
DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d/%b/%y %I:%M %p",
    "%d/%b/%y",
    "%d/%m/%Y %H:%M",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
)


def _date(value) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _split(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;|]", value or "") if part.strip()]


def _row(**values) -> dict:
    return {
        "title": (values.get("title") or "").strip()[:255],
        "description": (values.get("description") or "").strip(),
        "status": (values.get("status") or "").strip()[:100],
        "priority": PRIORITY_MAP.get(
            str(values.get("priority") or "").strip().lower(), "medium"
        ),
        "due": _date(values.get("due")),
        "start": _date(values.get("start")),
        "labels": [label[:50] for label in values.get("labels") or []][:10],
        "assignee": (values.get("assignee") or "").strip().lower(),
        "done": bool(values.get("done")),
        "estimate": values.get("estimate"),
        "checklist": [item[:255] for item in values.get("checklist") or []][:100],
    }


def parse_trello(raw: bytes) -> list[dict]:
    data = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("cards"), list):
        raise ValueError("not a Trello board")
    lists = {
        item.get("id"): item.get("name", "")
        for item in data.get("lists") or []
        if isinstance(item, dict)
    }
    checklists: dict[str, list[str]] = {}
    for checklist in data.get("checklists") or []:
        if not isinstance(checklist, dict):
            continue
        items = checklists.setdefault(checklist.get("idCard"), [])
        items += [
            str(item.get("name", ""))
            for item in checklist.get("checkItems") or []
            if isinstance(item, dict) and item.get("name")
        ]
    rows = []
    for card in data["cards"]:
        if not isinstance(card, dict) or card.get("closed"):
            continue
        rows.append(
            _row(
                title=card.get("name"),
                description=card.get("desc"),
                status=lists.get(card.get("idList"), ""),
                due=card.get("due"),
                start=card.get("start"),
                labels=[
                    label.get("name") or label.get("color") or ""
                    for label in card.get("labels") or []
                    if isinstance(label, dict)
                ],
                done=card.get("dueComplete"),
                checklist=checklists.get(card.get("id"), []),
            )
        )
    return rows


def parse_csv(raw: bytes) -> list[dict]:
    text = raw.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    header = [cell.strip().lower() for cell in next(reader, [])]

    def columns(field: str) -> list[int]:
        # Jira repeats a header once per value (Labels, Labels, ...)
        return [index for index, name in enumerate(header) if name in ALIASES[field]]

    index = {field: columns(field) for field in ALIASES}
    if not index["title"]:
        raise ValueError("no title column")
    rows = []
    for cells in reader:
        if not any(cell.strip() for cell in cells):
            continue

        def first(field: str) -> str:
            for column in index[field]:
                if column < len(cells) and cells[column].strip():
                    return cells[column]
            return ""

        def every(field: str) -> list[str]:
            values: list[str] = []
            for column in index[field]:
                if column < len(cells):
                    values += _split(cells[column])
            return values

        status = first("status")
        done_cell = first("done")
        estimate = first("estimate").replace(",", ".")
        rows.append(
            _row(
                title=first("title"),
                description=first("description"),
                status=status,
                priority=first("priority"),
                due=first("due"),
                start=first("start"),
                labels=every("labels"),
                assignee=(every("assignee") or [""])[0],
                done=bool(done_cell)
                and done_cell.strip().lower() not in ("false", "no"),
                estimate=int(float(estimate))
                if re.fullmatch(r"\d+(\.\d+)?", estimate)
                else None,
            )
        )
    return rows


class ImportService:
    @staticmethod
    def parse(source: str, upload) -> list[dict]:
        if upload.size > MAX_BYTES:
            raise ValidationError(MSG_IMPORT_TOO_LARGE)
        raw = upload.read()
        try:
            rows = parse_trello(raw) if source == "trello" else parse_csv(raw)
        except ValueError, UnicodeDecodeError, csv.Error, json.JSONDecodeError:
            raise ValidationError(MSG_IMPORT_FILE_INVALID)
        rows = [row for row in rows if row["title"]]
        if not rows:
            raise ValidationError(MSG_IMPORT_EMPTY)
        if len(rows) > MAX_TASKS:
            raise ValidationError(MSG_IMPORT_TOO_LARGE)
        return rows

    @staticmethod
    def run(user: User, sector_id, source: str, upload, dry_run: bool) -> dict:
        sector, _role = SectorService.get_sector(user, sector_id, Role.EDITOR)
        rows = ImportService.parse(source, upload)
        statuses = {status.name.lower(): status for status in sector.statuses.all()}
        new_columns = list(
            {
                row["status"].lower(): row["status"]
                for row in rows
                if row["status"] and row["status"].lower() not in statuses
            }.values()
        )
        labels = {label.name.lower(): label for label in sector.labels.all()}
        new_labels = list(
            {
                name.lower(): name
                for row in rows
                for name in row["labels"]
                if name.lower() not in labels
            }.values()
        )
        people = {
            email.lower(): user_id
            for user_id, email in User.objects.filter(
                id__in=SectorService.participant_ids(sector), is_active=True
            ).values_list("id", "email")
        }
        matched = sum(1 for row in rows if row["assignee"] in people)
        summary = {
            "total": len(rows),
            "new_columns": new_columns[:30],
            "new_labels": new_labels[:30],
            "assigned": matched,
            "sample": [row["title"] for row in rows[:5]],
            "created": 0,
        }
        if dry_run:
            return summary
        summary["created"] = ImportService._create(
            user, sector, source, rows, statuses, labels, people
        )
        return summary

    @staticmethod
    @transaction.atomic
    def _create(user, sector: Sector, source, rows, statuses, labels, people) -> int:
        position = (sector.statuses.aggregate(last=Max("position"))["last"] or 0) + 1
        for name in dict.fromkeys(row["status"] for row in rows if row["status"]):
            if name.lower() in statuses:
                continue
            done = name.lower() in DONE_WORDS
            statuses[name.lower()] = Status.objects.create(
                sector=sector,
                name=name,
                category=Status.Category.DONE if done else Status.Category.TODO,
                position=position,
            )
            position += 1
        default = (
            sector.statuses.filter(category=Status.Category.TODO)
            .order_by("position")
            .first()
            or sector.statuses.order_by("position").first()
        )
        done_column = (
            sector.statuses.filter(category=Status.Category.DONE)
            .order_by("position")
            .first()
        )
        for name in dict.fromkeys(n for row in rows for n in row["labels"]):
            if name.lower() not in labels:
                labels[name.lower()] = Label.objects.create(sector=sector, name=name)

        locked = Sector.objects.select_for_update().get(pk=sector.pk)
        counter = locked.task_counter
        tops: dict = {}
        now = timezone.now()
        created = []
        for row in rows:
            status = statuses.get(row["status"].lower()) if row["status"] else None
            if status is None:
                status = done_column if row["done"] and done_column else default
            if status.pk not in tops:
                last = Task.objects.filter(status=status, is_active=True).aggregate(
                    last=Max("position")
                )["last"]
                tops[status.pk] = -1 if last is None else last
            tops[status.pk] += 1
            counter += 1
            start = row["start"]
            if start and row["due"] and start > row["due"]:
                start = None
            estimate = row["estimate"]
            task = Task.objects.create(
                sector=sector,
                owner=user,
                status=status,
                position=tops[status.pk],
                sequence=counter,
                title=row["title"],
                description=row["description"],
                priority=row["priority"],
                due_date=row["due"],
                start_date=start,
                estimate=estimate if estimate is not None and estimate <= 999 else None,
                assignee_id=people.get(row["assignee"]),
                completed_at=now if status.category == Status.Category.DONE else None,
            )
            names = {name.lower() for name in row["labels"]}
            if names:
                task.labels.set([labels[name] for name in names if name in labels])
            if row["checklist"]:
                ChecklistItem.objects.bulk_create(
                    ChecklistItem(task=task, content=content, position=index)
                    for index, content in enumerate(row["checklist"])
                )
            created.append(task)
        locked.task_counter = counter
        locked.save(update_fields=["task_counter"])
        for task in created:
            ActivityService.record(
                task, user, TaskActivity.Action.CREATED, {"imported": [None, source]}
            )
        return len(created)
