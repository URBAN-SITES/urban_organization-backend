"""HTTP access to GitHub: app JWT, installation tokens, user tokens and error mapping."""

import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import jwt
import requests
from django.core.cache import cache
from rest_framework import status
from rest_framework.exceptions import APIException

from core.modules.github.response_messages import (
    MSG_GITHUB_FORBIDDEN,
    MSG_GITHUB_NOT_CONFIGURED,
    MSG_GITHUB_NOT_CONNECTED,
    MSG_GITHUB_RATE_LIMITED,
    MSG_GITHUB_UNAVAILABLE,
)

API_URL = "https://api.github.com"
WEB_URL = "https://github.com"
TIMEOUT = 10
API_VERSION = "2022-11-28"


class GitHubError(APIException):
    """Body carries a stable `code` so the UI can explain the problem in its own words."""

    def __init__(self, detail=None, code=None, **extra):
        detail = str(detail or self.default_detail)
        super().__init__({"detail": detail, "code": code or self.default_code, **extra})


class GitHubNotConfigured(GitHubError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = MSG_GITHUB_NOT_CONFIGURED
    default_code = "github_not_configured"


class GitHubUnavailable(GitHubError):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = MSG_GITHUB_UNAVAILABLE
    default_code = "github_unavailable"


class GitHubRateLimited(GitHubError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = MSG_GITHUB_RATE_LIMITED
    default_code = "github_rate_limited"


class GitHubNotConnected(GitHubError):
    # 409, not 401: a 401 would make the frontend think *our* session expired
    status_code = status.HTTP_409_CONFLICT
    default_detail = MSG_GITHUB_NOT_CONNECTED
    default_code = "github_not_connected"


class GitHubForbidden(GitHubError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = MSG_GITHUB_FORBIDDEN
    default_code = "github_forbidden"


@dataclass(frozen=True)
class AppSettings:
    app_id: str
    slug: str
    client_id: str
    client_secret: str
    private_key: str
    webhook_secret: str
    redirect_uri: str


def app_settings(require_app: bool = False) -> AppSettings:
    """OAuth needs the client id/secret; installation calls also need the app id and key."""
    frontend = os.getenv("FRONTEND_URL", "http://localhost:5173")
    found = AppSettings(
        app_id=os.getenv("GITHUB_APP_ID", ""),
        slug=os.getenv("GITHUB_APP_SLUG", ""),
        client_id=os.getenv("GITHUB_CLIENT_ID", ""),
        client_secret=os.getenv("GITHUB_CLIENT_SECRET", ""),
        # .env files keep the PEM on one line with literal \n
        private_key=os.getenv("GITHUB_APP_PRIVATE_KEY", "").replace("\\n", "\n"),
        webhook_secret=os.getenv("GITHUB_WEBHOOK_SECRET", ""),
        redirect_uri=os.getenv(
            "GITHUB_OAUTH_REDIRECT_URI", f"{frontend}/integrations/github/callback"
        ),
    )
    if not (found.client_id and found.client_secret):
        raise GitHubNotConfigured()
    if require_app and not (found.app_id and found.private_key):
        raise GitHubNotConfigured()
    return found


def _headers(token: str | None, scheme: str = "Bearer") -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
    }
    if token:
        headers["Authorization"] = f"{scheme} {token}"
    return headers


def raise_for_github(response: requests.Response, *, user_token: bool) -> None:
    """Maps GitHub failures to errors the UI can explain."""
    if response.ok:
        return
    code = response.status_code
    remaining = response.headers.get("x-ratelimit-remaining")
    if code == 429 or (code == 403 and remaining == "0"):
        reset = response.headers.get("x-ratelimit-reset")
        reset_at = (
            datetime.fromtimestamp(int(reset), tz=UTC).isoformat()
            if reset and reset.isdigit()
            else None
        )
        raise GitHubRateLimited(reset_at=reset_at)
    if code == 401:
        if user_token:
            raise GitHubNotConnected()
        raise GitHubUnavailable()  # our app credentials were refused
    if code == 403:
        raise GitHubForbidden()
    if code >= 500:
        raise GitHubUnavailable()


def request(method: str, url: str, *, token: str | None = None, user_token=True, **kw):
    """One API call; `url` may be a path below the API root."""
    if url.startswith("/"):
        url = API_URL + url
    try:
        response = requests.request(
            method, url, headers=_headers(token), timeout=TIMEOUT, **kw
        )
    except requests.RequestException:
        raise GitHubUnavailable()
    raise_for_github(response, user_token=user_token)
    return response


def paginate(path: str, *, token: str, key: str | None = None, limit: int = 1000, **kw):
    """Follows `Link: rel=next` up to `limit` items (GitHub pages hold at most 100)."""
    items: list = []
    url = path
    params = {"per_page": 100, **kw.pop("params", {})}
    while url and len(items) < limit:
        response = request("GET", url, token=token, params=params, **kw)
        if response.status_code == 404:
            break
        page = response.json()
        items.extend(page[key] if key else page)
        url = response.links.get("next", {}).get("url")
        params = None  # the next link already carries them
    return items[:limit]


def app_jwt(config: AppSettings) -> str:
    now = int(time.time())
    # backdated 60 s against clock drift; GitHub accepts at most 10 minutes
    payload = {"iat": now - 60, "exp": now + 540, "iss": config.app_id}
    return jwt.encode(payload, config.private_key, algorithm="RS256")


def installation_token(installation_id: int) -> str:
    """Short-lived token of one installation, cached until a minute before it expires."""
    key = f"github:installation:{installation_id}"
    cached = cache.get(key)
    if cached:
        return cached
    config = app_settings(require_app=True)
    try:
        response = requests.post(
            f"{API_URL}/app/installations/{installation_id}/access_tokens",
            headers=_headers(app_jwt(config)),
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        raise GitHubUnavailable()
    if response.status_code == 404:
        # the app was uninstalled or lost access to this account
        raise GitHubForbidden()
    raise_for_github(response, user_token=False)
    data = response.json()
    expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    ttl = int((expires - datetime.now(UTC)).total_seconds()) - 60
    if ttl > 0:
        cache.set(key, data["token"], ttl)
    return data["token"]
