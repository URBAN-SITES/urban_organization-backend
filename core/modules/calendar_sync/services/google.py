import os
import uuid
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.core import signing
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from core.models.user import User
from core.modules.calendar_sync.models.calendar import UserIntegration
from core.modules.calendar_sync.response_messages import (
    MSG_GOOGLE_CODE_REJECTED,
    MSG_GOOGLE_NOT_CONFIGURED,
    MSG_GOOGLE_NOT_CONNECTED,
    MSG_GOOGLE_SCOPE_MISSING,
    MSG_GOOGLE_STATE_INVALID,
    MSG_GOOGLE_UNAVAILABLE,
)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
SCOPE_CALENDAR = "https://www.googleapis.com/auth/calendar.events"
# drive.file is the non-sensitive scope: the app only sees files it created itself
SCOPE_DRIVE = "https://www.googleapis.com/auth/drive.file"
SCOPE = SCOPE_CALENDAR
STATE_MAX_AGE = 600  # seconds
TIMEOUT = 10
Provider = UserIntegration.Provider


class GoogleNotConfigured(APIException):
    status_code = 503
    default_detail = MSG_GOOGLE_NOT_CONFIGURED
    default_code = "google_not_configured"


class GoogleUnavailable(APIException):
    status_code = 502
    default_detail = MSG_GOOGLE_UNAVAILABLE
    default_code = "google_unavailable"


def _settings() -> tuple[str, str, str]:
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    redirect = os.getenv(
        "GOOGLE_OAUTH_REDIRECT_URI",
        f"{os.getenv('FRONTEND_URL', 'http://localhost:5173')}/integrations/google/callback",
    )
    if not (client_id and secret):
        raise GoogleNotConfigured()
    return client_id, secret, redirect


