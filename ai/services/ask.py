import logging
from functools import cache

import anthropic
from rest_framework import exceptions

from ai.response_messages import MSG_AI_BUSY, MSG_AI_DECLINED, MSG_AI_UNAVAILABLE

logger = logging.getLogger(__name__)

AI_MODEL = "claude-opus-5-5"
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant. Answer concisely."


@cache
def _client() -> anthropic.Anthropic:
    # reads ANTHROPIC_API_KEY from the environment
    return anthropic.Anthropic()


class AIService:
    @staticmethod
    def ask(prompt: str, system: str = DEFAULT_SYSTEM_PROMPT) -> str:
        """One-shot question to Claude. Reuse it for summaries, classification, extraction..."""
        try:
            response = _client().beta.messages.create(
                model=AI_MODEL,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": "low"},
                # if Claude declines, the API retries on a fallback model in the same call
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.RateLimitError:
            raise exceptions.Throttled(detail=MSG_AI_BUSY)
        except anthropic.APIError as error:
            logger.exception("Claude API error: %s", error)
            raise exceptions.APIException(MSG_AI_UNAVAILABLE)

        if response.stop_reason == "refusal":
            raise exceptions.ValidationError({"prompt": MSG_AI_DECLINED})
        return "".join(block.text for block in response.content if block.type == "text")
