from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from django.test import SimpleTestCase
from rest_framework.exceptions import PermissionDenied, ValidationError

from core.modules.ai.services.actions import get_action
from core.modules.ai.services.calendar import SCOPE_CALENDARS, SCOPE_LIST


@patch(
    "core.modules.ai.services.calendar.GoogleCalendarService.access_token",
    return_value="private-token",
)
@patch("core.modules.ai.services.calendar.requests.request")
class CalendarActionTests(SimpleTestCase):
    def setUp(self):
        self.user = SimpleNamespace(pk="user")

    def execute(self, name, data):
        return get_action(name).execute(self.user, {"data": data})

    def response(self, request, payload=None, status=200):
        request.return_value = Mock(status_code=status)
        request.return_value.json.return_value = payload or {}

    def test_scheduled_meet_creates_event_with_attendees(self, request, token):
        self.response(
            request,
            {
                "id": "event1",
                "hangoutLink": "https://meet.google.com/abc",
                "access_token": "hidden",
            },
        )
        result = self.execute(
            "event_create",
            {
                "summary": "Planning",
                "start": "2026-11-01T10:00:00-03:00",
                "end": "2026-11-01T11:00:00-03:00",
                "meet": True,
                "attendees": ["person@example.com"],
            },
        )
        args = request.call_args.kwargs
        self.assertIn("conferenceData", args["json"])
        self.assertEqual(args["params"]["sendUpdates"], "all")
        self.assertEqual(args["headers"]["Authorization"], "Bearer private-token")
        self.assertNotIn("access_token", result)
        token.assert_called_once()

    def test_invalid_dates_fail_before_calling_google(self, request, token):
        for start, end in [
            ("2026-11-01T10:00:00", "2026-11-01T11:00:00"),
            ("2026-11-01T10:00:00Z", "2026-11-01T09:00:00Z"),
        ]:
            with self.subTest(start=start), self.assertRaises(ValidationError):
                self.execute(
                    "event_create", {"summary": "Invalid", "start": start, "end": end}
                )
        request.assert_not_called()

    def test_calendar_create_update_delete(self, request, token):
        self.response(request, {"id": "secondary@example.com", "summary": "Team"})
        self.execute("calendar_create", {"summary": "Team"})
        self.assertEqual(
            request.call_args.args,
            ("POST", "https://www.googleapis.com/calendar/v3/calendars"),
        )
        token.assert_called_with(self.user, SCOPE_CALENDARS)
        self.execute(
            "calendar_update",
            {"calendar_id": "secondary@example.com", "summary": "New"},
        )
        self.assertEqual(request.call_args.args[0], "PATCH")
        self.response(request, {"id": "primary@example.com"})
        self.execute("calendar_delete", {"calendar_id": "secondary@example.com"})
        self.assertEqual(request.call_args.args[0], "DELETE")

    def test_primary_calendar_cannot_be_deleted(self, request, token):
        self.response(request, {"id": "primary@example.com"})
        for calendar_id in ("primary", "primary@example.com"):
            with self.assertRaises(ValidationError):
                self.execute("calendar_delete", {"calendar_id": calendar_id})
        self.assertTrue(all(call.args[0] == "GET" for call in request.call_args_list))

    def test_provider_permission_denial_is_not_reported_as_success(
        self, request, token
    ):
        self.response(request, status=403)
        with self.assertRaises(PermissionDenied):
            self.execute("event_delete", {"event_id": "event1"})

    def test_calendar_ids_cannot_replace_provider_host(self, request, token):
        self.response(request)
        self.execute("calendar_get", {"calendar_id": "https://evil.example/a?x=1"})
        url = request.call_args.args[1]
        self.assertEqual(urlsplit(url).netloc, "www.googleapis.com")
        self.assertNotIn("?", url)
        self.assertFalse(request.call_args.kwargs["allow_redirects"])

    def test_events_pagination_and_delete(self, request, token):
        self.response(
            request,
            {"items": [{"id": "event1", "summary": "One"}], "nextPageToken": "next"},
        )
        result = self.execute(
            "event_list",
            {"start": "2026-11-01T00:00:00Z", "end": "2026-11-02T00:00:00Z"},
        )
        self.assertEqual(result["next_page_token"], "next")
        self.response(request, status=204)
        result = self.execute("event_delete", {"event_id": "event1"})
        self.assertTrue(result["completed"])

    def test_event_update_validates_merged_time_range(self, request, token):
        self.response(
            request,
            {
                "id": "event1",
                "start": {"dateTime": "2026-11-01T10:00:00Z"},
                "end": {"dateTime": "2026-11-01T11:00:00Z"},
            },
        )
        with self.assertRaises(ValidationError):
            self.execute(
                "event_update", {"event_id": "event1", "start": "2026-11-01T12:00:00Z"}
            )
        self.assertEqual(request.call_count, 1)

    @patch(
        "core.modules.ai.services.calendar.GoogleCalendarService.authorize_url",
        return_value="https://accounts.google.com/o/oauth2/v2/auth?state=signed-state&scope=old",
    )
    def test_consent_url_preserves_signed_state(self, authorize, request, token):
        result = get_action("google_connect_url").execute(self.user, {})
        query = parse_qs(urlsplit(result["url"]).query)
        self.assertEqual(query["state"], ["signed-state"])
        self.assertIn(SCOPE_CALENDARS, query["scope"][0])
        self.assertIn(SCOPE_LIST, query["scope"][0])
        request.assert_not_called()
