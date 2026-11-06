"""AI for meetings: transcribe a recording and summarize it.

Two engines:
- "gemini" (default when GEMINI_API_KEY is set): Google Gemini does both, so it runs
  on a small server. The free tier may use the content to improve Google products.
- "local": ffmpeg + faster-whisper transcribe and Ollama summarizes; nothing leaves
  the server, but it needs ~12 GB of RAM. Turned on with MEETING_AI_ENABLED.

`MEETING_AI_ENGINE` forces one of them. With neither configured the UI says so.
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


GEMINI_MODEL = "gemini-flash-latest"
GEMINI_TIMEOUT_MS = 10 * 60 * 1000


@dataclass(frozen=True)
class AiSettings:
    engine: str
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


def engine() -> str | None:
    forced = os.getenv("MEETING_AI_ENGINE", "").strip().lower()
    if forced in ("gemini", "local"):
        return forced
    if os.getenv("GEMINI_API_KEY", "").strip():
        return "gemini"
    if os.getenv("MEETING_AI_ENABLED", "").lower() in ("1", "true", "yes"):
        return "local"
    return None


def enabled() -> bool:
    return engine() is not None


def ai_settings() -> AiSettings:
    kind = engine()
    if kind is None:
        raise InsightsNotConfigured()
    if kind == "gemini":
        # the model fields name what produced the transcript and the summary
        model = os.getenv("MEETING_AI_GEMINI_MODEL", GEMINI_MODEL)
        return AiSettings(
            engine=kind,
            whisper_model=model,
            whisper_device="",
            whisper_compute="",
            whisper_dir=None,
            language=os.getenv("MEETING_AI_LANGUAGE", "pt"),
            ollama_url="",
            ollama_model=model,
            context_tokens=0,
            max_seconds=_int("MEETING_AI_MAX_SECONDS", 90 * 60),
            max_bytes=_int("MEETING_AI_MAX_BYTES", 2 * 1024**3),
        )
    return AiSettings(
        engine=kind,
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


TRANSCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "language": {"type": "string"},
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "text": {"type": "string"},
                },
                "required": ["start", "end", "text"],
            },
        },
    },
    "required": ["language", "segments"],
}
TRANSCRIPT_PROMPT = (
    "Transcreva o áudio desta reunião palavra por palavra, no idioma falado. "
    "Divida em trechos curtos (uma frase ou fala), com início e fim em segundos "
    "desde o começo da gravação. Não resuma nem invente falas; trechos sem fala "
    "ficam de fora. `language` é o código ISO 639-1 do idioma."
)


def _gemini():
    from core.modules.ai.services.ask import _client

    return _client()


def _gemini_json(contents, schema: dict, cfg: AiSettings, system: str = "") -> dict:
    from google.genai import types
    from google.genai.errors import APIError

    try:
        response = _gemini().models.generate_content(
            model=cfg.ollama_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system or None,
                temperature=0.2,
                response_mime_type="application/json",
                response_json_schema=schema,
                http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS),
            ),
        )
    except APIError as exc:
        code = getattr(exc, "code", None)
        if code in (429, 500, 502, 503, 504):
            raise TransientError(f"Gemini answered {code}") from exc
        raise PermanentError(f"Gemini refused the request ({code}).") from exc
    except Exception as exc:  # network, timeout
        raise TransientError(f"Gemini unreachable: {type(exc).__name__}") from exc
    try:
        return json.loads(response.text or "")
    except json.JSONDecodeError as exc:
        raise PermanentError("The AI model did not return JSON.") from exc


def _download(url: str, target: str) -> str:
    """Saves the recording to disk and returns its content type."""
    try:
        with requests.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            with open(target, "wb") as out:
                for chunk in response.iter_content(1024 * 1024):
                    out.write(chunk)
            return response.headers.get("Content-Type", "video/mp4").split(";")[0]
    except requests.RequestException as exc:
        raise TransientError(f"could not download the recording: {exc}") from exc


def gemini_transcribe(url: str, folder: str, cfg: AiSettings):
    """Uploads the recording to Gemini and returns (segments, language, seconds)."""
    path = os.path.join(folder, "recording")
    mime = _download(url, path)
    client = _gemini()
    try:
        uploaded = client.files.upload(file=path, config={"mime_type": mime})
        # video is processed asynchronously; wait until it can be used
        deadline = time.monotonic() + 10 * 60
        while uploaded.state and uploaded.state.name == "PROCESSING":
            if time.monotonic() > deadline:
                raise TransientError("Gemini is still processing the file")
            time.sleep(5)
            uploaded = client.files.get(name=uploaded.name)
        if uploaded.state and uploaded.state.name == "FAILED":
            raise PermanentError("Gemini could not read the recording.")
    except TransientError, PermanentError:
        raise
    except Exception as exc:
        raise TransientError(f"Gemini upload failed: {type(exc).__name__}") from exc
    try:
        raw = _gemini_json([uploaded, TRANSCRIPT_PROMPT], TRANSCRIPT_SCHEMA, cfg)
    finally:
        try:
            client.files.delete(name=uploaded.name)
        except Exception:  # the file expires on its own after 48 h
            pass
    segments = [
        {
            "id": index,
            "start": round(float(piece["start"]), 2),
            "end": round(float(piece["end"]), 2),
            "text": str(piece["text"]).strip(),
        }
        for index, piece in enumerate(raw.get("segments") or [])
        if str(piece.get("text", "")).strip()
    ]
    seconds = max((piece["end"] for piece in segments), default=0.0)
    return segments, (raw.get("language") or cfg.language)[:8], float(seconds)


def transcribe_recording(url: str, folder: str, cfg: AiSettings):
    """(segments, language, audio seconds) for the recording at `url`."""
    if cfg.engine == "gemini":
        return gemini_transcribe(url, folder, cfg)
    audio = os.path.join(folder, "audio.wav")
    extract_audio(url, audio)
    return transcribe(audio, cfg)


def chat_json(system: str, prompt: str, schema: dict, cfg: AiSettings) -> dict:
    """One model call whose answer is constrained to `schema`."""
    if cfg.engine == "gemini":
        return _gemini_json(prompt, schema, cfg, system)
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
