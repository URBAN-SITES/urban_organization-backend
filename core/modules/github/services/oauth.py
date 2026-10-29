"""GitHub App OAuth: logging in (identity only) is kept apart from connecting (tokens)."""

import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.core import signing
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, ValidationError

from core.models.user import User
from core.modules.github.models.github import GitHubConnection, GitHubIdentity
from core.modules.github.response_messages import (
    MSG_GITHUB_ACCOUNT_INACTIVE,
    MSG_GITHUB_CODE_REJECTED,
    MSG_GITHUB_IDENTITY_TAKEN,
    MSG_GITHUB_LOGIN_REQUIRED,
    MSG_GITHUB_NO_EMAIL,
    MSG_GITHUB_STATE_INVALID,
    MSG_GITHUB_UNLINK_NEEDS_PASSWORD,
)
from core.modules.github.services.client import (
    TIMEOUT,
    WEB_URL,
    GitHubForbidden,
    GitHubNotConnected,
    GitHubUnavailable,
    app_settings,
    request,
)
from core.services.user import AuthService

STATE_SALT = "github-oauth"
STATE_MAX_AGE = 600  # seconds
REFRESH_MARGIN = timedelta(seconds=60)

LOGIN = "login"  # sign in or sign up; the token is thrown away
LINK = "link"  # attach a GitHub login to the current account; token thrown away
CONNECT = "connect"  # keep the token to read the user's repositories
PURPOSES = (LOGIN, LINK, CONNECT)


