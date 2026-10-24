import hashlib
import json
import logging
import os
import re
import time
import uuid

from django.core.cache import cache
from django.utils import timezone
from google.genai import types
from google.genai.errors import APIError
import httpx
from rest_framework import exceptions

from core.modules.ai.prompts.assistant import ASSISTANT_INSTRUCTIONS
from core.modules.ai.response_messages import (
    MSG_AI_ACTION_FAILED,
    MSG_AI_ACTION_INTERRUPTED,
    MSG_AI_BUSY,
    MSG_AI_CONFIRMATION_REQUIRED,
    MSG_AI_CONFIRMED_ALL,
    MSG_AI_CONFIRMED_PARTIAL,
    MSG_AI_DECLINED,
    MSG_AI_STUCK,
    MSG_AI_INVALID_ARGUMENTS,
    MSG_AI_INVALID_CONFIRMATION,
    MSG_AI_INVALID_CONVERSATION,
    MSG_AI_UNAVAILABLE,
    MSG_AI_UNVERIFIED,
)
from core.modules.ai.services.actions import get_action, json_value, registry
from core.modules.ai.services.ask import AI_MODEL, _client
from core.modules.kanban.services.sector import SectorService
from core.modules.kanban.services.status import StatusService
from core.modules.kanban.services.task import TaskService
from core.modules.organizations.services.organization import OrganizationService
from core.modules.user_settings.services.user_settings import UserSettingsService

logger = logging.getLogger(__name__)
# Tool calling needs a stronger model than the lite chatbot default.
ASSISTANT_MODEL = "gemini-flash-latest"
# Used once if the stronger model is overloaded before any tool has run.
FALLBACK_MODEL = AI_MODEL
FALLBACK_CODES = (429, 500, 502, 503, 504)
MAX_ROUNDS = 12
MAX_CALLS = 40
# Consecutive failed tool calls before the turn stops and asks the user for detail.
MAX_FAILURES = 3
MAX_SECONDS = 180
HISTORY_TTL = 1800
REQUEST_TTL = 86400
CONFIRM_TTL = 600
# Destructive actions never run on the model's say-so: the user confirms them.
DESTRUCTIVE_SUFFIXES = ("_delete", "_remove", "_revoke")


# First-person completion claims the model must never make without a receipt.
CLAIM_PATTERN = re.compile(
    r"\b(criei|cadastrei|adicionei|atualizei|alterei|modifiquei|movi|conclu[ií]|"
    r"exclu[ií]|apaguei|removi|registrei|atribu[ií]|defini|agendei)\b",
    re.IGNORECASE,
)


def unverified_claim(answer, actions):
    """True when the text says something was done but no write receipt succeeded."""
    if not CLAIM_PATTERN.search(answer):
        return False
    return not any(a.get("writes") and a.get("status") == "succeeded" for a in actions)


CHOICES_MARKER = "OPCOES:"
MAX_CHOICES = 6


def split_choices(answer):
    """Pull the optional trailing `OPCOES: a | b` line out of the answer.

    Choices are only UI shortcuts: picking one sends an ordinary new message."""
    lines = answer.rstrip().split("\n")
    if not lines or not lines[-1].startswith(CHOICES_MARKER):
        return answer, []
    options = [
        o.strip()[:80]
        for o in lines[-1][len(CHOICES_MARKER) :].split("|")
        if o.strip()
    ]
    return "\n".join(lines[:-1]).rstrip(), options[:MAX_CHOICES]


def is_destructive(name):
    return name.endswith(DESTRUCTIVE_SUFFIXES)


def pending_key(user):
    return f"ai:confirm:{user.pk}"


