from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models.user import User
from core.modules.calendar_sync.models.calendar import (
    TaskCalendarEvent,
    UserIntegration,
)
from core.modules.calendar_sync.services.google import SCOPE_CALENDAR
from core.modules.kanban.services.sector import SectorService
from core.modules.kanban.services.task import TaskService
from core.modules.organizations.services.organization import OrganizationService

REQUEST = "core.modules.calendar_sync.services.tasks.requests.request"
API = "/api/v1/integrations/google/tasks/"


def reply(status=200, data=None):
    response = MagicMock(status_code=status, ok=status < 400)
    response.json.return_value = data or {}
    return response


class TaskCalendarTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("o@a.com", "x12345678!", name="Owner")
        self.outsider = User.objects.create_user("x@a.com", "x12345678!", name="X")
        org = OrganizationService.create(self.owner, name="Acme")
        sector = SectorService.create(self.owner, org.id, name="Dev")
        self.task = TaskService.create(
            self.owner,
            sector.id,
            {"title": "Ship", "description": "release", "due_date": date(2026, 11, 5)},
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        for user in (self.owner, self.outsider):
            UserIntegration.objects.create(
                user=user,
                provider="google_calendar",
                access_token="AT",
                refresh_token="RT",
                scopes=[SCOPE_CALENDAR],
                expires_at=timezone.now() + timedelta(hours=1),
            )
        self.url = f"{API}{self.task.id}/"

    def test_status_before_sync(self):
        self.assertEqual(
            self.client.get(self.url).json(), {"synced": False, "last_synced_at": None}
        )

    def test_sync_creates_an_all_day_event_and_remembers_it(self):
        with patch(REQUEST, return_value=reply(200, {"id": "ev1"})) as call:
            response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["synced"])
        method, url = call.call_args.args[:2]
        self.assertEqual(method, "POST")
        body = call.call_args.kwargs["json"]
        self.assertEqual(body["summary"], "Ship")
        self.assertEqual(body["start"], {"date": "2026-11-05"})
        self.assertEqual(body["end"], {"date": "2026-11-06"})
        event = TaskCalendarEvent.objects.get(task=self.task, user=self.owner)
        self.assertEqual(event.google_event_id, "ev1")
        self.assertTrue(self.client.get(self.url).json()["synced"])

    def test_second_sync_updates_the_same_event(self):
        with patch(REQUEST, return_value=reply(200, {"id": "ev1"})):
            self.client.post(self.url)
        with patch(REQUEST, return_value=reply(200, {"id": "ev1"})) as call:
            self.client.post(self.url)
        self.assertEqual(call.call_args.args[0], "PUT")
        self.assertTrue(call.call_args.args[1].endswith("/ev1"))
        self.assertEqual(TaskCalendarEvent.objects.count(), 1)

    def test_event_deleted_in_google_is_recreated(self):
        with patch(REQUEST, return_value=reply(200, {"id": "ev1"})):
            self.client.post(self.url)
        answers = [reply(404), reply(200, {"id": "ev2"})]
        with patch(REQUEST, side_effect=answers):
            response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TaskCalendarEvent.objects.get().google_event_id, "ev2")

    def test_task_without_due_date_is_rejected(self):
        self.task.due_date = None
        self.task.save()
        with patch(REQUEST) as call:
            response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        call.assert_not_called()

    def test_unsync_deletes_the_event_and_the_link(self):
        with patch(REQUEST, return_value=reply(200, {"id": "ev1"})):
            self.client.post(self.url)
        with patch(REQUEST, return_value=reply(204)) as call:
            response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(call.call_args.args[0], "DELETE")
        self.assertFalse(TaskCalendarEvent.objects.exists())

    def test_unsync_when_never_synced_is_a_noop(self):
        with patch(REQUEST) as call:
            self.assertEqual(self.client.delete(self.url).status_code, 204)
        call.assert_not_called()

    def test_unsync_tolerates_an_event_already_gone(self):
        with patch(REQUEST, return_value=reply(200, {"id": "ev1"})):
            self.client.post(self.url)
        with patch(REQUEST, return_value=reply(410)):
            self.assertEqual(self.client.delete(self.url).status_code, 204)
        self.assertFalse(TaskCalendarEvent.objects.exists())

    def test_user_without_access_to_the_task_gets_404(self):
        self.client.force_authenticate(self.outsider)
        with patch(REQUEST) as call:
            self.assertEqual(self.client.post(self.url).status_code, 404)
            self.assertEqual(self.client.get(self.url).status_code, 404)
        call.assert_not_called()

    def test_not_connected_asks_to_connect(self):
        UserIntegration.objects.filter(user=self.owner).delete()
        self.assertEqual(self.client.post(self.url).status_code, 400)

    def test_rejected_token_marks_the_connection_revoked(self):
        with patch(REQUEST, return_value=reply(401)):
            self.assertEqual(self.client.post(self.url).status_code, 400)
        self.assertEqual(UserIntegration.objects.get(user=self.owner).status, "revoked")

    def test_google_outage_is_a_502(self):
        with patch(REQUEST, return_value=reply(500)):
            self.assertEqual(self.client.post(self.url).status_code, 502)
        self.assertFalse(TaskCalendarEvent.objects.exists())

    def test_requires_login(self):
        self.assertEqual(APIClient().get(self.url).status_code in (401, 403), True)
