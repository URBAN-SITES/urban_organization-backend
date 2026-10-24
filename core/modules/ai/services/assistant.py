import hashlib
import json
import logging
import os
import time
import uuid

from django.core.cache import cache
from django.utils import timezone
from google.genai import types
from google.genai.errors import APIError
from rest_framework import exceptions

from core.modules.ai.prompts.assistant import ASSISTANT_INSTRUCTIONS
from core.modules.ai.response_messages import (
    MSG_AI_ACTION_FAILED,
    MSG_AI_ACTION_INTERRUPTED,
    MSG_AI_BUSY,
    MSG_AI_DECLINED,
    MSG_AI_INVALID_ARGUMENTS,
    MSG_AI_INVALID_CONVERSATION,
    MSG_AI_UNAVAILABLE,
)
from core.modules.ai.services.actions import get_action, json_value, registry
from core.modules.ai.services.ask import AI_MODEL, _client
from core.modules.kanban.services.sector import SectorService
from core.modules.kanban.services.task import TaskService
from core.modules.organizations.services.organization import OrganizationService
from core.modules.user_settings.services.user_settings import UserSettingsService

logger = logging.getLogger(__name__)
MAX_ROUNDS = 12
MAX_CALLS = 40
MAX_SECONDS = 180
HISTORY_TTL = 1800
REQUEST_TTL = 86400


def tool_declarations():
    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="discover_actions",
                    description="Read the supported actions and exact argument schemas for a domain prefix.",
                    parameters_json_schema={
                        "type": "object",
                        "properties": {"prefix": {"type": "string"}},
                        "additionalProperties": False,
                    },
                ),
                types.FunctionDeclaration(
                    name="execute_action",
                    description="Execute one supported action as the authenticated user. arguments must be a JSON string matching the discovered schema.",
                    parameters_json_schema={
                        "type": "object",
                        "properties": {
                            "action": {"type": "string"},
                            "arguments": {"type": "string"},
                        },
                        "required": ["action", "arguments"],
                        "additionalProperties": False,
                    },
                ),
            ]
        )
    ]


def checked_context(user, context):
    if context.get("organization_id"):
        OrganizationService.get_membership(user, context["organization_id"])
    if context.get("sector_id"):
        sector, _ = SectorService.get_sector(user, context["sector_id"])
        if context.get("organization_id") and str(sector.organization_id) != str(
            context["organization_id"]
        ):
            raise exceptions.ValidationError(MSG_AI_INVALID_ARGUMENTS)
    if context.get("task_id"):
        task, sector, _ = TaskService.get_task(user, context["task_id"])
        if (
            context.get("sector_id")
            and str(task.sector_id) != str(context["sector_id"])
        ) or (
            context.get("organization_id")
            and str(sector.organization_id) != str(context["organization_id"])
        ):
            raise exceptions.ValidationError(MSG_AI_INVALID_ARGUMENTS)
    return json_value(context)


