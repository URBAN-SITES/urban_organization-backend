# Notification assessment and integration

> Historical assessment. For the current event matrix, frontend requirements and
> environment configuration after the branch integration, use
> [PUSH_NOTIFICATIONS.md](PUSH_NOTIFICATIONS.md).

Reviewed on 2026-10-23 across the backend, frontend and server Compose configuration.
This document describes the source integration. PRs and the deployment revision record
track rollout status; live Firebase delivery still requires browser acceptance.

## Inventory and gaps found

| Area | Existing behavior | Gap found / integrated behavior |
| --- | --- | --- |
| In-app inbox | Per-user persistence, newest first, 20-item pagination, unread filter, read and read-all API | Frontend only displayed a test button. It now uses the existing store to show notifications, filters, pagination, loading, errors and read actions. |
| Automatic events | Task assignment/reassignment, comments addressed to the assignee, chat mentions | These continue using the shared notification service. Self-assignment/comments and inaccessible chat mentions are excluded by existing business rules. |
| Browser devices | Unique FCM token, idempotent registration, reassignment to the latest account using that browser, per-user removal | Registration was disconnected from the UI. Activation now registers the token, remembers it locally, restores it on authenticated startup, and unregisters it before logout. Failed removal retains the token for retry. |
| Foreground | Firebase callback existed only on the test screen | Listening follows the authenticated session. FCM and WebSocket toasts share a notification ID to avoid two separate toast entries for the same notification. |
| Realtime | Authenticated `/ws/` user groups already used by chat | `notification.created` is emitted after commit. The frontend reloads the inbox/count, reconnects after connection loss and refreshes the unread count on window focus. |
| Background | PWA worker and FCM initialization existed | A notification payload was also manually displayed, risking duplication. Firebase now handles display and HTTPS click links to `/notificacoes`; icon and tag come from the backend. |
| Test sender | Authenticated endpoint accepted arbitrary tokens; frontend duplicated `v1` in URL | URL fixed. Only a device registered to the caller can be targeted. User push opt-out is enforced. The test does not create an inbox item. |
| Preferences | `UserSettings.push_enabled` stored in the database | It now suppresses push, while inbox persistence and realtime delivery remain available. There is still no public preferences API. The UI toggle controls this browser's token, not the global preference. |
| Transaction safety | FCM could run before the business transaction committed | Persistence remains inside the business transaction; external delivery runs after commit. Rollback delivers nothing. A WebSocket failure does not prevent an FCM attempt. |
| Delivery failures | Best-effort FCM and dead-token cleanup | Retained, with multicast batches capped at 500. Provider failures preserve the inbox item. Missing/invalid credential files return 503 on the test endpoint. |
| Other channels | SMTP/Celery for authentication codes and invitation emails | Those existing email flows are separate from product notifications. Payments, deadlines and weekly digests do not currently create notifications. |

The visible `/kanban` page still renders static example cards, and the frontend chat
module currently exports types without a screen or message service. Notification events
therefore exist in the backend even where the originating frontend interaction is not yet
integrated. Completing those business screens is separate from connecting the inbox.

## Contract

All HTTP routes below are under `/api/v1`, use the authenticated shared axios client,
and require CSRF for cookie-authenticated writes.

| Method / path | Request / result |
| --- | --- |
| `GET /notifications/?unread=true&page=1` | `{count, next, previous, results: [{id, title, message, data, is_read, created_at}]}` |
| `POST /notifications/<id>/read/` | No payload; 204. Another user's ID returns 404. |
| `POST /notifications/read-all/` | No payload; 204. |
| `POST /notifications/devices/` | `{token}`; 204. |
| `DELETE /notifications/devices/` | `{token}` in the JSON body; 204; scoped to the caller. |
| `POST /notifications/send/` | `{token, title, body?}`; `{message_id}`. 403 for a token not owned by the caller or global push opt-out; 503 if credentials are unavailable; 502 for an FCM provider error. |

WebSocket event: `{type: "notification.created", notification: <inbox item>}`.
FCM contains `notification: {title, body}`, string-valued event data and `notification_id`.
An accepted FCM message ID is not proof that a browser displayed the notification.

## Configuration assessment

