# Feature Branches

Every `feat/*` branch is **one commit on top of `dev`** and is independent of
the others. Nothing is merged into `dev` by default: you pull only what the
hackathon project needs.

- Structure, rules and auth flow: [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md)
- Naming and style: [`CONVENTIONS.md`](CONVENTIONS.md)

---

## How to use a branch

```bash
git checkout dev && git pull
git merge feat/payments feat/notifications   # pick what you need
pdm install                       # installs the new dependencies
cp .env.example .env              # then fill the new variables
pdm run manage.py migrate         # creates the new tables
pdm run manage.py test            # every branch ships green
```

**Conflicts when merging several branches** are small and append-only:

| File | Resolution |
|------|------------|
| `app/settings/base.py`, `app/urls.py` | Keep both sides |
| `.env.example`, `core/response_messages.py` | Keep both sides |
| `pdm.lock` | Keep either side, then run `pdm lock` |

---

## Index

| Group | Branch | One-liner |
|-------|--------|-----------|
| Users & access | [`feat/users`](#featusers) | Missing user routes |
| | [`feat/google-auth`](#featgoogle-auth) | Sign in with Google |
| | [`feat/rbac`](#featrbac) | Role-based permission |
| | [`feat/rate-limiting`](#featrate-limiting) | Request limits / brute-force protection |
| API structure | [`feat/generic-model`](#featgeneric-model) | Base model + CRUD in minutes |
| | [`feat/pagination-filters`](#featpagination-filters) | Pagination, filters, search, ordering |
| | [`feat/api-versioning`](#featapi-versioning) | `/api/v1/` |
| | [`feat/admin-config`](#featadmin-config) | Better Django admin |
| Communication | [`feat/emails`](#featemails) | Real SMTP e-mail |
| | [`feat/notifications`](#featnotifications) | In-app notifications |
| | [`feat/websockets`](#featwebsockets) | Real-time push |
| | [`feat/redis-celery`](#featredis-celery) | Background tasks + Redis cache |
| Files & utilities | [`feat/cloudinary-upload`](#featcloudinary-upload) | File upload to Cloudinary |
| | [`feat/qrcode`](#featqrcode) | QR code PNG |
| | [`feat/encryption`](#featencryption) | Encrypted model field |
| Payments & AI | [`feat/payments`](#featpayments) | Mercado Pago checkout |
| | [`feat/ai`](#featai) | Gemini-powered endpoint |
| | [`feat/data-libs`](#featdata-libs) | pandas, scikit-learn, OpenCV |
| Safety & infra | [`feat/idempotency`](#featidempotency) | Safe retries / no double charge |
| | [`feat/audit-logs`](#feataudit-logs) | Who changed what |
| | [`feat/docker`](#featdocker) | Docker + Postgres + production settings |

---

## Users & access

### `feat/users`

**What it does:** the template already had views to get one user and to update
your own profile, but no route pointed to them. This branch adds the routes and
fixes the id type (users have UUID primary keys).

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /api/v1/users/<uuid>/` | logged | One user. Non-staff only see active users |
| `PATCH /api/v1/users/me/update/` | logged | Update own `name` (e-mail/password are rejected) |

**Files:** `app/urls.py`, `core/views/user.py`, `core/services/user.py`
**Env vars:** none

---

### `feat/google-auth`

**What it does:** "Sign in with Google". The frontend gets an ID token from
Google Identity Services and sends it to the API, which verifies it with Google
and logs the user in with the **same cookies** as the e-mail login.

**Rules**
- First login creates the user (active, name from Google, no password).
- The Google e-mail must be verified.
- A user who started the e-mail registration but never finished is activated
  (Google proves the e-mail).
- A **deactivated** user (inactive and has logged in before) is rejected (403).

**Frontend**
```js
// callback of the Google button (Google Identity Services)
await fetch("/api/v1/login/google/", {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ credential: response.credential }),
});
```

**Setup:** create an OAuth Client ID (Web) in Google Cloud Console, add the
frontend origin to "Authorized JavaScript origins".

**Files:** `core/services/google_auth.py`, `core/serializers/google_auth.py`,
`core/views/google_auth.py`, `core/tests/test_google_auth.py`.
Refactor: `AuthService.create_session()` (shared by every login method) and
`set_auth_cookies()` in `core/utils/cookies.py`.
**Env vars:** `GOOGLE_CLIENT_ID`

---

### `feat/rbac`

**What it does:** a `HasRole` permission class. Roles are plain **Django Groups**,
so you create them and assign users in `/admin/` (no extra tables).

```python
from rest_framework.permissions import IsAuthenticated
from core.permissions.has_role import HasRole


class ReportView(APIView):
    permission_classes = [IsAuthenticated, HasRole]
    required_roles = ["admin", "manager"]  # any of them grants access
```

**Rules:** superusers always pass; anonymous users never pass.
For per-model add/change/delete rules use DRF's built-in `DjangoModelPermissions`.

**Files:** `core/permissions/has_role.py`, `core/tests/test_has_role.py`
**Env vars:** none

---

### `feat/rate-limiting`

**What it does:** DRF throttling, active on every view with no code changes.

| Scope | Limit | Applies to |
|-------|-------|------------|
| `anon` | 100/hour | Not logged in |
| `user` | 1000/hour | Logged in |
| `auth` | 10/minute | Login, registration, password reset, e-mail change |

Over the limit the API answers **429** with a `Retry-After` header.
Use the strict scope on any sensitive view: `throttle_scope = "auth"`.

**Note:** limits are stored in the cache. With more than one server process,
use Redis (`feat/redis-celery`), otherwise each process counts separately.

**Files:** `app/settings/base.py`, auth views
**Env vars:** none

---

## API structure

### `feat/generic-model`

**What it does:** two building blocks to create a full CRUD in minutes.

- `BaseModel` (abstract): UUID `id`, `owner`, `is_active`, `created_at`,
  `updated_at`, `soft_delete()`.
- `OwnedModelViewSet`: list/create/retrieve/update/delete **scoped to the logged
  user**; create fills `owner`; delete is a soft delete.

```python
# core/models/product.py
class Product(BaseModel):
    name = models.CharField(max_length=255)
    extra = models.JSONField(default=dict, blank=True)  # free-form fields


# core/serializers/product.py
class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ("id", "name", "extra", "created_at")


# core/views/product.py
class ProductViewSet(OwnedModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer


# urls
router = DefaultRouter()
router.register("products", ProductViewSet)
urlpatterns += router.urls
```

**Files:** `core/models/base.py`, `core/views/base.py`
**Env vars:** none

---

### `feat/pagination-filters`

**What it does:** global pagination plus filter/search/ordering backends.
`UserListView` already uses them as the example.

```
GET /api/v1/users/list/?page=2
GET /api/v1/users/list/?search=maria&ordering=-created_at&is_active=true
```

Paginated responses look like:
```json
{ "count": 42, "next": "...?page=3", "previous": "...?page=1", "results": [ ... ] }
```

Enable it on your own `ListAPIView` / `ViewSet`:
```python
filterset_fields = ["status"]  # ?status=open
search_fields = ["title", "owner__email"]  # ?search=
ordering_fields = ["created_at"]  # ?ordering=-created_at
```

**Page size:** 20 (`PAGE_SIZE` in settings). Plain `APIView`s are not paginated.
**Files:** `app/settings/base.py`, `core/views/user.py`
**Dependency:** `django-filter`
**Env vars:** none

---

### `feat/api-versioning`

**What it does:** every API route moves from `/api/v1/...` to `/api/v1/...`
(`NamespaceVersioning`). `request.version` is `"v1"` inside views.

To add a v2 later: include the new routes with `namespace="v2"` in `app/urls.py`
and add `"v2"` to `ALLOWED_VERSIONS`.

**Heads-up:** the frontend base URL changes to `/api/v1/`. Admin and docs stay
at `/admin/` and `/api/docs/`.
**Files:** `app/settings/base.py`, `app/urls.py`
**Env vars:** none

---

### `feat/admin-config`

**What it does:** improves `/admin/` only.

- Users: filters by active/staff/superuser/groups/date.
- One-time codes: filters by used/created/expires.
- New **User sessions** screen: device, IP, active, last activity; searchable;
  read-only (sessions can be deactivated by unchecking "active").

**Files:** `core/admin.py`
**Env vars:** none

---

## Communication

### `feat/emails`

**What it does:** configures real SMTP sending via Django 6.1 `MAILERS`
(the old `EMAIL_*` settings are deprecated). In dev, `dev.py` uses this SMTP mailer when
`EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD` are set; without them e-mails are printed to the terminal.

**Gmail:** enable 2FA and create an **App password**; use it as
`EMAIL_HOST_PASSWORD`.

**Files:** `app/settings/base.py`, `core/utils/email_token_sender.py`
**Env vars:** `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
`EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL`

---

### `feat/notifications`

**What it does:** stores notifications per user and lets the frontend list them
and mark them as read. If `FIREBASE_CREDENTIALS` is set, every notification is
also sent as a push (Firebase Cloud Messaging) to the user's registered devices,
unless their global push preference is disabled. Delivery runs after commit.

**Backend (from any service)**
```python
from core.modules.notifications.services.notification import NotificationService

NotificationService.notify(
    user, "Payment approved", "Your ticket is ready", data={"payment_id": str(p.id)}
)
```

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/notifications/` | My notifications (paginated if `feat/pagination-filters` is merged) |
| `GET /api/v1/notifications/?unread=true` | Only unread |
| `POST /api/v1/notifications/<id>/read/` | Mark one as read (204) |
| `POST /api/v1/notifications/read-all/` | Mark all as read (204) |
| `POST /api/v1/notifications/send/` | Test push to my registered token `{"token", "title", "body"}` → `{"message_id"}` (403 if not owned or opted out, 503 if not configured, 502 if FCM fails) |
| `POST /api/v1/notifications/devices/` | Register this browser's FCM token `{"token": "..."}` (204) |
| `DELETE /api/v1/notifications/devices/` | Remove it on logout `{"token": "..."}` (204) |

**Push setup**
1. Firebase Console → Project settings → Service accounts → Generate new private key.
2. Save the JSON in the backend folder as `firebase-credentials.json` (git-ignored) and set
   `FIREBASE_CREDENTIALS=firebase-credentials.json` in `.env`.
3. Frontend: `getToken(messaging, { vapidKey })` with the web config, then
   `POST /api/v1/notifications/devices/`. The frontend PWA worker (`/sw.js`)
   receives pushes while the tab is closed.

Push is best-effort: if FCM fails the notification is still saved, and tokens
FCM reports as dead are deleted.

**Real time:** the shared service emits `notification.created` to the user's `/ws/`
connections after commit. See [the integration assessment](NOTIFICATIONS_INTEGRATION.md)
for the current frontend flow, infrastructure requirements and remaining work.

**Files:** the `core/modules/notifications/` module (models, serializers, services, views, admin,
urls, tests), plus a migration in `core/migrations/` and one line in `app/urls.py`
**Env vars:** `FIREBASE_CREDENTIALS` (optional), `FRONTEND_URL` (HTTPS push click destination)

---

### `feat/websockets`

**What it does:** Django Channels. One socket per logged user at `/ws/`; the
backend can push JSON to every open tab/device of a user.

**Auth:** the handshake uses the same `access_token` cookie and the same rules
as the REST API (valid JWT + active session). Anonymous connections are closed
with code **4401**.

**Frontend**
```js
const ws = new WebSocket("ws://localhost:8000/ws/");   // wss:// in production
ws.onmessage = (event) => console.log(JSON.parse(event.data));
```

**Backend (sync code: views, services, Celery tasks)**
```python
from core.websockets.consumers import send_to_user

send_to_user(user.pk, {"type": "order_updated", "order_id": 12})
```

**Extending:** for chat-like flows (client → server), override `receive_json`
in `UserConsumer` or add a new consumer in `core/websockets/`.

**Notes**
- `daphne` is first in `INSTALLED_APPS`, so `runserver` serves HTTP + WebSocket.
- `CHANNEL_LAYERS` is in-memory and the Compose web service runs one Daphne
  process. For multiple web processes, use `channels_redis` with `REDIS_URL`.

**Files:** `core/websockets/{auth,consumers,routing}.py`, `app/asgi.py`,
`core/authenticate.py` (`is_session_active` extracted), `core/tests/test_websockets.py`
**Env vars:** none

---

### `feat/redis-celery`

**What it does:** Celery for background jobs and Redis as cache + broker.

```python
from core.tasks.email import send_email_task

send_email_task.delay(email, code, "Verify your e-mail")  # retries 3x with backoff
```

**Running in production**
```bash
celery -A app worker -l info
```

**Dev:** works **without Redis**: tasks run inline (`CELERY_TASK_ALWAYS_EAGER`)
and the cache is in memory. Delete both lines in `dev.py` to test the real setup.

**Adding a task:** create `core/tasks/<subject>.py` with `@shared_task` and import
it in `core/tasks/__init__.py` (Celery discovers `core.tasks`). Keep business
rules in services; tasks only call them.

**Files:** `app/celery.py`, `app/__init__.py`, `core/tasks/`, settings
**Env vars:** `REDIS_URL`

---

## Files & utilities

### `feat/cloudinary-upload`

**What it does:** uploads any file (image, video, PDF...) to Cloudinary and
returns its public URL. Files are stored in the folder `users/<user_id>/`.

```
POST /api/v1/uploads/       multipart/form-data, field "file" (max 10 MB)
→ 201 {"url": "https://res.cloudinary.com/...", "public_id": "users/<id>/abc"}
```

**Backend reuse**
```python
from core.modules.uploads.services.upload import UploadService

result = UploadService.upload(file, folder="products")
UploadService.delete(result["public_id"])
```

Store `url` (and `public_id` if you need to delete) in your model.

**Files:** self-contained `core/modules/uploads/` module (`services/upload.py`, `serializers/upload.py`, `views/upload.py`, `urls.py`, `response_messages.py`); registered in `app/urls.py`
**Env vars:** `CLOUDINARY_URL` (copy it from the Cloudinary dashboard)

---

### `feat/qrcode`

**What it does:** generates QR codes as PNG.

```html
<img src="/api/v1/qrcode/?data=TICKET-123" />  <!-- logged users, data up to 1000 chars -->
```

**Backend reuse** (e-mail attachment, upload to Cloudinary...)
```python
from core.utils.qrcode import make_qrcode_png

png_bytes = make_qrcode_png("https://my-app.com/tickets/123")
```

**Files:** `core/utils/qrcode.py`, `core/views/qrcode.py`
**Dependency:** `qrcode[pil]`
**Env vars:** none

---

### `feat/encryption`

**What it does:** `EncryptedTextField`, a model field encrypted at rest (Fernet /
AES). Your code reads and writes plain text; the database stores ciphertext.

```python
from core.models.fields import EncryptedTextField


class Profile(models.Model):
    cpf = EncryptedTextField()
```

**Generate the key**
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Limits:** the ciphertext changes on every save, so the column **cannot be
filtered, ordered or unique**. Losing `FIELD_ENCRYPTION_KEY` makes the data
unrecoverable — store it safely.

**Files:** `core/models/fields.py`, `core/tests/test_encrypted_field.py`
**Env vars:** `FIELD_ENCRYPTION_KEY`

---

## Payments & AI

### `feat/payments`

**What it does:** Mercado Pago **Checkout Pro** in its own `core/modules/payments` module.

**Flow**
1. Frontend calls `POST /api/v1/payments/` with `{"title": "Ticket", "amount": "10.00"}`.
2. API creates a local `Payment` (status `pending`) and returns `checkout_url`.
3. Frontend redirects the user to `checkout_url` and the user pays.
4. Mercado Pago calls `POST /api/v1/payments/webhook/`; the API fetches the payment
   **from the Mercado Pago API** (never trusts the request body) and updates
   the status (`approved`, `rejected`, `refunded`...).
5. If `FRONTEND_URL` is set, the user comes back to
   `FRONTEND_URL/payments/success|failure|pending`.

| Endpoint | Auth | Description |
|----------|------|-------------|
| `POST /api/v1/payments/` | logged | Create checkout → `{payment_id, checkout_url}` |
| `GET /api/v1/payments/` | logged | My payments |
| `POST /api/v1/payments/webhook/` | public | Mercado Pago notifications |

**Important**
- In a real flow, compute `amount` on the server (from your product/order),
  never trust the client value.
- The webhook needs a **public URL**. Locally use a tunnel (ngrok, cloudflared).
- Use test credentials from the Mercado Pago developer panel during the hackathon.
- Currency is BRL. Users with payments cannot be deleted (`PROTECT`).

**Files:** `core/modules/payments/{models,serializers,services,views}/payment.py`,
`core/modules/payments/{urls,admin,response_messages}.py`, migration, `core/modules/payments/tests/test_payment.py`
**Env vars:** `MP_ACCESS_TOKEN`, `FRONTEND_URL`

---

### `feat/ai`

**What it does:** sends prompts to Gemini through the official `google-genai` SDK.

```
POST /api/v1/ai/ask/   {"prompt": "Summarize this text: ..."}
→ 200 {"answer": "..."}
```

**Backend reuse** (summaries, classification, extraction, chat replies...)
```python
from core.modules.ai.services.ask import AIService

answer = AIService.ask(
    text,
    system="You classify support tickets as LOW, MEDIUM or HIGH. Answer with one word.",
)
```

**Behavior**
- Uses `gemini-flash-lite-latest` for concise, low-latency responses.
- Empty or blocked responses return 400; provider rate limits return 429.
- Rate limit from the provider → 429; other provider errors → 500 (logged).

**Files:** self-contained `core/modules/ai/` module (`services/ask.py`, `serializers/ask.py`, `views/ask.py`, `urls.py`, `response_messages.py`, `tests/test_ask.py`); registered in `app/urls.py`
**Env vars:** `GEMINI_API_KEY`

---

### `feat/data-libs`

**What it does:** only adds dependencies, no code.

| Library | Use it for |
|---------|------------|
| `pandas` | Reading CSV/Excel, reports, aggregations |
| `scikit-learn` | Simple ML: classification, regression, clustering |
| `opencv-python-headless` | Image processing (headless = no GUI, works in Docker) |

`datetime` is part of Python's standard library, nothing to install.
Put the code that uses them in a service (e.g. `core/services/report.py`).

**Files:** `pyproject.toml`, `pdm.lock`

---

## Safety & infra

### `feat/idempotency`

**What it does:** protects write requests against duplicates (double click on
"pay", retry after a timeout). Requests **without** the header are untouched.

```js
const key = crypto.randomUUID();     // one key per user action, reused on retries
await fetch("/api/v1/payments/", {
  method: "POST",
  credentials: "include",
  headers: { "Idempotency-Key": key, "X-CSRFToken": csrf, "Content-Type": "application/json" },
  body: JSON.stringify(data),
});
```

**Rules**
- Same key + same user + same method/path within **24h** → the first response is
  replayed (header `Idempotent-Replayed: true`); the action does not run again.
- Same key while the first request is still running → **409**.
- 5xx responses are not stored, so the client can retry.
- Don't send the header on login: replayed responses do not carry cookies.

**Note:** with more than one server process, use Redis (`feat/redis-celery`).
**Files:** `core/middleware/idempotency.py`, `core/tests/test_idempotency.py`
**Env vars:** none

---

### `feat/audit-logs`

**What it does:** `django-auditlog` records every create/update/delete of the
tracked models with **who** did it (the JWT user), **when**, the IP and the
changed fields. View it in `/admin/` → "Log entries". Also configures console
logging for the whole project.

**Tracked by default:** `core.User` (password and last_login excluded) and
`core.UserSession`. To track more:
```python
AUDITLOG_INCLUDE_TRACKING_MODELS = (
    ...,
    "payments.Payment",
)
```

**Why a custom middleware:** DRF authenticates the JWT inside the view, after
Django middlewares run, so the stock auditlog middleware would record no actor.
`core/middleware/audit.py` resolves the actor lazily.

**Files:** `core/middleware/audit.py`, settings, `core/tests/test_audit_log.py`
**Env vars:** `LOG_LEVEL` (default `INFO`)

---

### `feat/docker`

**What it does:** containerizes the API and makes `prod.py` usable.

```bash
cp .env.example .env      # set SECRET_KEY
docker compose up --build # API on http://localhost:8000
docker compose exec web python manage.py createsuperuser
```

**What's inside**
- `Dockerfile`: Python 3.14 slim, PDM resolves and installs the project lock,
  runs `collectstatic` as a non-root user, and serves HTTP/WebSockets with Daphne.
- `docker-compose.yml`: `migrate`, `web`, `worker`, Postgres 17, and Redis 7;
  the database and Redis have health checks, and Postgres uses a persistent volume.
- `prod.py`: Postgres from env, `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` from env,
  whitenoise for static files, HTTPS security settings (HSTS, secure cookies,
  SSL redirect). `SECRET_KEY` is required (fails fast if missing).

**`USE_HTTPS`:** `True` in real deploys. Compose sets it to `False` so login
cookies work over plain `http://localhost`.

**Not verified here:** the Docker image and Compose stack were not started.

**Files:** `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `app/settings/prod.py`
**Dependencies:** `psycopg[binary]`, `channels[daphne]`, `whitenoise`, `celery[redis]`
**Env vars:** `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `USE_HTTPS`,
`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`

---

## Recipes (combining branches)

| Goal | Merge | Glue code |
|------|-------|-----------|
| Real-time notifications | `notifications` + `websockets` | In `NotificationService.notify`, call `send_to_user(user.pk, NotificationSerializer(n).data)` |
| Notify when paid | `payments` + `notifications` | In `PaymentService.sync_from_provider`, notify the user when status becomes `approved` |
| Ticket with QR code | `payments` + `qrcode` (+ `cloudinary-upload`) | After approval, `make_qrcode_png(str(payment.id))` and upload or e-mail it |
| Async e-mails | `redis-celery` (+ `emails`) | `send_email_token(...)` queues delivery after the token transaction commits |
| AI over your data | `ai` + `data-libs` | Summarize a pandas DataFrame with `AIService.ask(df.describe().to_string())` |
| Production-ready | `docker` + `redis-celery` + `rate-limiting` + `idempotency` | Point `REDIS_URL` to a Redis service in compose |