class GoogleCalendarService:
    """Google Calendar access used to create Meet links. Not the Google *login*."""

    @staticmethod
    def authorize_url(user: User, drive: bool = False) -> str:
        client_id, _secret, redirect = _settings()
        scope = " ".join([SCOPE_CALENDAR, SCOPE_DRIVE] if drive else [SCOPE_CALENDAR])
        state = signing.dumps({"user": str(user.pk)}, salt="google-oauth")
        return (
            AUTH_URL
            + "?"
            + urlencode(
                {
                    "client_id": client_id,
                    "redirect_uri": redirect,
                    "response_type": "code",
                    "scope": scope,
                    "include_granted_scopes": "true",  # asking for Drive later keeps Calendar
                    "access_type": "offline",
                    "prompt": "consent",  # forces a refresh_token on every consent
                    "state": state,
                }
            )
        )

    @staticmethod
    def connect(user: User, code: str, state: str) -> UserIntegration:
        try:
            data = signing.loads(state, salt="google-oauth", max_age=STATE_MAX_AGE)
        except signing.BadSignature:
            raise ValidationError(MSG_GOOGLE_STATE_INVALID)
        if data.get("user") != str(user.pk):
            raise ValidationError(MSG_GOOGLE_STATE_INVALID)

        client_id, secret, redirect = _settings()
        token = GoogleCalendarService._token_request(
            {
                "code": code,
                "client_id": client_id,
                "client_secret": secret,
                "redirect_uri": redirect,
                "grant_type": "authorization_code",
            }
        )
        integration, _created = UserIntegration.objects.get_or_create(
            user=user, provider=Provider.GOOGLE_CALENDAR
        )
        integration.access_token = token["access_token"]
        # Google omits the refresh token when it already issued one; keep the old
        integration.refresh_token = (
            token.get("refresh_token") or integration.refresh_token
        )
        integration.expires_at = timezone.now() + timedelta(
            seconds=int(token.get("expires_in", 3600))
        )
        integration.scopes = token.get("scope", SCOPE).split()
        integration.status = UserIntegration.Status.ACTIVE
        integration.save()
        return integration

    @staticmethod
    def has_scope(integration: UserIntegration, scope: str) -> bool:
        # rows saved before scopes were tracked only ever had Calendar access
        if not integration.scopes:
            return scope == SCOPE_CALENDAR
        return scope in integration.scopes

    @staticmethod
    def access_token(user: User, scope: str) -> str:
        """A valid access token for `scope`, refreshed when needed."""
        integration = GoogleCalendarService.get_integration(user)
        if integration is None:
            raise ValidationError(MSG_GOOGLE_NOT_CONNECTED)
        if not GoogleCalendarService.has_scope(integration, scope):
            raise ValidationError(MSG_GOOGLE_SCOPE_MISSING)
        return GoogleCalendarService._fresh_access_token(integration)

    @staticmethod
    def mark_revoked(user: User) -> None:
        UserIntegration.objects.filter(
            user=user, provider=Provider.GOOGLE_CALENDAR
        ).update(status=UserIntegration.Status.REVOKED)

    @staticmethod
    def get_integration(user: User) -> UserIntegration | None:
        return UserIntegration.objects.filter(
            user=user,
            provider=Provider.GOOGLE_CALENDAR,
            status=UserIntegration.Status.ACTIVE,
        ).first()

    @staticmethod
    def disconnect(user: User) -> None:
        UserIntegration.objects.filter(
            user=user, provider=Provider.GOOGLE_CALENDAR
        ).delete()

    @staticmethod
    def create_meet(user: User, title: str) -> str:
        """Creates a one-hour calendar event with a Meet room and returns its link."""
        access = GoogleCalendarService.access_token(user, SCOPE_CALENDAR)
        now = timezone.now()
        try:
            response = requests.post(
                EVENTS_URL,
                params={"conferenceDataVersion": 1},
                headers={"Authorization": f"Bearer {access}"},
                json={
                    "summary": title,
                    "start": {"dateTime": now.isoformat()},
                    "end": {"dateTime": (now + timedelta(hours=1)).isoformat()},
                    "conferenceData": {
                        "createRequest": {
                            "requestId": str(uuid.uuid4()),
                            "conferenceSolutionKey": {"type": "hangoutsMeet"},
                        }
                    },
                },
                timeout=TIMEOUT,
            )
        except requests.RequestException:
            raise GoogleUnavailable()
        if response.status_code in (401, 403):
            GoogleCalendarService.mark_revoked(user)
            raise ValidationError(MSG_GOOGLE_NOT_CONNECTED)
        link = response.json().get("hangoutLink") if response.ok else None
        if not link:
            raise GoogleUnavailable()
        return link

    # helpers ------------------------------------------------------------

    @staticmethod
    def _fresh_access_token(integration: UserIntegration) -> str:
        expiring = integration.expires_at is None or (
            integration.expires_at - timezone.now() < timedelta(seconds=60)
        )
        if not expiring:
            return integration.access_token
        if not integration.refresh_token:
            raise ValidationError(MSG_GOOGLE_NOT_CONNECTED)
        client_id, secret, _redirect = _settings()
        try:
            token = GoogleCalendarService._token_request(
                {
                    "refresh_token": integration.refresh_token,
                    "client_id": client_id,
                    "client_secret": secret,
                    "grant_type": "refresh_token",
                }
            )
        except ValidationError:  # revoked or expired refresh token
            integration.status = UserIntegration.Status.REVOKED
            integration.save(update_fields=["status"])
            raise ValidationError(MSG_GOOGLE_NOT_CONNECTED)
        integration.access_token = token["access_token"]
        integration.expires_at = timezone.now() + timedelta(
            seconds=int(token.get("expires_in", 3600))
        )
        integration.save(update_fields=["access_token", "expires_at"])
        return integration.access_token

    @staticmethod
    def _token_request(payload: dict) -> dict:
        try:
            response = requests.post(TOKEN_URL, data=payload, timeout=TIMEOUT)
        except requests.RequestException:
            raise GoogleUnavailable()
        if response.status_code >= 500:
            raise GoogleUnavailable()
        if not response.ok:
            raise ValidationError(MSG_GOOGLE_CODE_REJECTED)
        return response.json()
