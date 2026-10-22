# Project Guide

Django REST backend template for the hackathon: e-mail/JWT authentication ready,
plus optional feature branches you merge only when the project needs them.

Read this first, then [`CONVENTIONS.md`](CONVENTIONS.md) for naming and style,
[`TEAM_WORKFLOW.md`](TEAM_WORKFLOW.md) for how we split work and review, and
[`FEATURE_BRANCHES.md`](FEATURE_BRANCHES.md) for the optional features.

---

## 1. Stack

| Piece | Choice |
|-------|--------|
| Language | Python 3.14 |
| Framework | Django 6.1 + Django REST Framework |
| Auth | `djangorestframework-simplejwt`, tokens in **HttpOnly cookies** |
| API docs | `drf-spectacular` (Swagger at `/api/docs/urls/`) |
| Package manager | PDM (`pdm.lock` is the source of truth) |
| Lint / format | Ruff (pre-commit + GitHub Actions) |
| DB | SQLite in dev, PostgreSQL in prod (`feat/docker`) |

## 2. Running locally

```bash
pdm install                     # creates .venv and installs everything
cp .env.example .env            # fill SECRET_KEY at least
pdm run manage.py migrate
pdm run manage.py createsuperuser
pdm run dev                     # runserver with app.settings.dev
pdm run manage.py test          # run the test suite
```

E-mails are printed to the terminal in dev (`MAILERS` console backend in `dev.py`).

## 3. Folder structure

```
app/                     # project config (not an app)
  settings/
    base.py              # shared by every environment
    dev.py               # DEBUG, SQLite, console e-mail
    prod.py              # production overrides (env vars only)
  urls.py                # root routes: /admin/, /api/docs/, /api/v1/
  asgi.py / wsgi.py      # default to app.settings.prod
core/                    # users, auth and everything shared
  models/                # one model (or family) per file
  serializers/           # input validation + output shape
  services/              # business rules
  views/                 # HTTP layer
  permissions/           # DRF permission classes
  utils/                 # small stateless helpers (cookies, e-mail sender)
  authenticate.py        # CustomAuthentication (JWT cookie + session check)
  response_messages.py   # every user-facing message (MSG_*)
  spectacular_serializers.py  # response schemas used only by the API docs
  admin.py
  migrations/
tests/                   # legacy root test package (keep new tests in <app>/tests/)
docs/                    # this guide, conventions, team workflow, feature branches
.github/                 # CI (ruff.yml), PR template, issue template
AGENTS.md / CLAUDE.md    # rules for AI agents working in the repo
```

### What goes where (rules)

| Folder | Put here | Never put here |
|--------|----------|----------------|
| `models/` | Fields, `Meta`, `__str__`, tiny state helpers (`soft_delete`, `mark_used`) | Requests, e-mails, external APIs |
| `serializers/` | Field validation (`validate_<field>`), output fields listed explicitly | Database writes for business flows (`fields = "__all__"` is forbidden) |
| `services/` | Business rules, transactions, calls to external providers; raise DRF exceptions | `request` objects, `Response` |
| `views/` | Read request → validate with serializer → call **one** service → return `Response`; `@extend_schema` on every method | Business rules, ORM queries beyond a simple `get_queryset` |
| `permissions/` | Who may call a view (`IsUserOwner`, `HasRole`) | Business validation |
| `utils/` | Pure helpers reused by several services | Anything that needs a model's business rules |
| `middleware/` | Cross-cutting request/response behavior (idempotency, audit) | Feature logic |
| `tasks/` | Celery tasks, thin wrappers that call services/utils | Business rules (keep them in services) |
| `response_messages.py` | `MSG_<MEANING> = _("...")` for every message the client sees | Hard-coded strings in views/services |
| `<app>/tests/` | `test_<subject>.py`, one file per subject | — |

**Self-contained features** (payments, chat, marketplace...) get their **own app**
with the same layered folders and an `urls.py` with `app_name`, so their
migrations never collide with `core`. See `payments/` in `feat/payments`.