class AssistantService:
    @classmethod
    def ask(cls, user, prompt, context=None, conversation_id=None, request_id=None):
        context = json_value(context or {})
        request_key = f"ai:request:{user.pk}:{request_id or uuid.uuid4()}"
        fingerprint = hashlib.sha256(
            json.dumps([prompt, context, str(conversation_id)], sort_keys=True).encode()
        ).hexdigest()
        previous = cache.get(request_key)
        if previous:
            if previous["fingerprint"] != fingerprint:
                raise exceptions.ValidationError(MSG_AI_INVALID_ARGUMENTS)
            return previous["response"]
        if not cache.add(request_key + ":lock", True, timeout=900):
            raise exceptions.Throttled(detail=MSG_AI_BUSY)
        try:
            # Close the race between reading the cached response and taking the lock.
            previous = cache.get(request_key)
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise exceptions.ValidationError(MSG_AI_INVALID_ARGUMENTS)
                return previous["response"]
            context = checked_context(user, context)
            history = []
            if conversation_id:
                history = cache.get(f"ai:history:{user.pk}:{conversation_id}")
                if history is None:
                    raise exceptions.ValidationError(MSG_AI_INVALID_CONVERSATION)
            result = cls._run(user, prompt, context, history)
            history = (
                history
                + [
                    {
                        "user": prompt,
                        "answer": result["answer"],
                        "actions": result["actions"],
                    }
                ]
            )[-6:]
            result["conversation_id"] = None
            if len(json.dumps(history)) <= 150000:
                next_id = str(uuid.uuid4())
                cache.set(f"ai:history:{user.pk}:{next_id}", history, HISTORY_TTL)
                result["conversation_id"] = next_id
            cache.set(
                request_key,
                {"fingerprint": fingerprint, "response": result},
                REQUEST_TTL,
            )
            return result
        finally:
            cache.delete(request_key + ":lock")

    @classmethod
    def _run(cls, user, prompt, context, history):
        preferences = UserSettingsService.get(user)
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text=json.dumps(
                            {
                                "current_request": prompt,
                                "selected_context": context,
                                "current_user": {
                                    "id": str(user.pk),
                                    "name": user.name,
                                    "timezone": preferences.timezone,
                                },
                                "previous_conversation_data": history,
                            },
                            ensure_ascii=False,
                        )
                    )
                ],
            )
        ]
        config = types.GenerateContentConfig(
            system_instruction=ASSISTANT_INSTRUCTIONS
            + "\nCurrent server time: "
            + timezone.now().isoformat(),
            tools=tool_declarations(),
            max_output_tokens=8192,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
            http_options=types.HttpOptions(
                timeout=60000, retry_options=types.HttpRetryOptions(attempts=1)
            ),
        )
        actions, seen = [], {}
        calls_used = 0
        deadline = time.monotonic() + MAX_SECONDS
        for _ in range(MAX_ROUNDS):
            if time.monotonic() >= deadline:
                return cls._interrupted(actions)
            try:
                response = _client().models.generate_content(
                    model=os.getenv("AI_ASSISTANT_MODEL", AI_MODEL),
                    contents=contents,
                    config=config,
                )
                candidate = (
                    response.candidates[0] if response and response.candidates else None
                )
                if (
                    not candidate
                    or not candidate.content
                    or candidate.finish_reason != types.FinishReason.STOP
                ):
                    raise exceptions.ValidationError(MSG_AI_DECLINED)
                content = candidate.content
            except Exception as error:
                # Never drop receipts after a write, even if the next model call fails.
                if actions:
                    return cls._interrupted(actions)
                if isinstance(error, exceptions.APIException):
                    raise
                if isinstance(error, APIError) and error.code == 429:
                    raise exceptions.Throttled(detail=MSG_AI_BUSY) from None
                logger.warning(
                    "AI assistant provider failure (%s)", type(error).__name__
                )
                raise exceptions.APIException(MSG_AI_UNAVAILABLE) from None
            calls = [
                part.function_call for part in content.parts or [] if part.function_call
            ]
            if not calls:
                answer = "".join(
                    part.text
                    for part in content.parts or []
                    if part.text and not part.thought
                )
                if not answer:
                    return cls._interrupted(actions)
                return {"answer": answer, "actions": actions, "interrupted": False}
            # Preserve complete model content, including Gemini thought signatures.
            contents.append(content)
            results = []
            for call in calls:
                if calls_used >= MAX_CALLS or time.monotonic() >= deadline:
                    return cls._interrupted(actions)
                calls_used += 1
                result = cls._tool(user, call, actions, seen)
                results.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=call.name, id=call.id, response=result
                        )
                    )
                )
            contents.append(types.Content(role="user", parts=results))
        return cls._interrupted(actions)

    @staticmethod
    def _interrupted(actions):
        return {
            "answer": str(MSG_AI_ACTION_INTERRUPTED),
            "actions": actions,
            "interrupted": True,
        }

    @staticmethod
    def _tool(user, call, actions, seen):
        receipt = None
        key = None
        try:
            args = call.args or {}
            if call.name == "discover_actions":
                if set(args) - {"prefix"} or not isinstance(
                    args.get("prefix", ""), str
                ):
                    raise exceptions.ValidationError(MSG_AI_INVALID_ARGUMENTS)
                return {
                    "actions": [
                        a.describe()
                        for name, a in registry().items()
                        if name.startswith(args.get("prefix", ""))
                    ]
                }
            if call.name != "execute_action" or set(args) != {"action", "arguments"}:
                raise exceptions.ValidationError(MSG_AI_INVALID_ARGUMENTS)
            if (
                not isinstance(args["action"], str)
                or not isinstance(args["arguments"], str)
                or len(args["arguments"]) > 30000
            ):
                raise exceptions.ValidationError(MSG_AI_INVALID_ARGUMENTS)
            action = get_action(args["action"])
            arguments = json.loads(args["arguments"])
            key = json.dumps([action.name, arguments], sort_keys=True)
            if action.write and key in seen:
                return {**seen[key], "replayed": True}
            receipt = {"action": action.name, "writes": action.write}
            if isinstance(arguments, dict):
                receipt["targets"] = {
                    key: value for key, value in arguments.items() if key in action.ids
                }
                if isinstance(arguments.get("data"), dict):
                    receipt["targets"].update(
                        {
                            key: value
                            for key, value in arguments["data"].items()
                            if key in ("event_id", "calendar_id")
                        }
                    )
            value = action.execute(user, arguments)
            receipt.update(status="succeeded", result=value)
        except exceptions.APIException as error:
            failure = {
                "status": "uncertain" if error.status_code >= 500 else "failed",
                "error": {
                    "code": error.status_code,
                    "detail": json_value(error.detail),
                },
            }
            if receipt is None:
                return failure
            receipt.update(failure)
        except ValueError, TypeError, RecursionError:
            failure = {
                "status": "failed",
                "error": {"code": 400, "detail": str(MSG_AI_INVALID_ARGUMENTS)},
            }
            if receipt is None:
                return failure
            # A handler may have committed a side effect before raising.
            receipt.update(
                status="uncertain", error={"detail": str(MSG_AI_ACTION_FAILED)}
            )
        except Exception as error:
            logger.warning("AI action failure (%s)", type(error).__name__)
            if receipt is None:
                return {
                    "status": "failed",
                    "error": {"detail": str(MSG_AI_ACTION_FAILED)},
                }
            receipt.update(
                status="uncertain", error={"detail": str(MSG_AI_ACTION_FAILED)}
            )
        actions.append(receipt)
        if receipt["writes"]:
            seen[key] = receipt
        return receipt
