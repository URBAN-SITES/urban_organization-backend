"""LiveKit access without the SDK: room tokens, Twirp calls and webhook checks.

Tokens are HS256 JWTs signed with the API secret, so they never leave the backend
until a permitted user asks for one. The server API is Twirp over JSON.
"""

import base64
import hashlib
import os
import time
from dataclasses import dataclass

import jwt
import requests
from rest_framework import status
from rest_framework.exceptions import APIException

from core.modules.meetings.response_messages import (
    MSG_LIVEKIT_SIGNATURE_INVALID,
    MSG_LIVEKIT_UNAVAILABLE,
    MSG_MEETINGS_NOT_CONFIGURED,
)

TIMEOUT = 10
ROOM_TOKEN_TTL = 2 * 60 * 60
SERVER_TOKEN_TTL = 60


class MeetingError(APIException):
    """Body carries a stable `code` so the UI can explain the problem in its own words."""

    def __init__(self, detail=None, code=None):
        detail = str(detail or self.default_detail)
        super().__init__({"detail": detail, "code": code or self.default_code})


class MeetingsNotConfigured(MeetingError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = MSG_MEETINGS_NOT_CONFIGURED
    default_code = "meetings_not_configured"


class LiveKitUnavailable(MeetingError):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = MSG_LIVEKIT_UNAVAILABLE
    default_code = "livekit_unavailable"


class InvalidSignature(MeetingError):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = MSG_LIVEKIT_SIGNATURE_INVALID
    default_code = "invalid_signature"


@dataclass(frozen=True)
class LiveKitSettings:
    url: str  # what browsers connect to (ws:// or wss://)
    api_url: str  # what the backend calls (http:// or https://)
    api_key: str
    api_secret: str


def livekit_settings() -> LiveKitSettings:
    url = os.getenv("LIVEKIT_URL", "").strip()
    key = os.getenv("LIVEKIT_API_KEY", "").strip()
    secret = os.getenv("LIVEKIT_API_SECRET", "").strip()
    if not (url and key and secret):
        raise MeetingsNotConfigured()
    api_url = os.getenv("LIVEKIT_API_URL", "").strip() or url.replace(
        "wss://", "https://", 1
    ).replace("ws://", "http://", 1)
    return LiveKitSettings(url, api_url.rstrip("/"), key, secret)


def _sign(cfg: LiveKitSettings, claims: dict, ttl: int) -> str:
    now = int(time.time())
    payload = {"iss": cfg.api_key, "nbf": now - 5, "exp": now + ttl, **claims}
    return jwt.encode(payload, cfg.api_secret, algorithm="HS256")


def room_token(identity: str, name: str, room: str) -> str:
    """Join token for one room. Publishing data lets the UI raise hands later."""
    cfg = livekit_settings()
    return _sign(
        cfg,
        {
            "sub": identity,
            "name": name,
            "video": {
                "room": room,
                "roomJoin": True,
                "canPublish": True,
                "canSubscribe": True,
                "canPublishData": True,
            },
        },
        ROOM_TOKEN_TTL,
    )


def twirp(service: str, method: str, body: dict, grant: dict) -> dict:
    cfg = livekit_settings()
    token = _sign(cfg, {"video": grant}, SERVER_TOKEN_TTL)
    try:
        response = requests.post(
            f"{cfg.api_url}/twirp/livekit.{service}/{method}",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as error:
        raise LiveKitUnavailable() from error
    if response.status_code >= 400:
        try:
            message = response.json().get("msg", "")
        except ValueError:
            message = response.text[:200]
        raise LiveKitUnavailable(
            f"{MSG_LIVEKIT_UNAVAILABLE} ({message})" if message else None
        )
    return response.json()


def verify_webhook(body: bytes, authorization: str) -> None:
    """LiveKit signs a JWT whose `sha256` claim is the base64 SHA-256 of the body."""
    cfg = livekit_settings()
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = jwt.decode(
            token,
            cfg.api_secret,
            algorithms=["HS256"],
            issuer=cfg.api_key,
            leeway=60,
            options={"require": ["iss", "sha256"]},
        )
    except jwt.PyJWTError as error:
        raise InvalidSignature() from error
    digest = base64.b64encode(hashlib.sha256(body).digest()).decode()
    if claims["sha256"] != digest:
        raise InvalidSignature()