class GitHubOAuthService:
    @staticmethod
    def authorize_url(purpose: str, user: User | None = None) -> str:
        if purpose != LOGIN and user is None:
            raise AuthenticationFailed(MSG_GITHUB_LOGIN_REQUIRED)
        config = app_settings()
        state = signing.dumps(
            {
                "purpose": purpose,
                "user": str(user.pk) if user else None,
                "nonce": secrets.token_urlsafe(8),
            },
            salt=STATE_SALT,
        )
        query = {
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "state": state,
            "allow_signup": "true",
        }
        return f"{WEB_URL}/login/oauth/authorize?{urlencode(query)}"

    @staticmethod
    def read_state(state: str, user: User | None) -> str:
        """Purpose of a callback; the state must be ours, fresh and for this user."""
        try:
            data = signing.loads(state, salt=STATE_SALT, max_age=STATE_MAX_AGE)
        except signing.BadSignature:
            raise ValidationError(MSG_GITHUB_STATE_INVALID)
        purpose = data.get("purpose")
        if purpose not in PURPOSES:
            raise ValidationError(MSG_GITHUB_STATE_INVALID)
        if purpose != LOGIN:
            if user is None or not user.is_authenticated:
                raise AuthenticationFailed(MSG_GITHUB_LOGIN_REQUIRED)
            if data.get("user") != str(user.pk):
                raise ValidationError(MSG_GITHUB_STATE_INVALID)
        return purpose

    # flows --------------------------------------------------------------

    @staticmethod
    def login(code: str, user_agent: str, ip_address: str) -> dict:
        """Signs in by GitHub identity, then by verified e-mail; creates the account if needed."""
        token = GitHubOAuthService._exchange(code)
        try:
            profile = GitHubOAuthService._profile(token["access_token"])
            email = GitHubOAuthService._verified_email(token["access_token"], profile)
        finally:
            GitHubOAuthService._revoke_token(token["access_token"])

        identity = (
            GitHubIdentity.objects.select_related("user")
            .filter(github_id=profile["id"])
            .first()
        )
        with transaction.atomic():
            if identity:
                user = identity.user
                if not user.is_active:
                    raise AuthenticationFailed(MSG_GITHUB_ACCOUNT_INACTIVE)
                if identity.login != profile["login"]:
                    identity.login = profile["login"]
                    identity.save(update_fields=["login"])
            else:
                if not email:
                    raise AuthenticationFailed(MSG_GITHUB_NO_EMAIL)
                user = GitHubOAuthService._user_for_email(email, profile)
                if GitHubIdentity.objects.filter(user=user).exists():
                    # the account already logs in with another GitHub user
                    raise AuthenticationFailed(MSG_GITHUB_IDENTITY_TAKEN)
                GitHubIdentity.objects.create(
                    user=user, github_id=profile["id"], login=profile["login"]
                )
        return AuthService.create_session(user, user_agent, ip_address)

    @staticmethod
    def link(user: User, code: str) -> GitHubIdentity:
        token = GitHubOAuthService._exchange(code)
        try:
            profile = GitHubOAuthService._profile(token["access_token"])
        finally:
            GitHubOAuthService._revoke_token(token["access_token"])
        taken = GitHubIdentity.objects.filter(github_id=profile["id"]).exclude(
            user=user
        )
        if taken.exists():
            raise ValidationError(MSG_GITHUB_IDENTITY_TAKEN)
        identity, _created = GitHubIdentity.objects.update_or_create(
            user=user,
            defaults={"github_id": profile["id"], "login": profile["login"]},
        )
        return identity

    @staticmethod
    def connect(user: User, code: str) -> GitHubConnection:
        token = GitHubOAuthService._exchange(code)
        profile = GitHubOAuthService._profile(token["access_token"])
        connection, _created = GitHubConnection.objects.get_or_create(
            user=user,
            defaults={"github_id": profile["id"], "login": profile["login"]},
        )
        GitHubOAuthService._store(connection, token)
        connection.github_id = profile["id"]
        connection.login = profile["login"]
        connection.avatar_url = profile.get("avatar_url") or ""
        connection.save()
        return connection

    @staticmethod
    def unlink(user: User) -> None:
        if not user.has_usable_password():
            # without a password the GitHub login may be the only way into the account
            raise ValidationError(MSG_GITHUB_UNLINK_NEEDS_PASSWORD)
        GitHubIdentity.objects.filter(user=user).delete()

    @staticmethod
    def disconnect(user: User) -> bool:
        """Revokes the authorization on GitHub and deletes the stored tokens."""
        connection = GitHubConnection.objects.filter(user=user).first()
        if connection is None:
            return False
        revoked = GitHubOAuthService._revoke_grant(connection.access_token)
        connection.delete()
        return revoked

    @staticmethod
    def access_token(user: User) -> str:
        """A valid user token, refreshed when it is about to expire."""
        connection = GitHubConnection.objects.filter(user=user).first()
        if connection is None:
            raise GitHubNotConnected()
        if (
            connection.expires_at
            and connection.expires_at - timezone.now() < REFRESH_MARGIN
        ):
            GitHubOAuthService._refresh(connection)
        return connection.access_token

    @staticmethod
    def forget(user: User) -> None:
        """GitHub refused the token for good (revoked in GitHub's settings)."""
        GitHubConnection.objects.filter(user=user).delete()

    # helpers ------------------------------------------------------------

    @staticmethod
    def _oauth_post(data: dict) -> dict:
        config = app_settings()
        try:
            response = requests.post(
                f"{WEB_URL}/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": config.client_id,
                    "client_secret": config.client_secret,
                    **data,
                },
                timeout=TIMEOUT,
            )
        except requests.RequestException:
            raise GitHubUnavailable()
        if response.status_code >= 500:
            raise GitHubUnavailable()
        # GitHub answers 200 with an `error` field when the code or token is bad
        return response.json() if response.ok else {"error": "http_error"}

    @staticmethod
    def _exchange(code: str) -> dict:
        token = GitHubOAuthService._oauth_post(
            {"code": code, "redirect_uri": app_settings().redirect_uri}
        )
        if token.get("error") or not token.get("access_token"):
            raise ValidationError(MSG_GITHUB_CODE_REJECTED)
        return token

    @staticmethod
    def _refresh(connection: GitHubConnection) -> None:
        if not connection.refresh_token:
            connection.delete()
            raise GitHubNotConnected()
        token = GitHubOAuthService._oauth_post(
            {"grant_type": "refresh_token", "refresh_token": connection.refresh_token}
        )
        if token.get("error") or not token.get("access_token"):
            connection.delete()  # the refresh token expired or was revoked
            raise GitHubNotConnected()
        GitHubOAuthService._store(connection, token)
        connection.save()

    @staticmethod
    def _store(connection: GitHubConnection, token: dict) -> None:
        now = timezone.now()
        connection.access_token = token["access_token"]
        # apps without expiring tokens send neither field
        connection.refresh_token = token.get("refresh_token", "")
        expires = token.get("expires_in")
        refresh_expires = token.get("refresh_token_expires_in")
        connection.expires_at = (
            now + timedelta(seconds=int(expires)) if expires else None
        )
        connection.refresh_expires_at = (
            now + timedelta(seconds=int(refresh_expires)) if refresh_expires else None
        )

    @staticmethod
    def _profile(access_token: str) -> dict:
        return request("GET", "/user", token=access_token).json()

    @staticmethod
    def _verified_email(access_token: str, profile: dict) -> str | None:
        """Primary verified e-mail; needs the app's "Email addresses: read" permission."""
        try:
            response = request("GET", "/user/emails", token=access_token)
        except GitHubForbidden:
            return None  # the app was created without the e-mail permission
        if response.ok:
            emails = response.json()
            for entry in sorted(emails, key=lambda e: not e.get("primary")):
                if entry.get("verified") and entry.get("email"):
                    return entry["email"].strip().lower()
        return None

    @staticmethod
    def _user_for_email(email: str, profile: dict) -> User:
        user = User.objects.find_by_email(email)
        if user is None:
            user = User.objects.create(
                email=email, name=profile.get("name") or profile["login"]
            )
            user.set_unusable_password()
            user.save(update_fields=["password"])
            return user
        if not user.is_active:
            # never logged in = unfinished e-mail sign-up; GitHub proved the e-mail
            if user.last_login is not None:
                raise AuthenticationFailed(MSG_GITHUB_ACCOUNT_INACTIVE)
            user.is_active = True
            user.save(update_fields=["is_active", "updated_at"])
        return user

    @staticmethod
    def _revoke_token(access_token: str) -> bool:
        return GitHubOAuthService._revoke("token", access_token)

    @staticmethod
    def _revoke_grant(access_token: str) -> bool:
        return GitHubOAuthService._revoke("grant", access_token)

    @staticmethod
    def _revoke(what: str, access_token: str) -> bool:
        config = app_settings()
        try:
            response = requests.delete(
                f"https://api.github.com/applications/{config.client_id}/{what}",
                auth=(config.client_id, config.client_secret),
                headers={"Accept": "application/vnd.github+json"},
                json={"access_token": access_token},
                timeout=TIMEOUT,
            )
        except requests.RequestException:
            return False
        # 404: the token was already gone
        return response.status_code in (204, 404)