### Adding a feature: checklist

1. Branch `feat/<kebab-name>` from `dev`; open the PR into `dev` (never commit to `main`).
2. Model in `models/<subject>.py` → `makemigrations`.
3. Serializer(s) in `serializers/<subject>.py`.
4. Service in `services/<subject>.py` (the only place with rules).
5. View in `views/<subject>.py` with `@extend_schema`.
6. Route in `app/urls.py` (core) or `<app>/urls.py` (feature app), kebab-case.
7. Messages in `response_messages.py`; env vars in `.env.example`.
8. Admin registration with `list_display`, `list_filter`, `search_fields`.
9. A test for any non-trivial logic; `ruff check . && ruff format .`.

## 4. Authentication (how it works)

- **Login** (`POST /api/v1/login/`) sets two HttpOnly cookies: `access_token`
  (15 min) and `refresh_token` (1 day), plus the `csrftoken` cookie.
- Every login creates/updates a **`UserSession`** row (device, IP, JTIs).
  `CustomAuthentication` accepts a token **only if its session is active**, so
  logout / revoking a session invalidates it immediately, not only at expiry.
- **Refresh** (`POST /api/v1/refresh/`) rotates both tokens and blacklists the old
  refresh token.
- **CSRF**: cookie-authenticated writes (`POST/PUT/PATCH/DELETE`) must send the
  `X-CSRFToken` header with the `csrftoken` cookie value.
- Public views set `authentication_classes = []` and `permission_classes = [AllowAny]`.
  On those, DRF answers failed auth with **403**, not 401.
- Frontend must send requests with credentials (`fetch(..., {credentials: "include"})`).

### Session endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/sessions/` | Active sessions, flags the current one |
| `DELETE /api/v1/sessions/<id>/` | Revoke another device (not the current one) |
| `POST /api/v1/me/revoke-sessions/` | Log out everywhere |
| `POST /api/v1/me/logout/` | Log out this device |

## 5. Business rules

### Users
- Login is by **e-mail** (`USERNAME_FIELD = "email"`), primary key is a **UUID**.
- Users are **never deleted**: `is_active = False` (soft delete / deactivation).
- Non-staff users only see **active** users; staff/superusers see everyone.
- `PATCH` on own profile only changes `name`; e-mail and password have their own flows.
- Passwords: min. 9 characters + Django's similarity/common/numeric validators.

### One-time code flows (registration, password reset, e-mail change)

All three follow **request → verify → confirm**:

1. **request** — generates a 6-digit code, stores only its **hash**, e-mails it.
   A new request replaces the previous code.
2. **verify** — optional check so the UI can validate the code before the last step.
3. **confirm** — validates the code again and applies the change; code is marked used.

Rules shared by every code (`OneTimeCode`): expires in **15 minutes**, burns after
**5 wrong attempts**, single use.

- **Registration** creates the user **inactive** at step 1; confirm sets name,
  password and activates it.
- **Password reset** always answers "code sent" even if the e-mail does not exist
  (no user enumeration).
- **E-mail change** is authenticated, sends the code to the **new** address and
  requires the **current password** on confirm.

## 6. Settings & environment

- `manage.py` uses `app.settings.dev`; `wsgi.py`/`asgi.py` default to `app.settings.prod`.
- Secrets only via environment variables, loaded from `.env` (`python-dotenv`).
  Every new variable is documented in `.env.example`.
- Mail uses Django 6.1 **`MAILERS`** (`EMAIL_*` settings are deprecated).

## 7. Feature branches

Full usage docs for each branch: [`FEATURE_BRANCHES.md`](FEATURE_BRANCHES.md).

Each branch is **one commit on top of `dev`**, independent of the
others. Merge only what the hackathon needs:

```bash
git checkout dev && git pull
git merge feat/payments feat/notifications
pdm install && pdm run manage.py migrate
```

