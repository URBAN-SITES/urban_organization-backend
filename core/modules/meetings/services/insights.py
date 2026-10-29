"""Recording -> transcript -> structured summary -> reviewed tasks.

The pipeline is idempotent per file (`source_key`), keeps the transcript when the
summary fails so a retry only redoes the missing step, and never touches the
recording itself.
"""

import logging
import os
import re
import tempfile
import unicodedata
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from core.models.user import User
from core.modules.kanban.services.sector import SectorService
from core.modules.kanban.services.task import TaskService
from core.modules.meetings.models.insight import MeetingActionTask, MeetingInsight
from core.modules.meetings.models.meeting import MeetingRecording
from core.modules.meetings.response_messages import (
    MSG_INSIGHT_ACTION_INVALID,
    MSG_INSIGHT_ALREADY_DONE,
    MSG_INSIGHT_ALREADY_RUNNING,
    MSG_INSIGHT_NOT_DONE,
    MSG_MEETING_NOT_INVITED,
    MSG_MEETING_ORGANIZER_REQUIRED,
)
from core.modules.meetings.services import ai, storage
from core.modules.meetings.services.meetings import MeetingService, RecordingService

logger = logging.getLogger(__name__)
Status = MeetingInsight.Status
# a worker that died mid-run leaves the row "running"; after this it may be retaken
STALE_AFTER = timedelta(hours=3)
QUOTE_SEGMENTS = 3

# What the model must return. Every item points at transcript segment ids, so the
# server can attach the real quote and timestamp instead of trusting the model.
_REFS = {"type": "array", "items": {"type": "integer"}}
_POINT = {
    "type": "object",
    "properties": {"text": {"type": "string"}, "segment_ids": _REFS},
    "required": ["text", "segment_ids"],
}
SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "executive_summary": {"type": "string"},
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "segment_ids": _REFS},
                "required": ["title", "segment_ids"],
            },
        },
        "decisions": {"type": "array", "items": _POINT},
        "problems": {"type": "array", "items": _POINT},
        "next_steps": {"type": "array", "items": _POINT},
        "open_questions": {"type": "array", "items": _POINT},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "assignee": {"type": ["string", "null"]},
                    "due_date": {"type": ["string", "null"]},
                    "segment_ids": _REFS,
                },
                "required": [
                    "title",
                    "description",
                    "assignee",
                    "due_date",
                    "segment_ids",
                ],
            },
        },
    },
    "required": [
        "executive_summary",
        "topics",
        "decisions",
        "problems",
        "next_steps",
        "open_questions",
        "actions",
    ],
}

SYSTEM_PROMPT = """Você resume reuniões de trabalho em português do Brasil.
Use somente o que está na transcrição. Não invente fatos, nomes, prazos nem decisões.
Cada linha da transcrição começa com [id | mm:ss]. Em todo item, preencha segment_ids
com os ids das linhas que sustentam o item (no máximo 3).
- executive_summary: 3 a 5 frases.
- topics: assuntos na ordem em que aparecem.
- decisions: só o que foi decidido explicitamente.
- problems, next_steps, open_questions: listas curtas; vazias se não houver.
- actions: tarefas que alguém precisa fazer. assignee é o nome da pessoa citada como
  responsável, ou null se ninguém foi citado. due_date é YYYY-MM-DD só se um prazo
  foi dito na reunião (use a data da reunião para "amanhã", "sexta" etc.); senão null.
Responda apenas com o JSON pedido."""


def clock(seconds: float) -> str:
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


class _PointSerializer(serializers.Serializer):
    text = serializers.CharField(allow_blank=False, max_length=2000)
    segment_ids = serializers.ListField(child=serializers.IntegerField(), max_length=20)


class _TopicSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=300)
    segment_ids = serializers.ListField(child=serializers.IntegerField(), max_length=20)


