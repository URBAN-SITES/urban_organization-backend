import os

from google.auth import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from rest_framework.exceptions import APIException, AuthenticationFailed

from core.models.user import User
from core.response_messages import (
    MSG_GOOGLE_CREDENTIAL_INVALID,
    MSG_GOOGLE_EMAIL_NOT_VERIFIED,
    MSG_GOOGLE_NOT_CONFIGURED,
    MSG_GOOGLE_UNAVAILABLE,
)
from core.services.user import AuthService

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
# Google's clock and ours differ by a few seconds; without tolerance a valid token is
# sometimes rejected as "used too early".
CLOCK_SKEW_SECONDS = 10


class GoogleUnavailable(APIException):
    status_code = 503
    default_detail = MSG_GOOGLE_UNAVAILABLE
    default_code = "google_unavailable"


class GoogleAuthService:
    @staticmethod
    def login(credential: str, user_agent_string: str, ip_address: str) -> dict:
        """`credential` is the ID token the frontend gets from Google Identity Services."""
        try:
            # the audience must always be our client id: None would skip that check
            payload = id_token.verify_oauth2_token(
                credential,
                google_requests.Request(),
                GOOGLE_CLIENT_ID,
                clock_skew_in_seconds=CLOCK_SKEW_SECONDS,
            )
        except google_exceptions.TransportError:
            # could not reach Google to fetch its signing keys
            raise GoogleUnavailable()
        except ValueError:
            if not GOOGLE_CLIENT_ID:
                raise GoogleUnavailable(MSG_GOOGLE_NOT_CONFIGURED)
            raise AuthenticationFailed(MSG_GOOGLE_CREDENTIAL_INVALID)
        if not payload.get("email_verified"):
            raise AuthenticationFailed(MSG_GOOGLE_EMAIL_NOT_VERIFIED)
        if not payload.get("email"):
            raise AuthenticationFailed(MSG_GOOGLE_CREDENTIAL_INVALID)

        email = payload["email"].strip().lower()
        user = User.objects.find_by_email(email)
        created = user is None
        if created:
            user, created = User.objects.get_or_create(
                email=email, defaults={"name": payload.get("name", "")}
            )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        elif not user.is_active:
            # never logged in = unfinished e-mail registration, Google proves the e-mail
            if user.last_login is not None:
                raise AuthenticationFailed()
            user.is_active = True
            user.name = user.name or payload.get("name", "")
            user.save(update_fields=["is_active", "name", "updated_at"])

        return AuthService.create_session(user, user_agent_string, ip_address)