| Branch | Adds | Env vars |
|--------|------|----------|
| `feat/users` | Routes for user detail and self-update | — |
| `feat/admin-config` | Admin filters/search, session admin | — |
| `feat/rate-limiting` | DRF throttling, `auth` scope 10/min on login and code flows | — |
| `feat/pagination-filters` | Pagination (20), `django-filter`, search, ordering | — |
| `feat/api-versioning` | Routes under `/api/v1/` (`NamespaceVersioning`) | — |
| `feat/emails` | SMTP mailer from env | `EMAIL_*`, `DEFAULT_FROM_EMAIL` |
| `feat/rbac` | `HasRole` permission (roles = Django Groups) | — |
| `feat/generic-model` | `BaseModel` (UUID, timestamps, soft delete, owner) + `OwnedModelViewSet` | — |
| `feat/qrcode` | `GET /api/v1/qrcode/?data=` → PNG, `make_qrcode_png()` | — |
| `feat/cloudinary-upload` | `POST /api/v1/uploads/`, `UploadService` | `CLOUDINARY_URL` |
| `feat/redis-celery` | Celery + Redis cache/broker, `send_email_task` | `REDIS_URL` |
| `feat/encryption` | `EncryptedTextField` (Fernet) | `FIELD_ENCRYPTION_KEY` |
| `feat/idempotency` | `Idempotency-Key` header replays the first response | — |
| `feat/audit-logs` | `django-auditlog` (who changed what) + console `LOGGING` | `LOG_LEVEL` |
| `feat/notifications` | In-app notifications, `NotificationService.notify()` | — |
| `feat/websockets` | Channels at `/ws/`, JWT cookie auth, `send_to_user()` | — |
| `feat/google-auth` | `POST /api/v1/login/google/` (Google ID token) | `GOOGLE_CLIENT_ID` |
| `feat/payments` | `payments` app: Mercado Pago checkout + webhook | `MP_ACCESS_TOKEN`, `FRONTEND_URL` |
| `feat/ai` | `POST /api/v1/ai/ask/` with Gemini, `AIService.ask()` | `GEMINI_API_KEY` |
| `feat/data-libs` | pandas, scikit-learn, opencv-headless | — |
| `feat/docker` | Dockerfile and Compose (Postgres, Redis, web, worker), ASGI server, production settings | `POSTGRES_*`, `ALLOWED_HOSTS`, `USE_HTTPS` |

### Merging several branches

Expect small, append-only conflicts in: `app/settings/base.py`, `app/urls.py`,
`.env.example`, `core/response_messages.py` → **keep both sides**.
For `pdm.lock` conflicts, keep either side and run `pdm lock` again.

### Good combinations

- **Real-time notifications**: `feat/notifications` + `feat/websockets` → call
  `send_to_user(user.pk, {...})` inside `NotificationService.notify`.
- **Payments that notify**: `feat/payments` + `feat/notifications` → notify in
  `PaymentService.sync_from_provider` when status becomes `approved`.
- **Production**: Docker Compose starts Postgres, Redis, migrations, the ASGI web
  process, and a Celery worker. The in-memory channel layer supports the single
  web process; use `channels_redis` when scaling to multiple web processes.
- **Async e-mails**: `send_email_token(...)` queues Celery delivery after its
  database transaction commits; dev runs the task eagerly.

## 8. Known issues (fix before the demo)

| Issue | Where | Fix |
|-------|-------|-----|
| Token refresh crashes (500): `UserSession` has no `updated_at` | `SessionService.update_session_jtis` | Use `"last_activity"` in `update_fields` |
| Login response body also returns the tokens, defeating HttpOnly cookies | `LoginView` | Remove `"data": token_data` |
| `prod.py` on `main` has empty `DATABASES` / `ALLOWED_HOSTS` | `app/settings/prod.py` | Merge `feat/docker` |
| `"ATOMIC_REQUESTS "` has a trailing space, so it is ignored | `dev.py` | Remove the space |
| Models in `core/models/` beyond `User` are registered only because `admin.py` imports them | `core/models/__init__.py` | Import new models there if a worker/script needs them |