def compact_actions(actions):
    """Keep history small: receipts without full payloads."""
    compact = []
    for receipt in actions:
        entry = {
            key: receipt[key] for key in ("action", "status", "targets") if key in receipt
        }
        result = receipt.get("result")
        if isinstance(result, dict):
            entry["result"] = {
                key: result[key]
                for key in ("id", "title", "name", "status")
                if key in result
            }
        compact.append(entry)
    return compact


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
    def ask(
        cls,
        user,
        prompt,
        context=None,
        conversation_id=None,
        request_id=None,
        confirmation_token=None,
    ):
        context = json_value(context or {})
        request_key = f"ai:request:{user.pk}:{request_id or uuid.uuid4()}"
        fingerprint = hashlib.sha256(
            json.dumps(
                [prompt, context, str(conversation_id), str(confirmation_token)],
                sort_keys=True,
            ).encode()
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
            pending = []
            if confirmation_token:
                result = cls._confirm(user, confirmation_token)
            else:
                # A new message supersedes any deletion still awaiting confirmation.
                cache.delete(pending_key(user))
                result = cls._run(user, prompt, context, history, pending)
            result["confirmation_token"] = cls._store_pending(user, pending)
            history = (
                history
                + [
                    {
                        "user": prompt,
                        "answer": result["answer"],
                        "actions": compact_actions(result["actions"]),
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

    @staticmethod
    def _store_pending(user, pending):
        if not pending:
            return None
        token = str(uuid.uuid4())
        cache.set(pending_key(user), {"token": token, "actions": pending}, CONFIRM_TTL)
        return token

    @classmethod
    def _confirm(cls, user, token):
        stored = cache.get(pending_key(user))
        if not stored or stored["token"] != str(token):
            raise exceptions.ValidationError(MSG_AI_INVALID_CONFIRMATION)
        # Single use, even if execution is interrupted: never replay a delete.
        cache.delete(pending_key(user))
        actions, seen = [], {}
        for item in stored["actions"]:
            call = types.FunctionCall(
                name="execute_action",
                args={
                    "action": item["action"],
                    "arguments": json.dumps(item["arguments"]),
                },
            )
            cls._tool(user, call, actions, seen, [], confirmed=True)
        done = sum(1 for a in actions if a["status"] == "succeeded")
        message = MSG_AI_CONFIRMED_ALL if done == len(actions) else MSG_AI_CONFIRMED_PARTIAL
        return {
            "answer": str(message) % {"done": done, "total": len(actions)},
            "actions": actions,
            "interrupted": False,
        }

    @staticmethod
    def _snapshot(user, context):
        """Ground the model in real IDs so it does not have to guess or probe."""
        organizations = [
            {"id": str(org.pk), "name": org.name, "role": org.current_role}
            for org in OrganizationService.list_for(user)
        ]
        snapshot = {"organizations": organizations}
        scope = (
            [o for o in organizations if o["id"] == str(context["organization_id"])]
            if context.get("organization_id")
            else organizations
        )
        sectors = []
        for org in scope:
            for sector in SectorService.list_for(user, org["id"]):
                sectors.append(
                    {"id": str(sector.pk), "name": sector.name, "organization_id": org["id"]}
                )
        snapshot["sectors"] = sectors[:30]
        if context.get("sector_id"):
            snapshot["selected_sector_statuses"] = [
                {"id": str(s.pk), "name": s.name, "category": s.category}
                for s in StatusService.list_for(user, context["sector_id"])
            ]
        return snapshot

    @classmethod
    def _run(cls, user, prompt, context, history, pending):
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
                                "workspace_snapshot": cls._snapshot(user, context),
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
        failures = 0
        model = os.getenv("AI_ASSISTANT_MODEL", ASSISTANT_MODEL)
        calls_used = 0
        deadline = time.monotonic() + MAX_SECONDS
        for _ in range(MAX_ROUNDS):
            if time.monotonic() >= deadline:
                return cls._interrupted(actions)
            try:
                response = _client().models.generate_content(
                    model=model,
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
                # Without writes, restarting the turn on the lighter model is safe.
                if (
                    model != FALLBACK_MODEL
                    and not any(a["writes"] for a in actions)
                    and (
                        isinstance(error, httpx.TimeoutException)
                        or (isinstance(error, APIError) and error.code in FALLBACK_CODES)
                    )
                ):
                    logger.warning(
                        "AI assistant model fallback (%s)",
                        getattr(error, "code", type(error).__name__),
                    )
                    model = FALLBACK_MODEL
                    # Thought signatures belong to the model that produced them.
                    del contents[1:]
                    actions.clear()
                    seen.clear()
                    continue
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
            logger.info(
                "AI round model=%s calls=%s text=%s",
                model,
                [c.name for c in calls],
                any(p.text for p in content.parts or []),
            )
            if not calls:
                answer = "".join(
                    part.text
                    for part in content.parts or []
                    if part.text and not part.thought
                )
                if not answer:
                    return cls._interrupted(actions)
                answer, choices = split_choices(answer)
                if not answer:
                    return cls._interrupted(actions)
                unverified = unverified_claim(answer, actions)
                if unverified:
                    answer += str(MSG_AI_UNVERIFIED)
                return {
                    "answer": answer,
                    "actions": actions,
                    "interrupted": False,
                    "choices": choices,
                    "unverified": unverified,
                }
            # Preserve complete model content, including Gemini thought signatures.
            contents.append(content)
            results = []
            for call in calls:
                if calls_used >= MAX_CALLS or time.monotonic() >= deadline:
                    return cls._interrupted(actions)
                calls_used += 1
                result = cls._tool(user, call, actions, seen, pending)
                failures = failures + 1 if result.get("status") == "failed" else 0
                results.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=call.name, id=call.id, response=result
                        )
                    )
                )
            contents.append(types.Content(role="user", parts=results))
            if failures >= MAX_FAILURES:
                return {
                    "answer": str(MSG_AI_STUCK),
                    "actions": actions,
                    "interrupted": True,
                }
        return cls._interrupted(actions)

    @staticmethod
    def _interrupted(actions):
        return {
            "answer": str(MSG_AI_ACTION_INTERRUPTED),
            "actions": actions,
            "interrupted": True,
        }

    @staticmethod
    def _tool(user, call, actions, seen, pending, confirmed=False):
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
            if is_destructive(action.name) and not confirmed:
                if not isinstance(arguments, dict):
                    raise exceptions.ValidationError(MSG_AI_INVALID_ARGUMENTS)
                pending.append({"action": action.name, "arguments": arguments})
                receipt.update(
                    status="confirmation_required",
                    detail=str(MSG_AI_CONFIRMATION_REQUIRED),
                )
            else:
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
