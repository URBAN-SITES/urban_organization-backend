import logging
from functools import cache

from google import genai
from google.genai.errors import APIError
from rest_framework import exceptions

from core.ai.response_messages import MSG_AI_BUSY, MSG_AI_DECLINED, MSG_AI_UNAVAILABLE

logger = logging.getLogger(__name__)

# gemini-flash-lite-latest is fast, free tier supported and responsive
AI_MODEL = "gemini-flash-lite-latest"
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant. Answer concisely."


@cache
def _client() -> genai.Client:
    # Reads GEMINI_API_KEY from the environment automatically
    return genai.Client()


class AIService:
    @staticmethod
    def ask(prompt: str, system: str = DEFAULT_SYSTEM_PROMPT) -> str:
        """One-shot question to Gemini. Reuse it for summaries, classification, extraction..."""
        try:
            client = _client()
            response = client.models.generate_content(
                model=AI_MODEL,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    system_instruction=system,
                ),
            )
        except APIError as error:
            if getattr(error, "code", None) == 429:
                raise exceptions.Throttled(detail=MSG_AI_BUSY)
            logger.exception("Gemini API error: %s", error)
            raise exceptions.APIException(MSG_AI_UNAVAILABLE)
        except Exception as error:
            logger.exception("Gemini client error: %s", error)
            raise exceptions.APIException(MSG_AI_UNAVAILABLE)

        if not response or not response.text:
            raise exceptions.ValidationError({"prompt": MSG_AI_DECLINED})
        return response.text
