"""Local AI for meetings: ffmpeg + faster-whisper transcribe, Ollama summarizes.

Nothing leaves the server. Both engines are optional: without MEETING_AI_ENABLED
the pipeline never runs and the UI says it is not configured.
"""

import json
import os
import subprocess
import time
from dataclasses import dataclass
from functools import cache

import requests
from rest_framework import status

from core.modules.meetings.response_messages import MSG_INSIGHTS_NOT_CONFIGURED
from core.modules.meetings.services.livekit import MeetingError

OLLAMA_TIMEOUT = 15 * 60
FFMPEG_TIMEOUT = 30 * 60


class InsightsNotConfigured(MeetingError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = MSG_INSIGHTS_NOT_CONFIGURED
    default_code = "insights_not_configured"


class TransientError(Exception):
    """Worth retrying later: engine down, network hiccup."""


class PermanentError(Exception):
    """Retrying the same input would fail again; the message is shown to users."""


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except ValueError:
        return default


@dataclass(frozen=True)
class AiSettings:
    whisper_model: str
    whisper_device: str
    whisper_compute: str
    whisper_dir: str | None
    language: str
    ollama_url: str
    ollama_model: str
    context_tokens: int
    max_seconds: int
    max_bytes: int


def enabled() -> bool:
    return os.getenv("MEETING_AI_ENABLED", "").lower() in ("1", "true", "yes")


def ai_settings() -> AiSettings:
    if not enabled():
        raise InsightsNotConfigured()
    return AiSettings(
        whisper_model=os.getenv("WHISPER_MODEL", "large-v3-turbo"),
        whisper_device=os.getenv("WHISPER_DEVICE", "cpu"),
        whisper_compute=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
        whisper_dir=os.getenv("WHISPER_MODEL_DIR") or None,
        language=os.getenv("MEETING_AI_LANGUAGE", "pt"),
        ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
        context_tokens=_int("OLLAMA_CONTEXT_TOKENS", 32768),
        max_seconds=_int("MEETING_AI_MAX_SECONDS", 90 * 60),
        max_bytes=_int("MEETING_AI_MAX_BYTES", 2 * 1024**3),
    )


def extract_audio(source: str, target: str) -> None:
    """16 kHz mono WAV, which is what Whisper expects. `source` may be a signed URL."""
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-loglevel",
                "error",
                "-y",
                "-i",
                source,
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "wav",
                target,
            ],
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise PermanentError("ffmpeg is not installed on the worker.") from exc
    except subprocess.TimeoutExpired as exc:
        raise TransientError("audio extraction timed out") from exc
    if result.returncode != 0:
        # 4xx/5xx from the bucket or a broken file; the log tail says which
        detail = (result.stderr or "").strip().splitlines()[-1:] or ["ffmpeg failed"]
        raise TransientError(detail[0][:300])


@cache
def _whisper(name: str, device: str, compute: str, root: str | None):
    from faster_whisper import WhisperModel  # heavy import, worker only

    return WhisperModel(name, device=device, compute_type=compute, download_root=root)


def transcribe(path: str, cfg: AiSettings) -> tuple[list[dict], str, float]:
    """Returns (segments, language, audio seconds)."""
    try:
        model = _whisper(
            cfg.whisper_model, cfg.whisper_device, cfg.whisper_compute, cfg.whisper_dir
        )
    except Exception as exc:  # model download or load
        raise TransientError(f"could not load Whisper model: {exc}") from exc
    pieces, info = model.transcribe(
        path, language=cfg.language or None, vad_filter=True, beam_size=5
    )
    segments = [
        {
            "id": index,
            "start": round(piece.start, 2),
            "end": round(piece.end, 2),
            "text": piece.text.strip(),
        }
        for index, piece in enumerate(pieces)
        if piece.text.strip()
    ]
    return segments, info.language, float(info.duration)


def chat_json(system: str, prompt: str, schema: dict, cfg: AiSettings) -> dict:
    """One Ollama call whose answer is constrained to `schema`."""
    try:
        response = requests.post(
            f"{cfg.ollama_url}/api/chat",
            json={
                "model": cfg.ollama_model,
                "stream": False,
                "format": schema,
                "options": {"temperature": 0.2, "num_ctx": cfg.context_tokens},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=OLLAMA_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise TransientError(f"Ollama unreachable: {exc}") from exc
    if response.status_code == 404:
        raise PermanentError(
            f"Ollama model {cfg.ollama_model} is not installed (ollama pull)."
        )
    if response.status_code >= 400:
        raise TransientError(f"Ollama answered {response.status_code}")
    content = (response.json().get("message") or {}).get("content", "")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise PermanentError("The summary model did not return JSON.") from exc


class Stopwatch:
    def __enter__(self):
        self.start = time.monotonic()
        return self

    def __exit__(self, *_exc):
        self.seconds = round(time.monotonic() - self.start, 1)
