# Workspace assistant

`POST /api/v1/ai/ask/` now executes application actions through Gemini function
calling. Authentication, CSRF and subscriber requirements are unchanged. The
existing `{ "prompt": "..." }` request and `answer` response remain supported.
The PDF analysis endpoint remains independent and has no action tools.

## Supported capabilities

The explicit registry in `services/actions.py` contains 94 actions:

| Area | Operations |
| --- | --- |
| Organizations | List, get, create, update, delete; add/remove members and change roles |
| Invitations | List organization/mine, create with optional sector access, revoke, accept |
| Teams | List, get, create, update, delete; members/roles and sector links |
| Kanban | Sectors, columns, tasks/subtasks: create, read, update, delete; move/complete/reopen tasks |
| Task details | Checklists, comments, resource links |
| Workspace | Search, dashboard, reports, file/link listing |
| Local agenda | List task deadlines; create/change/delete through task operations |
| Google Calendar | List/get/create/update/delete secondary calendars; list/get/create/update/delete timed events |
| Calendar sync | Inspect, sync or remove the current user's task event |
| Meet | Start immediately and post to a channel, or schedule via `event_create` with `meet=true` |
| Chat | List channels/messages, direct/team conversations, send/edit/delete, mark read |
| Preferences / Drive | Read/update preferences; list app-visible Drive files and attach existing files to tasks |

The assistant does not expose payments, refunds, subscription details, financial
notifications, passwords, session management, device tokens, arbitrary HTTP,
SQL, shell commands or arbitrary model/service invocation. Binary file uploads
still use the existing upload endpoints. It does not automatically track browser
activity; the frontend supplies selected context and the user supplies requests.

## Frontend contract

```json
{
  "prompt": "Crie uma tarefa de revisão para amanhã neste setor",
  "context": {
    "organization_id": "<organization UUID>",
    "sector_id": "<sector UUID>"
  },
  "request_id": "<new UUID for this user message>",
  "conversation_id": "<ID returned by the previous response, if any>"
}
```

`context`, `request_id` and `conversation_id` are optional. Context accepts
organization, sector and task UUIDs, checks access, and rejects mismatched parents.
It assists target resolution; it does not grant access. The actor always comes
from `request.user`. The assistant can discover the user's workspaces when no
context is supplied and asks for clarification if the target is ambiguous.

```json
{
  "answer": "Criei a tarefa de revisão.",
  "actions": [
    {
      "action": "task_create",
      "writes": true,
      "targets": { "sector_id": "<UUID>" },
      "status": "succeeded",
      "result": { "id": "<UUID>", "title": "Revisão" }
    }
  ],
  "conversation_id": "<UUID>",
  "interrupted": false
}
```

The task result above is abbreviated. Render `answer`, use action receipts to
refresh affected views, and retain `conversation_id` for follow-up questions.
For retries of the **same** user message reuse `request_id` with the identical
body. A new message gets a new UUID. Responses are cached per authenticated user
and request ID for 24 hours; reuse with a different payload is rejected. Identical
writes within one turn are also deduplicated. This is cache-based replay protection,
not exactly-once delivery across process crashes or cache loss.

Conversation history is server-side, owner-scoped, expires after 30 minutes and
retains up to six turns within a 150 KB serialized limit. If that size is exceeded,
`conversation_id` is null. An expired or another user's ID is rejected. Client-supplied
tool transcripts are not accepted. Use a shared cache such as the project's Redis
backend in multi-worker deployments; development's local-memory cache does not
share state between processes and is cleared on restart.

Tool errors have `status: failed` with an error code/detail; external server errors
or unexpected handler failures may be `uncertain`. Check uncertain operations
before retrying. A provider error after completed actions returns their receipts
with `interrupted: true`, rather than hiding the mutations behind a generic 500.
There is no transaction spanning multiple tools or external providers. The UI must
not interpret HTTP 200 alone as proof that every requested action succeeded.

## Execution and permissions

The model discovers schemas with `discover_actions`, then requests a named
`execute_action`. Only registered handlers are dispatchable. Arguments are validated
against existing serializers, rejecting unknown/read-only fields. Membership IDs
are integers; domain entities use UUIDs. Business services enforce existing roles,
private-sector access, assignee/parent relationships, WIP limits and deletion rules.

Names, documents, descriptions, chat messages and prior summaries are treated as
untrusted data in the system prompt. Prompt instructions are not a substitute for
the deterministic action allowlist, input validation and service permissions.
Secrets and payment records are not provided as tools. Ordinary workspace content
selected through tools is sent to Gemini, as required for these operations.

The loop runs sequentially and preserves complete Gemini model parts, including
thought signatures. It is limited to 12 rounds, 40 tool calls and a 180-second
budget checked between calls; an in-flight call can exceed the budget. Gemini
calls have a 60-second timeout and one attempt. External writes are not
automatically retried. Configure the HTTP deployment timeout accordingly.

`AI_ASSISTANT_MODEL` optionally overrides the existing chatbot model for the
action assistant. It must support Gemini function calling. `GEMINI_API_KEY` and
the SDK client are reused. `AIService.ask()` remains available as a text-only
internal utility; the HTTP endpoint now delegates to `AssistantService.ask()`.

## Google consent

Existing task event synchronization and immediate Meet creation reuse the
connected account and `calendar.events` grant. Calendar management additionally
uses `calendar.calendars`; listing calendars uses `calendar.calendarlist.readonly`.
`google_connect_url` returns a consent URL with these scopes, retaining the existing
signed state, redirect URI and callback. The user must open that URL and grant
access; the assistant cannot authorize itself. Register the requested scopes in
the Google Cloud OAuth consent configuration as applicable.

All Google requests go to fixed Calendar API paths with encoded identifiers,
redirects disabled, and the current user's token obtained only on the backend.
The primary calendar cannot be deleted. Event times require explicit offsets;
attendees receive Google's invitations/updates. Meet creation can be pending:
use `event_get` to retrieve the link later instead of creating another event.
If an immediate Meet is created but posting to chat fails, its link is still
returned with `posted: false`.

References:
- [Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling)
- [Calendar scopes](https://developers.google.com/workspace/calendar/api/auth)
- [Event creation and conference data](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert)
- [Secondary calendar deletion](https://developers.google.com/workspace/calendar/api/v3/reference/calendars/delete)

## Verification

Run `pdm run manage.py test core.modules.ai`. Tests mock Gemini/Google, while
application action tests exercise the real services and the isolated Django test
database. No real invitations, meetings or production resources are created.
They cover permissions, task lifecycle, memberships, invitations, chat, agenda,
calendar requests, malformed/unknown tools, deduplication, partial failures,
conversation ownership and the existing PDF/subscriber behavior.
