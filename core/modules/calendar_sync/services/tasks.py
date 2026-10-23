from datetime import timedelta

import requests
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core.models.user import User
from core.modules.calendar_sync.models.calendar import TaskCalendarEvent
from core.modules.calendar_sync.response_messages import (
    MSG_CALENDAR_NO_DUE_DATE,
    MSG_GOOGLE_NOT_CONNECTED,
)
from core.modules.calendar_sync.services.google import (
    EVENTS_URL,
    SCOPE_CALENDAR,
    TIMEOUT,
    GoogleCalendarService,
    GoogleUnavailable,
)
from core.modules.kanban.services.task import TaskService

GONE = (404, 410)  # event deleted on Google's side


class TaskCalendarService:
    """One-way sync: a task's due date becomes an all-day event in the user's own calendar."""

    @staticmethod
    def get(user: User, task_id) -> TaskCalendarEvent | None:
        TaskService.get_task(user, task_id)
        return TaskCalendarEvent.objects.filter(task_id=task_id, user=user).first()

    @staticmethod
    def sync(user: User, task_id) -> TaskCalendarEvent:
        """Creates the event, or updates it when the task is already synced."""
        task, _sector, _role = TaskService.get_task(user, task_id)
        if task.due_date is None:
            raise ValidationError(MSG_CALENDAR_NO_DUE_DATE)
        body = {
            "summary": task.title,
            "description": task.description,
            "start": {"date": task.due_date.isoformat()},
            "end": {"date": (task.due_date + timedelta(days=1)).isoformat()},
        }
        existing = TaskCalendarEvent.objects.filter(task=task, user=user).first()
        event_id = None
        if existing:
            response = TaskCalendarService._call(
                user, "PUT", f"{EVENTS_URL}/{existing.google_event_id}", json=body
            )
            if response.status_code not in GONE:
                event_id = existing.google_event_id
        if event_id is None:  # first sync, or the event was deleted in Google
            event_id = TaskCalendarService._call(
                user, "POST", EVENTS_URL, json=body
            ).json()["id"]
        integration = GoogleCalendarService.get_integration(user)
        event, _created = TaskCalendarEvent.objects.update_or_create(
            task=task,
            user=user,
            defaults={
                "google_event_id": event_id,
                "calendar_id": integration.calendar_id if integration else "primary",
                "last_synced_at": timezone.now(),
                "last_error": "",
            },
        )
        return event

    @staticmethod
    def unsync(user: User, task_id) -> None:
        """Removes the Google event (if any) and forgets the link."""
        event = TaskCalendarService.get(user, task_id)
        if event is None:
            return
        TaskCalendarService._call(
            user, "DELETE", f"{EVENTS_URL}/{event.google_event_id}"
        )
        event.delete()

    @staticmethod
    def _call(user: User, method: str, url: str, **kwargs):
        token = GoogleCalendarService.access_token(user, SCOPE_CALENDAR)
        try:
            response = requests.request(
                method,
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=TIMEOUT,
                **kwargs,
            )
        except requests.RequestException:
            raise GoogleUnavailable()
        if response.status_code in (401, 403):
            GoogleCalendarService.mark_revoked(user)
            raise ValidationError(MSG_GOOGLE_NOT_CONNECTED)
        if not response.ok and response.status_code not in GONE:
            raise GoogleUnavailable()
        return response
