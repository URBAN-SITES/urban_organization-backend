"""Recordings bucket (S3 or compatible: R2, MinIO): presigned URLs and deletes.

SigV4 query signing is short enough to keep here instead of adding boto3.
"""

import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

import requests
from rest_framework import status

from core.modules.meetings.response_messages import MSG_RECORDINGS_NOT_CONFIGURED
from core.modules.meetings.services.livekit import MeetingError

SIGNED_URL_TTL = 60 * 60
TIMEOUT = 10


class RecordingsNotConfigured(MeetingError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = MSG_RECORDINGS_NOT_CONFIGURED
    default_code = "recordings_not_configured"


@dataclass(frozen=True)
class BucketSettings:
    bucket: str
    region: str
    endpoint: str  # https://s3.<region>.amazonaws.com or the provider's endpoint
    access_key: str
    secret_key: str
    path_style: bool


def bucket_settings() -> BucketSettings:
    bucket = os.getenv("RECORDINGS_S3_BUCKET", "").strip()
    access = os.getenv("RECORDINGS_S3_ACCESS_KEY", "").strip()
    secret = os.getenv("RECORDINGS_S3_SECRET_KEY", "").strip()
    if not (bucket and access and secret):
        raise RecordingsNotConfigured()
    region = os.getenv("RECORDINGS_S3_REGION", "").strip() or "us-east-1"
    endpoint = os.getenv("RECORDINGS_S3_ENDPOINT", "").strip().rstrip("/")
    return BucketSettings(
        bucket=bucket,
        region=region,
        endpoint=endpoint or f"https://s3.{region}.amazonaws.com",
        access_key=access,
        secret_key=secret,
        path_style=bool(endpoint),
    )


def egress_upload() -> dict:
    """The `s3` block of an Egress file output: LiveKit uploads straight to us."""
    cfg = bucket_settings()
    upload = {
        "access_key": cfg.access_key,
        "secret": cfg.secret_key,
        "region": cfg.region,
        "bucket": cfg.bucket,
        "force_path_style": cfg.path_style,
    }
    if cfg.path_style:
        upload["endpoint"] = cfg.endpoint
    return upload


def _object_url(cfg: BucketSettings, key: str) -> str:
    path = quote(key, safe="/~")
    if cfg.path_style:
        return f"{cfg.endpoint}/{cfg.bucket}/{path}"
    parts = urlsplit(cfg.endpoint)
    return f"{parts.scheme}://{cfg.bucket}.{parts.netloc}/{path}"


def _hmac(key: bytes, text: str) -> bytes:
    return hmac.new(key, text.encode(), hashlib.sha256).digest()


def presign(
    key: str,
    method: str = "GET",
    expires: int = SIGNED_URL_TTL,
    params: dict | None = None,
    now: datetime | None = None,
) -> str:
    cfg = bucket_settings()
    url = urlsplit(_object_url(cfg, key))
    now = now or datetime.now(UTC)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    day = now.strftime("%Y%m%d")
    scope = f"{day}/{cfg.region}/s3/aws4_request"
    query = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{cfg.access_key}/{scope}",
        "X-Amz-Date": stamp,
        "X-Amz-Expires": str(expires),
        "X-Amz-SignedHeaders": "host",
        **(params or {}),
    }
    canonical_query = "&".join(
        f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}"
        for k, v in sorted(query.items())
    )
    canonical = "\n".join(
        [
            method,
            url.path,
            canonical_query,
            f"host:{url.netloc}\n",
            "host",
            "UNSIGNED-PAYLOAD",
        ]
    )
    to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            stamp,
            scope,
            hashlib.sha256(canonical.encode()).hexdigest(),
        ]
    )
    signing_key = _hmac(
        _hmac(_hmac(_hmac(f"AWS4{cfg.secret_key}".encode(), day), cfg.region), "s3"),
        "aws4_request",
    )
    signature = hmac.new(signing_key, to_sign.encode(), hashlib.sha256).hexdigest()
    return f"{url.scheme}://{url.netloc}{url.path}?{canonical_query}&X-Amz-Signature={signature}"


def download_url(key: str, filename: str) -> str:
    disposition = f'attachment; filename="{filename}"'
    return presign(key, params={"response-content-disposition": disposition})


def delete_object(key: str) -> None:
    """Missing objects are fine: S3 answers 204 either way."""
    response = requests.delete(
        presign(key, method="DELETE", expires=60), timeout=TIMEOUT
    )
    if response.status_code not in (200, 204, 404):
        response.raise_for_status()