class _ActionSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(allow_blank=True, max_length=4000)
    assignee = serializers.CharField(allow_null=True, allow_blank=True, max_length=200)
    due_date = serializers.CharField(allow_null=True, allow_blank=True, max_length=40)
    segment_ids = serializers.ListField(child=serializers.IntegerField(), max_length=20)


class SummaryOutputSerializer(serializers.Serializer):
    """Second check of the model output, after Ollama's own schema constraint."""

    executive_summary = serializers.CharField(max_length=6000)
    topics = _TopicSerializer(many=True, max_length=50)
    decisions = _PointSerializer(many=True, max_length=50)
    problems = _PointSerializer(many=True, max_length=50)
    next_steps = _PointSerializer(many=True, max_length=50)
    open_questions = _PointSerializer(many=True, max_length=50)
    actions = _ActionSerializer(many=True, max_length=50)


class SummaryBuilder:
    """Turns the validated model output into what is stored and shown."""

    def __init__(self, segments: list[dict], people: list[User], meeting_day: date):
        self.by_id = {segment["id"]: segment for segment in segments}
        self.people = people
        self.meeting_day = meeting_day

    def _refs(self, ids: list[int]) -> list[dict]:
        seen, refs = set(), []
        for segment_id in ids:
            if segment_id in self.by_id and segment_id not in seen:
                seen.add(segment_id)
                refs.append(self.by_id[segment_id])
        return sorted(refs, key=lambda s: s["start"])[:QUOTE_SEGMENTS]

    def _source(self, ids: list[int]) -> dict | None:
        refs = self._refs(ids)
        if not refs:
            return None
        return {
            "segment_ids": [s["id"] for s in refs],
            "start": refs[0]["start"],
            "end": refs[-1]["end"],
            "quote": " ".join(s["text"] for s in refs),
        }

    def _points(self, items: list[dict]) -> list[dict]:
        points = []
        for item in items:
            source = self._source(item["segment_ids"])
            points.append({"text": item["text"].strip(), "source": source})
        return points

    def _assignee(self, name: str | None) -> User | None:
        """Exact full name or unique first name among project members; else nobody."""
        wanted = _normalize(name or "")
        if not wanted:
            return None
        full = [p for p in self.people if _normalize(p.get_full_name()) == wanted]
        if len(full) == 1:
            return full[0]
        first = [
            p
            for p in self.people
            if _normalize(p.get_full_name()).split(" ")[0] == wanted.split(" ")[0]
        ]
        return first[0] if len(first) == 1 else None

    def _due(self, value: str | None) -> date | None:
        try:
            due = date.fromisoformat((value or "").strip())
        except ValueError:
            return None
        # a deadline before the meeting or years away is a hallucination, not a plan
        if due < self.meeting_day or due > self.meeting_day + timedelta(days=730):
            return None
        return due

    def build(self, data: dict) -> dict:
        actions = []
        dropped = 0
        for item in data["actions"]:
            source = self._source(item["segment_ids"])
            if source is None:
                dropped += 1  # an action must come from something said
                continue
            person = self._assignee(item["assignee"])
            due = self._due(item["due_date"])
            actions.append(
                {
                    "title": item["title"].strip(),
                    "description": item["description"].strip(),
                    "assignee_id": str(person.id) if person else None,
                    "assignee_name": person.get_full_name() if person else None,
                    "assignee_mentioned": (item["assignee"] or "").strip() or None,
                    "due_date": due.isoformat() if due else None,
                    "source": source,
                }
            )
        topics = []
        for item in data["topics"]:
            source = self._source(item["segment_ids"])
            topics.append({"title": item["title"].strip(), "source": source})
        return {
            "executive_summary": data["executive_summary"].strip(),
            "topics": topics,
            "decisions": self._points(data["decisions"]),
            "problems": self._points(data["problems"]),
            "next_steps": self._points(data["next_steps"]),
            "open_questions": self._points(data["open_questions"]),
            "actions": actions,
            "dropped_actions": dropped,
        }