- The service-account JSON is present and the configured project IDs in `.env.prod`
  and frontend `.env.local` match it. Firebase browser variables and VAPID are populated.
  This checks local configuration consistency, not provider authorization or live delivery.
- Production backend and worker mount the credential secret successfully. Keep the private
  JSON out of Git, Docker build contexts and all `VITE_*` variables.
- The development backend inherited `/run/secrets/firebase_admin` from `.env`, but that
  secret is not mounted in development. Both development Compose copies now override
  `FIREBASE_CREDENTIALS=/app/firebase-credentials.json`, using the existing bind mount.
  An already-running container must be recreated to pick up this environment change.
- `FRONTEND_URL` now also exists in Django settings and supplies the notification click
  destination. FCM click links are included only for HTTPS URLs.
- Vite proxies `/ws/` as well as `/api/`. Production Nginx already proxies WebSockets.
- The full pre-deployment suite exposed an existing CORS regression on `dev`: every
  origin was accepted despite the existing rejection test. The configured trusted-origin
  allowlist is restored, including production origins appended by production settings.
- Push requires a supported browser, permission, a secure context and an active worker.
  The Vite development server has the PWA worker disabled; the UI reports this instead
  of waiting indefinitely. Test push in a built/previewed or HTTPS deployed application.
- The in-memory channel layer supports the current single web process. It does not
  distribute WebSocket events between processes or from a separate Celery worker.

## Next implementation priorities

1. Add a user-settings API and UI for global push opt-out, category preferences and
   quiet hours. Reuse the existing settings model; keep per-browser activation separate.
2. Add notification events for invitation acceptance, payment approval and relevant task
   status changes. Define recipient rules and idempotency for repeated webhook events.
3. Add scheduled deadline reminders and weekly digests with Celery Beat, timezone-aware
   windows and persistent deduplication. The worker exists; periodic scheduling does not.
4. Move FCM delivery to Celery with transient-error retry/backoff, a durable delivery
   record and provider failure metrics. Current post-commit delivery is synchronous,
   has no retry and can add request latency. There is no guaranteed delivery/outbox.
5. Use a Redis-backed channel layer before increasing web replicas or moving realtime
   delivery into worker processes. Add cross-tab read-state events and full background
   token lifecycle handling, including remote session revocation.
6. Open the specific task/chat message from notification data after their frontend routes
   are integrated. Current clicks open the working inbox rather than a placeholder route.

## Verification and rollout

Frontend checks: `npm run type-check`, `npm run lint`, `npm run build`, and
`node --test src/modules/notifications/__tests__/notifications.spec.ts` (Node 24).
The focused tests use real Pinia/Vue and mock HTTP/Firebase boundaries; no new test
runner dependency was added. They cover unread pagination, read actions, account reset,
list errors, refreshes during in-flight requests, token registration and removal retry.

Backend checks: `python manage.py check`, Ruff on changed Python files, and
`python manage.py test core.modules.notifications core.modules.kanban core.modules.chat --noinput`.
Run tests with `FIREBASE_CREDENTIALS=` so unrelated tests never call the live provider;
the push tests override settings and mock FCM explicitly. The full suite also needs
`FIELD_ENCRYPTION_KEY` for its isolated database; CI uses a documented non-secret fixture
key and local runs can generate an ephemeral Fernet key.

The backend domain suite passed 91 tests; the final focused backend run passed 18 tests.
The frontend focused run passed 6 tests; lint, type-check, PWA build and Ruff passed.

Before production rollout, perform a browser acceptance test with two accounts: assign a
real task through the existing backend API (the current Kanban screen is static), verify
only the recipient's inbox and unread count update; activate push;
verify one foreground toast and one background notification; click it; mark as read;
reload; log out and verify this browser stops receiving that account's pushes. Repeat
with denied permission and a network failure during token removal.

No migration or dependency change is needed. Deploy backend and frontend together.
The integration targets `dev` in both repositories and preserves the working checkouts.
GitHub collision checks found no overlapping open PRs when preparing this integration.

Firebase references: [receiving web messages](https://firebase.google.com/docs/cloud-messaging/web/receive-messages)
and [Admin SDK delivery](https://firebase.google.com/docs/cloud-messaging/send/admin-sdk).
