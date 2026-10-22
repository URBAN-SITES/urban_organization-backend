import os

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from rest_framework.exceptions import AuthenticationFailed

from core.models.user import User
from core.response_messages import (
    MSG_GOOGLE_CREDENTIAL_INVALID,
    MSG_GOOGLE_EMAIL_NOT_VERIFIED,
)
from core.services.user import AuthService

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")


class GoogleAuthService:
    @staticmethod
    def login(credential: str, user_agent_string: str, ip_address: str) -> dict:
        """`credential` is the ID token the frontend gets from Google Identity Services."""
        try:
            payload = id_token.verify_oauth2_token(
                credential, google_requests.Request(), GOOGLE_CLIENT_ID
            )
        except ValueError:
            raise AuthenticationFailed(MSG_GOOGLE_CREDENTIAL_INVALID)
        if not payload.get("email_verified"):
            raise AuthenticationFailed(MSG_GOOGLE_EMAIL_NOT_VERIFIED)

        user, created = User.objects.get_or_create(
            email=User.objects.normalize_email(payload["email"]),
            defaults={"name": payload.get("name", "")},
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