def transcript_text(segments: list[dict]) -> str:
    return "\n".join(f"[{s['id']} | {clock(s['start'])}] {s['text']}" for s in segments)


def _people(recording: MeetingRecording) -> list[User]:
    meeting = recording.meeting
    allowed = SectorService.participant_ids(meeting.sector)
    return list(User.objects.filter(id__in=allowed, is_active=True))


def summarize(recording: MeetingRecording, segments: list[dict], cfg) -> dict:
    meeting = recording.meeting
    day = timezone.localtime(meeting.starts_at).date()
    people = _people(recording)
    names = ", ".join(sorted(p.get_full_name() for p in people if p.get_full_name()))
    prompt = (
        f"Reunião: {meeting.title}\nData: {day.isoformat()}\n"
        f"Pessoas do projeto: {names or 'não informado'}\n\n"
        f"Transcrição:\n{transcript_text(segments)}"
    )
    last_error = ""
    for _attempt in range(2):  # one more try when the output breaks the schema
        raw = ai.chat_json(SYSTEM_PROMPT, prompt, SUMMARY_SCHEMA, cfg)
        output = SummaryOutputSerializer(data=raw)
        if output.is_valid():
            return SummaryBuilder(segments, people, day).build(output.validated_data)
        last_error = str(output.errors)[:500]
    raise ai.PermanentError(f"The summary did not match the schema: {last_error}")


class InsightPipeline:
    @staticmethod
    def enqueue(recording: MeetingRecording, force: bool = False) -> MeetingInsight:
        """Creates (or resets) the row and schedules the worker after commit."""
        cfg = ai.ai_settings()
        insight, created = MeetingInsight.objects.get_or_create(
            recording=recording,
            defaults={
                "transcribe_model": cfg.whisper_model,
                "summary_model": cfg.ollama_model,
            },
        )
        if not created and force:
            insight.status = Status.PENDING
            insight.error = ""
            insight.save(update_fields=["status", "error", "updated_at"])
        from core.modules.meetings.tasks import process_meeting_insight

        transaction.on_commit(lambda: process_meeting_insight.delay(str(insight.id)))
        return insight

    @staticmethod
    def on_recording_ready(recording: MeetingRecording) -> None:
        if not ai.enabled():
            return
        InsightPipeline.enqueue(recording)

    @staticmethod
    def _claim(insight_id) -> tuple[MeetingInsight, bool] | None:
        """Locks the row and decides what is left to do. None means nothing."""
        with transaction.atomic():
            insight = (
                MeetingInsight.objects.select_for_update()
                .select_related("recording__meeting__sector")
                .filter(id=insight_id)
                .first()
            )
            if insight is None:
                return None
            recording = insight.recording
            same_file = insight.source_key == recording.file_key
            if insight.status == Status.DONE and same_file:
                return None
            if insight.running and insight.updated_at > timezone.now() - STALE_AFTER:
                return None  # another worker has it
            if recording.status != MeetingRecording.Status.READY:
                return None
            needs_transcript = not (same_file and insight.segments)
            insight.attempts += 1
            insight.error = ""
            insight.status = (
                Status.TRANSCRIBING if needs_transcript else Status.SUMMARIZING
            )
            insight.save()
            return insight, needs_transcript

    @staticmethod
    def _check_limits(recording: MeetingRecording, cfg) -> None:
        if recording.duration_seconds > cfg.max_seconds:
            raise ai.PermanentError(
                f"Recording longer than the limit ({cfg.max_seconds // 60} min)."
            )
        if recording.size_bytes > cfg.max_bytes:
            raise ai.PermanentError(
                f"Recording larger than the limit ({cfg.max_bytes // 1024**2} MB)."
            )

    @staticmethod
    def run(insight_id) -> None:
        claimed = InsightPipeline._claim(insight_id)
        if claimed is None:
            return
        insight, needs_transcript = claimed
        recording = insight.recording
        try:
            cfg = ai.ai_settings()
            if needs_transcript:
                InsightPipeline._check_limits(recording, cfg)
                with tempfile.TemporaryDirectory() as tmp:
                    audio = os.path.join(tmp, "audio.wav")
                    with ai.Stopwatch() as watch:
                        ai.extract_audio(storage.presign(recording.file_key), audio)
                        segments, language, seconds = ai.transcribe(audio, cfg)
                if seconds > cfg.max_seconds:
                    raise ai.PermanentError("Audio longer than the limit.")
                insight.segments = segments
                insight.language = language
                insight.audio_seconds = seconds
                insight.source_key = recording.file_key
                insight.transcribe_model = cfg.whisper_model
                insight.transcribe_seconds = watch.seconds
                insight.status = Status.SUMMARIZING
                insight.save()
            if not insight.segments:
                insight.summary = None
                insight.error = "no_speech"
            else:
                with ai.Stopwatch() as watch:
                    insight.summary = summarize(recording, insight.segments, cfg)
                insight.summary_seconds = watch.seconds
                insight.summary_model = cfg.ollama_model
            insight.status = Status.DONE
            insight.finished_at = timezone.now()
            insight.save()
        except ai.TransientError as exc:
            # back to pending: the task decides whether to retry or give up
            InsightPipeline.mark(insight.id, Status.PENDING, str(exc))
            raise
        except (ai.PermanentError, ai.InsightsNotConfigured) as exc:
            InsightPipeline.mark(insight.id, Status.FAILED, str(exc))
        except Exception as exc:
            logger.exception("meeting insight %s failed", insight.id)
            InsightPipeline.mark(insight.id, Status.FAILED, f"unexpected: {exc}")

    @staticmethod
    def mark(insight_id, status: str, error: str) -> None:
        MeetingInsight.objects.filter(id=insight_id).update(
            status=status, error=error[:2000], updated_at=timezone.now()
        )


