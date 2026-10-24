# Push notifications: backend, frontend and deployment contract

This is the current integration guide after the notification review on
`fix/notifications`. It supersedes the event inventory and environment advice in
`NOTIFICATIONS_INTEGRATION.md` and `NOTIFICATIONS_PUSH_REVIEW.md`.

## 1. Delivery pipeline

Business service -> database notification in the business transaction -> commit ->
`notification.created` over WebSocket + Firebase Cloud Messaging (FCM) to the user's
registered devices. A rollback creates no notification and sends nothing.

The inbox does not require Firebase. Push requires an active recipient, at least one
registered token, `push_enabled=true` (the default), and valid backend credentials.
WebSocket failure does not block FCM. Delivery callbacks are best-effort: an external
failure is logged, does not turn a committed action into HTTP 500, and does not stop
later recipients. There is no durable push queue, automatic retry or delivery receipt.
FCM sends run synchronously after commit, in batches of at most 500 tokens.

## 2. Events and recipients

The following events are connected to the shared inbox/WebSocket/FCM pipeline.
All domain events now include `data.event` and `data.organization_id`. Existing
inbox records may lack these keys, so the frontend must keep a fallback.

| Event | Trigger | Recipient / exclusions | Additional data |
| --- | --- | --- | --- |
| `task.assigned` | Create task with assignee; change assignee | New active assignee with sector access; not the actor; not a no-op edit | `task_id`, `sector_id` |
| `task.commented` | Create a task comment | Active assignee with sector access; not the author; respects `app_comments` | `task_id`, `sector_id` |
| `task.status_changed` | Move a task to a different column | Active assignee with sector access; not the actor; respects `app_status` | `task_id`, `sector_id` |
| `chat.mentioned` | Send a message with explicit `mentions` IDs | Active mentioned readers only; excludes sender, outsiders and duplicate IDs | `channel_id`, `message_id` |
| `organization.invited` | Create organization invitation | Existing active account matching invite email (case-insensitive); e-mail is still sent | `invite_id` |
| `organization.invite_accepted` | Successfully accept an invitation | Active inviter, if still an organization member and not the accepting user | `invite_id`, `accepted_by_id` |
| `organization.member_added` | Directly add an existing user | Added active user, excluding actor | `role` |
| `organization.role_changed` | Change a member's role | Affected active user, excluding actor; unchanged role sends nothing | `role` |
| `organization.member_removed` | Remove a member | Removed active user; voluntary departure sends nothing | `role` (previous role) |

Accepting an invitation sends the acceptance event to its inviter, not a duplicate
member-added notification to the invitee. New users without an account receive the
invitation by email only. Acceptance is single-use. Push never contains the raw
invitation token, token hash or acceptance link: those remain in the email flow.

Reordering within a column, renaming a column/changing its category, task edits
without reassignment, ordinary chat messages without mentions, organization creation
or renaming, calendar/report reads, payment webhooks, deadline reminders and weekly
digests do not generate these push events. General/team/sector/direct chat channels
all support mention notifications subject to their existing access rules. Ordinary
chat messages continue to use the separate `chat.message` WebSocket event.

### Preferences

`GET/PATCH /api/v1/users/me/settings/`:

```json
{"push_enabled": true, "app_comments": true, "app_status": true}
```

- `push_enabled=false` disables FCM, including the test endpoint, but preserves the
  inbox and WebSocket notifications.
- `app_comments=false` or `app_status=false` suppresses that category entirely:
  inbox, WebSocket notification and FCM. The business action still succeeds.
- An absent settings record uses the default enabled behavior.
- `email_*` fields do not enable FCM or create new push events. `app_ai` does not
  create an AI notification trigger.

## 3. Frontend API contract

Use the shared authenticated axios client with cookies and `X-CSRFToken`. The
backend supports `GET /api/v1/csrf/` for cookie initialization; refresh expired
sessions through the existing auth flow. Do not add a second `/v1` to the base URL.

| Method/path (relative to `/api/v1`) | Body / response |
| --- | --- |
| `POST /notifications/devices/` | `{token}` -> 204 (registration only, not proof of delivery) |
| `DELETE /notifications/devices/` | JSON body `{token}` -> 204, scoped to current user |
| `POST /notifications/send/` | `{token, title, body?}` -> 200 `{message_id}` |
| `GET /notifications/?unread=true&page=1` | Paginated `{count,next,previous,results}` |
| `POST /notifications/<integer-id>/read/` | 204 |
| `POST /notifications/read-all/` | 204 |

The test requires a token owned by the caller and the global preference enabled.
It does not create an inbox item or emit a WebSocket notification. HTTP 200 means
FCM accepted the message, not that the device displayed it. Keep `message_id` for
diagnosis. Errors: 400 invalid input; 401 session; 403 CSRF, token ownership or
global preference; 503 missing/invalid credentials; 502 provider rejection.

An automatic notification produces this WebSocket payload:

```json
{
  "type": "notification.created",
  "notification": {
    "id": 123,
    "title": "Your task changed status",
    "message": "Deliver feature: Concluído",
    "data": {
      "event": "task.status_changed",
      "organization_id": "organization-uuid",
      "task_id": "task-uuid",
      "sector_id": "sector-uuid"
    },
    "is_read": false,
    "created_at": "2026-10-24T12:00:00Z"
  }
}
```

FCM includes `notification: {title, body}` plus string-valued `data` with the same
domain keys and `notification_id: "123"`. Deduplicate FCM and WebSocket foreground
toasts using the notification ID. HTTP inbox IDs are integers; FCM IDs are strings.

### Required browser behavior

1. Use HTTPS (loopback is allowed for local tests), a supported browser, notification
   permission and an active FCM-initialized service worker. On iOS/iPadOS, Web Push
   requires a supported version and an installed Home Screen web app; request
   permission from a user interaction.
2. Obtain the FCM token with `getToken(messaging, {vapidKey, serviceWorkerRegistration})`
   using the **same active registration** as the PWA worker. Wait for worker activation;
   do not accidentally register a second competing worker.
3. Register the token after login/activation and re-register when the token/account
   changes. Registration transfers a token to the latest authenticated account.
4. Install the `onMessage` listener for the authenticated app session. With an app
   tab visible, show a toast; FCM does not automatically show an OS notification.
5. In the worker, initialize Firebase Messaging. For the existing notification
   payload, FCM handles background display; do not also call `showNotification` for
   the same message. Hide all app windows/tabs to test background display.
6. Unregister this token **before** logout, while credentials and CSRF are valid.
   Do not clear local state on a failed unregister; keep it for retry. Backend
   session revocation alone does not remove device tokens.
7. Distinguish browser registration from the account preference. The current front's
   `pushEnabled` only reflects a local token, not the global `push_enabled` value.

### Frontend changes needed for the added events (not applied here)

- Extend `src/modules/notifications/utils/index.ts` to use `data.event` for types,
  icons and translated titles. Preserve fallback for older records.
- Add translations for the new status/invitation/member titles. The backend messages
  follow the repository's English convention; the current UI will otherwise show
  these new titles in English.
- In `useOpenNotification.ts`, do not unconditionally select `organization_id` for
  `organization.invited` or `organization.member_removed`: the recipient has no
  membership yet, or no longer has it. Refresh organization membership before selecting
  one for other events. Keep removed-member notifications in the inbox.
- Use `/invitations/mine/` to display pending invitations; accepting still requires
  the token from the email link (`POST /invitations/accept/`, `{token}`). An invite ID
  is not an acceptance token.
- Task events carry `organization_id`, `sector_id`, `task_id`; chat events also carry
  `channel_id` and `message_id`. Open the appropriate screen only after checking
  current access. Background clicks intentionally open `/notificacoes` for all events.
- Creating/updating a task sends `assignee` (UUID), not the read-only `assignee_id`.
  Column changes use `POST /tasks/<uuid>/move/` with `{status: "status-uuid"}`.
  Chat mentions must send `mentions: ["user-uuid"]`; typing `@name` in content alone
  does not resolve a recipient on the backend.

## 4. Environment variables

### Backend production (example values; replace hosts and secrets)

```dotenv
DJANGO_SETTINGS_MODULE=app.settings.prod
SECRET_KEY=<private-django-secret>
FIREBASE_CREDENTIALS=/run/secrets/firebase_admin
FRONTEND_URL=https://app.example.com
ALLOWED_HOSTS=app.example.com,api.example.com
CSRF_TRUSTED_ORIGINS=https://app.example.com
USE_HTTPS=True
LOG_LEVEL=INFO
REDIS_URL=redis://redis:6379/0
```

- `FIREBASE_CREDENTIALS` is a **readable file path inside the backend runtime**, not
  JSON contents, an API key, a VAPID key or a path only available on the Docker host.
  Empty disables push. Use a Firebase service-account JSON with valid private key,
  project and FCM sending permissions; enable the FCM HTTP v1 API for the project.
  The process needs outbound HTTPS to Google OAuth/FCM. Restart after rotating it:
  the Firebase app is initialized once per process.
- `FRONTEND_URL` is the browser app's origin, not the API URL and not `/api/v1`.
  HTTPS links become `<FRONTEND_URL>/notificacoes`. Local HTTP still receives push,
  but the HTTPS-only FCM click link is omitted.
- `ALLOWED_HOSTS` contains comma-separated hostnames without scheme. Trusted origins
  contain scheme and port if nonstandard, without trailing slash or spaces. In the
  current dev/prod settings, additional `CSRF_TRUSTED_ORIGINS` also extend the shared
  CORS allowlist. There is no `CORS_ALLOWED_ORIGINS` environment parser.
- Prefer same-origin `/api/v1` and `/ws/` through a reverse proxy so cookies/CSRF
  work consistently. Correct trusted origins alone do not make cross-site cookies
  work. Do not weaken CSRF or CORS globally to work around a URL mismatch.
