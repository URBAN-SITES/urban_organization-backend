"""Saved assistant conversations: listed per place (general or a project), reopened
later, and used to rebuild the model's context once the short cache has expired."""

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from core.modules.ai.models.thread import AssistantThread
from core.modules.ai.services.assistant import compact_actions
from core.modules.kanban.services.sector import SectorService

MAX_MESSAGES = 200
HISTORY_TURNS = 6
LIST_LIMIT = 50


class ThreadService:
    @staticmethod
    def list_for(user, sector_id=None):
        rows = AssistantThread.objects.filter(user=user, sector_id=sector_id)
        return [
            {
                "id": row.id,
                "title": row.title,
                "updated_at": row.updated_at,
                "message_count": len(row.messages),
            }
            for row in rows[:LIST_LIMIT]
        ]

    @staticmethod
    def get(user, thread_id) -> AssistantThread:
        thread = AssistantThread.objects.filter(user=user, id=thread_id).first()
        if thread is None:
            raise NotFound()
        if thread.sector_id:
            # access to the project may have been removed since
            SectorService.get_sector(user, thread.sector_id)
        return thread

    @staticmethod
    def delete(user, thread_id) -> None:
        AssistantThread.objects.filter(user=user, id=thread_id).delete()

    @staticmethod
    def history(user, thread_id):
        """The last turns in the shape AssistantService keeps in its cache, or None."""
        thread = AssistantThread.objects.filter(id=thread_id).first()
        if thread is None:
            return None
        if thread.user_id != user.pk:
            # someone else's conversation: refuse before any tool runs
            raise NotFound()
        turns, prompt = [], None
        for message in thread.messages:
            if message.get("role") == "user":
                prompt = message.get("content", "")
            elif prompt is not None:
                turns.append(
                    {
                        "user": prompt,
                        "answer": message.get("content", ""),
                        "actions": message.get("actions", []),
                    }
                )
                prompt = None
        return turns[-HISTORY_TURNS:]

    @staticmethod
    @transaction.atomic
    def record(user, thread_id, sector_id, prompt, result, request_id=None):
        """Appends the exchange; a replayed request id is written only once."""
        thread = (
            AssistantThread.objects.select_for_update().filter(id=thread_id).first()
        )
        if thread is not None and thread.user_id != user.pk:
            raise NotFound()
        if thread is None:
            try:
                with transaction.atomic():
                    thread = AssistantThread.objects.create(
                        id=thread_id,
                        user=user,
                        sector_id=sector_id,
                        title=prompt.strip().replace("\n", " ")[:120] or "Conversa",
                    )
            except IntegrityError:
                raise NotFound() from None
        key = str(request_id) if request_id else None
        if key and any(m.get("request_id") == key for m in thread.messages):
            return thread
        now = timezone.now().isoformat()
        thread.messages = (
            thread.messages
            + [
                {
                    "role": "user",
                    "content": prompt,
                    "created_at": now,
                    "request_id": key,
                },
                {
                    "role": "assistant",
                    "content": result.get("answer", ""),
                    "actions": compact_actions(result.get("actions", [])),
                    "choices": result.get("choices", []),
                    "created_at": now,
                },
            ]
        )[-MAX_MESSAGES:]
        thread.save(update_fields=["messages", "updated_at"])
        return thread