class InsightService:
    @staticmethod
    def _recording(user: User, meeting_id, recording_id):
        access = MeetingService.access(user, meeting_id)
        if not access.join:
            raise PermissionDenied(MSG_MEETING_NOT_INVITED)
        recording = RecordingService._recording(access.meeting, recording_id)
        return access, recording

    @staticmethod
    def get(user: User, meeting_id, recording_id) -> MeetingInsight:
        _access, recording = InsightService._recording(user, meeting_id, recording_id)
        insight = MeetingInsight.objects.filter(recording=recording).first()
        if insight is None:
            ai.ai_settings()  # 503 with a clear code when not configured
            raise NotFound()
        return insight

    @staticmethod
    def process(user: User, meeting_id, recording_id) -> MeetingInsight:
        """Manual start or retry; refuses while running or when already done."""
        access, recording = InsightService._recording(user, meeting_id, recording_id)
        if not access.manage:
            raise PermissionDenied(MSG_MEETING_ORGANIZER_REQUIRED)
        if recording.status != MeetingRecording.Status.READY:
            raise ValidationError({"detail": "recording_not_ready"})
        with transaction.atomic():
            insight = (
                MeetingInsight.objects.select_for_update()
                .filter(recording=recording)
                .first()
            )
            if insight and insight.running:
                raise ValidationError({"detail": MSG_INSIGHT_ALREADY_RUNNING})
            if insight and insight.status == Status.DONE:
                raise ValidationError({"detail": MSG_INSIGHT_ALREADY_DONE})
            return InsightPipeline.enqueue(recording, force=True)

    @staticmethod
    def created_tasks(insight: MeetingInsight) -> dict[int, str | None]:
        return {
            row.action_index: str(row.task_id) if row.task_id else None
            for row in insight.action_tasks.all()
        }

    @staticmethod
    def create_tasks(user: User, meeting_id, recording_id, items: list[dict]) -> dict:
        """Creates the reviewed actions as tasks. Already created ones are skipped."""
        access, recording = InsightService._recording(user, meeting_id, recording_id)
        sector_id = access.meeting.sector_id
        created, skipped = [], []
        with transaction.atomic():
            insight = (
                MeetingInsight.objects.select_for_update()
                .filter(recording=recording)
                .first()
            )
            if insight is None or insight.status != Status.DONE or not insight.summary:
                raise ValidationError({"detail": MSG_INSIGHT_NOT_DONE})
            actions = insight.summary.get("actions", [])
            done = InsightService.created_tasks(insight)
            for item in items:
                index = item["index"]
                if index >= len(actions):
                    raise ValidationError({"detail": MSG_INSIGHT_ACTION_INVALID})
                if index in done or index in {c["index"] for c in created}:
                    skipped.append(index)
                    continue
                source = actions[index]["source"]
                origin = (
                    f'\n\nOrigem: reunião "{access.meeting.title}", '
                    f'{clock(source["start"])}: "{source["quote"]}"'
                )
                task = TaskService.create(
                    user,
                    sector_id,
                    {
                        "title": item["title"],
                        "description": (item.get("description") or "") + origin,
                        "assignee": item.get("assignee"),
                        "due_date": item.get("due_date"),
                    },
                )
                try:
                    with transaction.atomic():
                        MeetingActionTask.objects.create(
                            insight=insight,
                            action_index=index,
                            task=task,
                            created_by=user,
                        )
                except IntegrityError:  # pragma: no cover - guarded by the lock
                    raise ValidationError({"detail": MSG_INSIGHT_ACTION_INVALID})
                created.append({"index": index, "task_id": str(task.id)})
        return {"created": created, "skipped": skipped}

    @staticmethod
    def markdown(user: User, meeting_id, recording_id) -> tuple[str, str]:
        insight = InsightService.get(user, meeting_id, recording_id)
        if insight.status != Status.DONE:
            raise ValidationError({"detail": MSG_INSIGHT_NOT_DONE})
        meeting = insight.recording.meeting
        started = timezone.localtime(insight.recording.started_at)
        lines = [f"# {meeting.title}", "", f"Gravação de {started:%d/%m/%Y %H:%M}", ""]
        summary = insight.summary or {}

        def at(source):
            return f" ({clock(source['start'])})" if source else ""

        if summary:
            lines += ["## Resumo", "", summary["executive_summary"], ""]
            sections = [
                ("Tópicos", [(t["title"], t["source"]) for t in summary["topics"]]),
                ("Decisões", [(p["text"], p["source"]) for p in summary["decisions"]]),
                ("Problemas", [(p["text"], p["source"]) for p in summary["problems"]]),
                (
                    "Próximos passos",
                    [(p["text"], p["source"]) for p in summary["next_steps"]],
                ),
                (
                    "Perguntas em aberto",
                    [(p["text"], p["source"]) for p in summary["open_questions"]],
                ),
            ]
            for title, items in sections:
                if items:
                    lines += [f"## {title}", ""]
                    lines += [f"- {text}{at(source)}" for text, source in items]
                    lines.append("")
            if summary["actions"]:
                lines += ["## Ações sugeridas", ""]
                for action in summary["actions"]:
                    who = action["assignee_name"] or "sem responsável identificado"
                    due = action["due_date"] or "sem prazo identificado"
                    lines.append(f"- **{action['title']}** ({who}; {due})")
                    lines.append(
                        f'  > {clock(action["source"]["start"])} "{action["source"]["quote"]}"'
                    )
                lines.append("")
        lines += ["## Transcrição", ""]
        lines += [f"[{clock(s['start'])}] {s['text']}" for s in insight.segments]
        filename = f"{meeting.title[:60]} {started:%Y-%m-%d}.md"
        return "\n".join(lines) + "\n", filename
