"""Calendar tools scoped to the caller's Google OAuth grants; no arbitrary URLs."""

import uuid
from urllib.parse import parse_qs, quote, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from django.utils.dateparse import parse_datetime
from rest_framework import serializers
from rest_framework.exceptions import (
    NotFound,
    PermissionDenied,
    Throttled,
    ValidationError,
)

from core.modules.ai.response_messages import (
    MSG_AI_CALENDAR_ACCESS,
    MSG_AI_INVALID_ARGUMENTS,
)
from core.modules.ai.serializers.actions import validate_input
from core.modules.calendar_sync.services.google import (
    SCOPE_CALENDAR,
    TIMEOUT,
    GoogleCalendarService,
    GoogleUnavailable,
)

BASE = "https://www.googleapis.com/calendar/v3"
SCOPE_CALENDARS = "https://www.googleapis.com/auth/calendar.calendars"
SCOPE_LIST = "https://www.googleapis.com/auth/calendar.calendarlist.readonly"


class CalendarSelector(serializers.Serializer):
    calendar_id = serializers.CharField(max_length=1024, default="primary")


class CalendarWrite(serializers.Serializer):
    summary = serializers.CharField(max_length=255)
    description = serializers.CharField(
        max_length=4000, required=False, allow_blank=True
    )
    time_zone = serializers.CharField(max_length=100, default="America/Sao_Paulo")

    def validate_time_zone(self, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError, ValueError:
            raise ValidationError(MSG_AI_INVALID_ARGUMENTS) from None
        return value


class CalendarUpdate(CalendarWrite, CalendarSelector):
    pass


class CalendarList(serializers.Serializer):
    page_token = serializers.CharField(max_length=4096, required=False)


class EventSelector(CalendarSelector):
    event_id = serializers.RegexField(r"^[A-Za-z0-9_-]{1,1024}$")


class EventList(CalendarSelector):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    page_token = serializers.CharField(max_length=4096, required=False)

    def validate(self, data):
        if data["end"] <= data["start"] or (data["end"] - data["start"]).days > 366:
            raise ValidationError(MSG_AI_INVALID_ARGUMENTS)
        return data


class EventWrite(CalendarSelector):
    summary = serializers.CharField(max_length=255)
    description = serializers.CharField(
        max_length=4000, required=False, allow_blank=True
    )
    start = serializers.DateTimeField(
        help_text="ISO 8601 with timezone offset, e.g. 2026-10-24T14:00:00-03:00"
    )
    end = serializers.DateTimeField(
        help_text="ISO 8601 with timezone offset; must be later than start"
    )
    location = serializers.CharField(max_length=500, required=False, allow_blank=True)
    attendees = serializers.ListField(
        child=serializers.EmailField(), max_length=100, required=False
    )
    meet = serializers.BooleanField(default=False)

    def validate(self, data):
        for key in ("start", "end"):
            if key in self.initial_data:
                raw = self.initial_data[key]
                try:
                    parsed = parse_datetime(raw) if isinstance(raw, str) else None
                except ValueError:
                    parsed = None
                if parsed is None or parsed.utcoffset() is None:
                    raise ValidationError(MSG_AI_INVALID_ARGUMENTS)
        if "start" in data and "end" in data and data["end"] <= data["start"]:
            raise ValidationError(MSG_AI_INVALID_ARGUMENTS)
        return data


class EventUpdate(EventWrite, EventSelector):
    pass


def _call(user, method, path, scope, **kwargs):
    token = GoogleCalendarService.access_token(user, scope)
    try:
        response = requests.request(
            method,
            BASE + path,
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
            allow_redirects=False,
            **kwargs,
        )
    except requests.RequestException:
        raise GoogleUnavailable() from None
    if response.status_code in (401, 403):
        raise PermissionDenied(MSG_AI_CALENDAR_ACCESS)
    if response.status_code in (404, 410):
        raise NotFound()
    if response.status_code == 429:
        raise Throttled()
    if response.status_code == 400:
        raise ValidationError(MSG_AI_INVALID_ARGUMENTS)
    if not 200 <= response.status_code < 300:
        raise GoogleUnavailable()
    if response.status_code == 204:
        return {}
    try:
        return response.json()
    except ValueError:
        raise GoogleUnavailable() from None


def _calendar_path(calendar_id):
    return "/calendars/" + quote(calendar_id, safe="")


def _event_path(calendar_id, event_id=None):
    path = _calendar_path(calendar_id) + "/events"
    return path + "/" + quote(event_id, safe="") if event_id else path


def _describe_calendar(value):
    return {
        key: value[key]
        for key in ("id", "summary", "description", "timeZone", "accessRole", "primary")
        if key in value
    }


def _describe_event(value):
    # Deliberately exclude arbitrary provider metadata, attachments and auth details.
    result = {
        key: value[key]
        for key in (
            "id",
            "summary",
            "description",
            "location",
            "start",
            "end",
            "status",
            "htmlLink",
            "hangoutLink",
        )
        if key in value
    }
    if "attendees" in value:
        result["attendees"] = [
            {"email": item.get("email"), "response_status": item.get("responseStatus")}
            for item in value["attendees"][:100]
        ]
    result["meet_status"] = (
        value.get("conferenceData", {})
        .get("createRequest", {})
        .get("status", {})
        .get("statusCode")
    )
    return result


def connect_url(user):
    # Reuse existing signed OAuth state and callback. Consent still happens in the browser.
    url = urlsplit(GoogleCalendarService.authorize_url(user))
    query = parse_qs(url.query)
    query["scope"] = [" ".join((SCOPE_CALENDAR, SCOPE_CALENDARS, SCOPE_LIST))]
    return {"url": urlunsplit(url._replace(query=urlencode(query, doseq=True)))}


def connection_status(user):
    integration = GoogleCalendarService.get_integration(user)
    return {
        "connected": integration is not None,
        "events": bool(
            integration and GoogleCalendarService.has_scope(integration, SCOPE_CALENDAR)
        ),
        "calendars": bool(
            integration
            and GoogleCalendarService.has_scope(integration, SCOPE_CALENDARS)
        ),
        "calendar_list": bool(
            integration and GoogleCalendarService.has_scope(integration, SCOPE_LIST)
        ),
    }


def list_calendars(user, page_token=None):
    params = {"maxResults": 50}
    if page_token:
        params["pageToken"] = page_token
    payload = _call(user, "GET", "/users/me/calendarList", SCOPE_LIST, params=params)
    return {
        "results": [_describe_calendar(v) for v in payload.get("items", [])],
        "next_page_token": payload.get("nextPageToken"),
    }


def create_calendar(user, **data):
    body = {key: value for key, value in data.items() if key != "time_zone"}
    body["timeZone"] = data["time_zone"]
    return _describe_calendar(
        _call(user, "POST", "/calendars", SCOPE_CALENDARS, json=body)
    )


def update_calendar(user, calendar_id="primary", **data):
    if not data:
        raise ValidationError(MSG_AI_INVALID_ARGUMENTS)
    if "time_zone" in data:
        data["timeZone"] = data.pop("time_zone")
    return _describe_calendar(
        _call(user, "PATCH", _calendar_path(calendar_id), SCOPE_CALENDARS, json=data)
    )


def delete_calendar(user, calendar_id="primary"):
    primary = _call(user, "GET", _calendar_path("primary"), SCOPE_CALENDARS)
    if calendar_id in ("primary", primary.get("id")):
        raise ValidationError(MSG_AI_INVALID_ARGUMENTS)
    _call(user, "DELETE", _calendar_path(calendar_id), SCOPE_CALENDARS)


def list_events(user, start, end, calendar_id="primary", page_token=None):
    params = {
        "timeMin": start.isoformat(),
        "timeMax": end.isoformat(),
        "singleEvents": True,
        "orderBy": "startTime",
        "maxResults": 50,
    }
    if page_token:
        params["pageToken"] = page_token
    payload = _call(
        user, "GET", _event_path(calendar_id), SCOPE_CALENDAR, params=params
    )
    return {
        "results": [_describe_event(v) for v in payload.get("items", [])],
        "next_page_token": payload.get("nextPageToken"),
    }


def get_event(user, event_id, calendar_id="primary"):
    return _describe_event(
        _call(user, "GET", _event_path(calendar_id, event_id), SCOPE_CALENDAR)
    )


def _event_body(data):
    body = {
        key: data[key] for key in ("summary", "description", "location") if key in data
    }
    for key in ("start", "end"):
        if key in data:
            body[key] = {"dateTime": data[key].isoformat()}
    if "attendees" in data:
        body["attendees"] = [{"email": email} for email in data["attendees"]]
    if data.get("meet"):
        body["conferenceData"] = {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }
    return body


def create_event(user, calendar_id="primary", **data):
    return _describe_event(
        _call(
            user,
            "POST",
            _event_path(calendar_id),
            SCOPE_CALENDAR,
            params={"conferenceDataVersion": 1, "sendUpdates": "all"},
            json=_event_body(data),
        )
    )


def update_event(user, event_id=None, calendar_id="primary", **data):
    if not event_id or not data:
        raise ValidationError(MSG_AI_INVALID_ARGUMENTS)
    # Check the merged range before sending a partial time change to Google.
    if "start" in data or "end" in data:
        existing = get_event(user, event_id, calendar_id)
        merged = {
            key: data[key].isoformat()
            if key in data
            else existing.get(key, {}).get("dateTime")
            for key in ("start", "end")
        }
        validate_input(EventWrite, merged, partial=True)
    return _describe_event(
        _call(
            user,
            "PATCH",
            _event_path(calendar_id, event_id),
            SCOPE_CALENDAR,
            params={"conferenceDataVersion": 1, "sendUpdates": "all"},
            json=_event_body(data),
        )
    )


def delete_event(user, event_id, calendar_id="primary"):
    _call(
        user,
        "DELETE",
        _event_path(calendar_id, event_id),
        SCOPE_CALENDAR,
        params={"sendUpdates": "all"},
    )


def register_calendar_actions(add):
    add("google_status", connection_status)
    add(
        "google_connect_url",
        connect_url,
        description="Get a Google consent URL. Ask the user to open it if calendar permissions are missing; never claim the account was connected automatically.",
    )
    add("calendar_list", list_calendars, input=CalendarList)
    add(
        "calendar_get",
        lambda u, calendar_id="primary": _describe_calendar(
            _call(u, "GET", _calendar_path(calendar_id), SCOPE_CALENDARS)
        ),
        input=CalendarSelector,
    )
    add("calendar_create", create_calendar, input=CalendarWrite, write=True)
    add(
        "calendar_update",
        update_calendar,
        input=CalendarUpdate,
        partial=True,
        write=True,
    )
    add(
        "calendar_delete",
        delete_calendar,
        input=CalendarSelector,
        write=True,
        description="Delete a secondary Google calendar and all its events. Requires explicit user request; cannot delete the primary calendar.",
    )
    add("event_list", list_events, input=EventList)
    add("event_get", get_event, input=EventSelector)
    add(
        "event_create",
        create_event,
        input=EventWrite,
        write=True,
        description="Schedule a Google Calendar event. Set meet=true for a Meet; attendees receive invitations. Return pending if the conference is not ready.",
    )
    add("event_update", update_event, input=EventUpdate, partial=True, write=True)
    add("event_delete", delete_event, input=EventSelector, write=True)