- Redis/Celery are used by invitation email and other existing features, not by FCM
  delivery. Configure the existing `EMAIL_*` variables and worker for real invitation
  emails. Broker enqueue failures are logged and do not block the separate push.
- Database and encryption settings follow `.env.example`/deployment documentation.
  Do not overwrite an existing `FIELD_ENCRYPTION_KEY` when configuring push.

### Frontend build-time variables

```dotenv
VITE_API_BASE_URL=/api/v1
VITE_API_KEY=<firebase-web-api-key>
VITE_AUTH_DOMAIN=<project-id>.firebaseapp.com
VITE_PROJECT_ID=<same-project-as-service-account>
VITE_STORAGE_BUCKET=<value-from-firebase-web-config>
VITE_MESSAGING_SENDER_ID=<firebase-project-number>
VITE_APP_ID=<firebase-web-app-id>
VITE_VAPID_KEY=<public-web-push-certificate-key>
# Optional for analytics; not required for push:
VITE_MEASUREMENT_ID=
```

Copy Firebase Web App configuration from the console. `VITE_MESSAGING_SENDER_ID` is
the project **number**, not its textual ID. The public VAPID key comes from Firebase
Project settings > Cloud Messaging > Web Push certificates for the same project.
Never put a service-account private key/JSON in `VITE_*`. Vite embeds these variables
in both application and worker bundles at build time: rebuild/redeploy the front
after changes and ensure the new worker activates. Runtime container environment
alone cannot change an already-built frontend.

### Existing Compose deployment

`deployment/compose.prod.yml` mounts the credential secret at
`/run/secrets/firebase_admin`; its host source is
`FIREBASE_CREDENTIALS_FILE=./backend-resenha/firebase-credentials.json`. This variable
belongs to Compose's `.env.prod`, not Django. Firebase `VITE_*` values are also build
args from `.env.prod`. The private JSON is not copied into the image.

The supplied production Compose/Nginx/frontend Dockerfile explicitly use
`https://4000.michalski.app` as the app origin. Compose `environment` overrides the
backend `.env`, and the frontend Dockerfile sets its API URL during build. If deploying
under another hostname, align all these deployment files; merely editing `.env`
will not override those hardcoded entries.

Development Compose uses `/app/firebase-credentials.json` through its bind mount,
not the production secret path. Its Vite dev server has push workers disabled.
Test with a built frontend and verify the worker, rather than assuming `npm run dev`
can receive background notifications.

### Local preview example (without Docker)

```dotenv
# Backend .env, app.settings.dev, SQLite: omit POSTGRES_HOST.
SECRET_KEY=<local-django-secret>
FIREBASE_CREDENTIALS=/absolute/path/to/firebase-credentials.json
FRONTEND_URL=http://127.0.0.1:5173
ALLOWED_HOSTS=127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:5173
```

Build the frontend with `VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1` and the Firebase
variables. Run backend on `127.0.0.1:8000`; preview with
`npm run preview -- --host 127.0.0.1 --port 5173 --strictPort`, then open
`http://127.0.0.1:5173`. Do not mix `localhost` and `127.0.0.1`. If using port 4173,
explicitly add that full origin to `CSRF_TRUSTED_ORIGINS` and align `FRONTEND_URL`.
Preview has no configured WebSocket proxy; this arrangement tests FCM and HTTP,
not realtime WebSocket delivery.

## 5. Verification and troubleshooting

1. In the actual backend runtime, verify the credential path is readable, restart
   after changing credentials, and compare its project ID with the front's compiled
   configuration. This review does not certify a remote server's environment.
2. In the browser, verify HTTPS, granted permission, active `/sw.js`, the expected
   Firebase project and the account preference. Registration must return 204.
3. Use the test endpoint: inspect status, response detail and `message_id`. Observe
   the received `ResenhaCoders` toast separately from the button's success toast.
4. Test background separately with all app tabs hidden and the browser running.
   Check OS notification settings/Do Not Disturb. A visible second app tab can route
   delivery to the foreground listener instead.
5. With two accounts, exercise every row in the event table: assignment, comment,
   move, mention, invitation and acceptance, add/change/remove member. Check inbox,
   then FCM; test self-actions, opt-out, permission loss and repeated no-op actions.

Logs include `notification_id`, error type/code and multicast success/failure counts.
An individual FCM failure does not necessarily raise an exception for the whole batch.
`SenderIdMismatchError` indicates incompatible project/token provenance; tokens are
kept while configuration is corrected. `UnregisteredError` deletes the expired token;
the frontend must obtain and register a current token. Transient failures keep tokens
but do not retry automatically. `LOG_LEVEL=DEBUG` additionally exposes no-device and
opt-out skip reasons. The structured delivery fields do not include device tokens.

The current channel layer is in-memory: use one ASGI web process for realtime
WebSockets. Redis being configured for cache/Celery does not make Channels distributed.
FCM delivery itself does not depend on the WebSocket connection or channel layer.

Automated tests mock Firebase transport and use an isolated database; they validate
event recipients, transaction boundaries, preferences, cleanup and the cookie/CSRF
contract. They do not establish that a physical device displayed a notification.
