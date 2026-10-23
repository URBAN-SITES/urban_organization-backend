import json
import logging
import os

from google.genai import types
from google.genai.errors import APIError
from rest_framework import exceptions

from core.modules.ai.prompts.analysis import FILE_ANALYSIS_INSTRUCTIONS
from core.modules.ai.response_messages import (
    MSG_AI_BUSY,
    MSG_AI_DECLINED,
    MSG_AI_INVALID_ANALYSIS,
    MSG_AI_UNAVAILABLE,
)
from core.modules.ai.serializers.analysis import AIFileAnalysisSerializer
from core.modules.ai.services.ask import AI_MODEL, _client

logger = logging.getLogger(__name__)


class GeminiClient:
    @staticmethod
    def analyze(file):
        """Reuse the chatbot's SDK client with independent analysis instructions."""
        try:
            response = _client().models.generate_content(
                model=os.getenv("AI_ANALYSIS_MODEL", AI_MODEL),
                contents=[
                    types.Part.from_bytes(
                        data=file["data"], mime_type=file["mime_type"]
                    ),
                    "Analyze this file using the required schema.",
                ],
                config=types.GenerateContentConfig(
                    system_instruction=FILE_ANALYSIS_INSTRUCTIONS,
                    response_mime_type="application/json",
                    response_json_schema=AIFileAnalysisSerializer.json_schema(),
                    max_output_tokens=8192,
                    http_options=types.HttpOptions(
                        timeout=int(os.getenv("AI_ANALYSIS_TIMEOUT_MS", "60000")),
                        retry_options=types.HttpRetryOptions(attempts=1),
                    ),
                ),
            )
        except APIError as error:
            if getattr(error, "code", None) == 429:
                raise exceptions.Throttled(detail=MSG_AI_BUSY) from error
            # Do not log provider messages: they may include uploaded content.
            logger.warning(
                "Gemini analysis API error (code=%s)", getattr(error, "code", None)
            )
            raise exceptions.APIException(MSG_AI_UNAVAILABLE) from error
        except Exception as error:
            logger.warning("Gemini analysis client failed (%s)", type(error).__name__)
            raise exceptions.APIException(MSG_AI_UNAVAILABLE) from error

        if not response or not response.candidates:
            raise exceptions.ValidationError(MSG_AI_DECLINED)
        if response.candidates[0].finish_reason != types.FinishReason.STOP:
            raise exceptions.ValidationError(MSG_AI_INVALID_ANALYSIS)
        text = response.text
        if not text:
            raise exceptions.ValidationError(MSG_AI_DECLINED)
        if len(text) > 262144:
            raise exceptions.ValidationError(MSG_AI_INVALID_ANALYSIS)
        try:
            payload = json.loads(text)
        except (ValueError, RecursionError) as error:
            raise exceptions.ValidationError(MSG_AI_INVALID_ANALYSIS) from error
        serializer = AIFileAnalysisSerializer(data=payload)
        if not serializer.is_valid():
            raise exceptions.ValidationError(MSG_AI_INVALID_ANALYSIS)
        return serializer.validated_data
