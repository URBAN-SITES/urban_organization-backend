# Backend review and subscriber AI chat plan

## Review scope and repository state

Reviewed the repository structure, team rules, project configuration, routes,
models and central services for authentication, organizations, teams, Kanban,
chat, AI, payments, uploads, search, notifications and Calendar integration.
This is an architectural review, not a complete security audit or runtime validation.

- Working branch: `feat/subscriber-ai-chat`, created from local `dev` at `a2a53fe`.
- Local `dev` matched the cached `origin/dev`; no remote refresh was performed.
- The previous branch, `fix/org-removal-cleanup`, contains commit `f7feb07`
  beyond `dev`. That member-access cleanup is not included in this branch.
  Coordinate its integration before changing organization access behavior.
- Initial working tree was clean.
- GitHub CLI is unauthenticated. Open Issues, PRs and Project status could not
  be checked or updated. No Issue or owner was supplied for this feature.

## Existing backend

| Area | Current implementation | Relevance to the new feature |
|------|------------------------|------------------------------|
| Architecture | Django/DRF, one `core` app, layered feature modules | Extend `core/modules/ai`; keep business logic in services |
| Authentication | JWT cookies, active sessions, CSRF on cookie writes, Google login | Reuse the current authenticated user; never accept an actor from AI output |
| Organizations and teams | Memberships, roles, personal workspaces, sector/team links | Resolve access from current membership for every operation |
| Kanban | Sectors, statuses, tasks, assignments, checklist, comments, links, progress | Reuse task serializers and `TaskService` for mutations |
| Human chat | Organization, sector, team, multi-team and direct channels; messages, mentions, task citations | Already serves communication between people; no AI channel exists |
| Real time | Channels endpoint `/ws/`, user events, typing and presence | Optional later extension; HTTP is enough for a first AI flow |
| AI | `POST /api/v1/ai/ask/`, Gemini text generation, provider error mapping | One-shot only; no history, structured actions or subscription check |
| Payments | Mercado Pago PIX creation, local payment status, webhook provider lookup | Payment records exist; plans and subscriptions do not |
| Uploads and search | Cloudinary attachment handling, scoped task/people/file search | Keep AI context scoped to accessible resources |
| Notifications | Persistent notifications and Firebase integration | Existing task service already handles assignee notification |
| Calendar | Google OAuth, stored encrypted credentials, Meet creation; event model | Separate from the initial AI task-creation scope |
| Other models | User settings and advanced Kanban schema | Do not assume every modeled feature has an implemented API |
| Operations | Docker/deployment scripts, PostgreSQL production, SQLite development, Celery/Redis integration | Validate with installed locked dependencies before delivery |

## Gaps affecting subscribers-only AI

1. `AIAskView` requires only `IsAuthenticated`. Any logged-in user can currently
   call it. A new paid route alone would leave this existing entry point open.
2. `Payment` has status and amount, but no plan, entitlement period or renewal
   contract. An approved payment alone cannot establish an active subscription.
3. PIX title and amount currently come from request validation. A subscription
   checkout must resolve its product and price on the server.
4. AI responses are plain text. There is no task extraction schema, action
   validation, execution record or duplicate-request protection for AI actions.
5. There are no private AI conversation/message models or conversation ownership
   rules. Human chat models require an organization and human-channel semantics.
6. Global throttles exist, but there is no AI-specific usage quota. Provider
   throttling is handled only after Gemini returns an error.
7. Existing AI tests cover generated text and empty output, not paid access,
   conversation isolation or task execution.

## Proposed first delivery (not implemented)

A separate private AI chat for an authenticated subscriber. The user selects a
sector and sends a prompt such as "Create a high-priority task to review the
presentation tomorrow". The backend extracts a typed task proposal, validates
its fields and creates the task through the existing Kanban service. The
response includes the assistant message and the actual created task identifier.

The subscriber must also have editor access to the selected sector. Paying must
never grant additional organization or sector privileges.

### Integration sequence

1. Agree on entitlement ownership (individual user or organization), duration,
   plan pricing, cancellation/refund behavior and usage allowance.
2. Define a subscription/entitlement model and server-owned purchase contract.
   Update entitlement from verified provider state with idempotent processing;
   pending or rejected payments must not unlock AI.
3. Add a reusable active-subscription permission and enforce it on all public AI
   entry points, including the existing `ask` endpoint.
4. Add private AI conversations and messages inside the AI module, scoped to
   owner and selected sector. Register models through `core/models/__init__.py`
   and migrations under `core/migrations/`.
5. Add structured task extraction. Treat model output as untrusted input:
   validate allowed fields and resolve referenced objects with current access.
   Never execute generated Python, SQL or arbitrary tool names.
6. Execute through `TaskService.create(user, sector_id, validated_data)` using
   `TaskCreateSerializer` where applicable. Preserve assignment checks, status
   rules, WIP limits, completion timestamps and notifications.
7. Record execution results and use a per-user request identifier to prevent
   repeated requests from creating duplicate tasks. Do not hold a database
   transaction open during a Gemini network request.
8. Add AI usage limits and bounded history. Keep the initial flow to task
   creation; task changes, deletion and bulk execution require separate scope.

### Proposed API shape for agreement

These routes and payloads are proposals, not existing contracts:

- `POST /api/v1/ai/conversations/`: create a private conversation for `sector_id`.
- `GET /api/v1/ai/conversations/`: list the caller's conversations.
- `GET /api/v1/ai/conversations/<id>/messages/`: paginated private history.
- `POST /api/v1/ai/conversations/<id>/messages/`: accept `prompt` and
  `request_id`; return the assistant message and any created task.

Use the existing cookie/CSRF flow. Resolve subscription and sector access before
provider calls and check them again before a delayed write. Do not send unrelated
organization data or provider credentials to the model.

### Acceptance criteria

- Anonymous users and users without an active subscription cannot invoke AI.
- Expired, revoked or refunded entitlement prevents new AI operations.
- The existing `ask` endpoint cannot bypass paid access.
- A subscriber can create a valid task by prompt in a sector they can edit.
- A subscriber with viewer access cannot create tasks through AI.
- Conversations and task context never leak between users or organizations.
- Invalid output, nonexistent references and provider failure create no task.
- Retrying the same request creates at most one task.
- Replies report database results and do not claim an action that failed.
- Relevant permission, payment-state, isolation and task-execution tests pass.

## Verification and handoff

No application code, dependencies, settings or migrations were changed.

Attempted checks:

- `pdm run python manage.py check`: PDM launcher could not write its cache lock
  under the sandbox. Retried directly using the existing virtualenv.
- `.venv/bin/python manage.py check`: failed during startup with
  `ModuleNotFoundError: No module named 'celery'`.
- `.venv/bin/ruff check .`: failed because the executable is absent.
- The test suite did not execute because the preceding startup check failed.

Install the existing locked environment before rerunning Django checks, tests
and Ruff. No Gemini, Mercado Pago, Cloudinary, Firebase or Google Calendar live
operation was performed.

Before implementation, associate an Issue, check remote overlap and agree on the
subscription rules and shared API/model contracts. Repository rules require
owner approval for dependencies, migrations, authentication, global settings
and shared API changes. This document prepares that review without introducing
those changes.
