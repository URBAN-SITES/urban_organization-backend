# Inceptum API

Django 6.1 + Django REST Framework backend of Inceptum: organizations, projects
(`Sector` in the code) with a Kanban board, tasks, chat, meetings with recordings,
meeting transcription and summaries, GitHub integration, payments and notifications.
Authentication uses e-mail/JWT in HttpOnly cookies, plus Google and GitHub sign-in.

## Documentation

| Doc | What's in it |
|-----|--------------|
| [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md) | Stack, folder structure, auth, business rules, known issues |
| [`docs/PRODUCT_SCOPE.md`](docs/PRODUCT_SCOPE.md) | Product goal, priorities and data rules |
| [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) | Branches, commits, naming and code style |
| [`docs/TEAM_WORKFLOW.md`](docs/TEAM_WORKFLOW.md) | Issues, PRs, collisions, splitting large tasks |
| [`docs/GITHUB.md`](docs/GITHUB.md) | GitHub App setup and permissions |
| [`docs/REUNIOES.md`](docs/REUNIOES.md) | Meetings with LiveKit, recordings and storage |
| [`docs/LIGACOES.md`](docs/LIGACOES.md) | Voice/video calls in chat (WebRTC) and message reactions |
| [`docs/IA-REUNIOES.md`](docs/IA-REUNIOES.md) | Transcription (faster-whisper) and summaries (Ollama) on our own server |
| [`docs/PUSH_NOTIFICATIONS.md`](docs/PUSH_NOTIFICATIONS.md) | Firebase Cloud Messaging setup |
| [`docs/RELATORIO-RECONSTRUCAO.md`](docs/RELATORIO-RECONSTRUCAO.md) | Post-hackathon rebuild report (phases 0 to 6) |
| [`AGENTS.md`](AGENTS.md) | Rules for AI agents working in this repo |

Interactive API docs: `/api/docs/urls/` (Swagger) and `/api/docs/schema/` (OpenAPI).

## Running locally

Requirements: Python 3.14, [PDM](https://pdm-project.org), and Redis for the
production-like setup. Everything else is optional and only turns a feature on.

```bash
pdm install                       # creates .venv from pdm.lock
cp .env.example .env              # see "Environment variables" below
pdm run manage.py migrate
pdm run manage.py createsuperuser # optional, for /admin/
pdm run dev                       # runserver (daphne: HTTP + WebSocket) on :8000
```

- **Database.** With `POSTGRES_HOST` empty the dev settings use SQLite
  (`db.sqlite3`). Set `POSTGRES_HOST` (and `POSTGRES_PASSWORD`) to use PostgreSQL.
- **Background jobs.** In dev, Celery runs tasks inline (`CELERY_TASK_ALWAYS_EAGER`),
  so no worker is needed. In production run the worker with
  `celery -A app worker --loglevel=info` next to the web process, both pointing at
  the same `REDIS_URL`.
- **Realtime.** Dev uses an in-memory channel layer (one process). Production uses
  Redis (`channels_redis`) when `REDIS_URL` is set, so the worker can push chat and
  notification events to the web process.
- **E-mail.** Without `EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`, codes are printed to the
  terminal.
- **Meeting AI (optional).** Needs `ffmpeg`, [Ollama](https://ollama.com) with the model
  in `OLLAMA_MODEL` pulled, and `MEETING_AI_ENABLED=true`. faster-whisper downloads its
  model on first use. See `docs/IA-REUNIOES.md`.

The frontend runs separately (`frontend-resenha`, `npm run dev` on :5173) and talks to
this API through Vite's `/api` proxy.

### Checks

```bash
export SECRET_KEY=ci-only FIELD_ENCRYPTION_KEY=AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=
pdm run ruff check . && pdm run ruff format --check .
pdm run manage.py makemigrations --check --dry-run
pdm run manage.py test
```

`core/tests/test_cross_tenant.py` calls every route as a user of another organization
and `core/tests/test_security_hardening.py` calls every private route without a session;
both fail when a new endpoint forgets its permission check.

## Environment variables

Secrets live only in `.env` (never committed). `.env.example` lists every key.

| Variable | Required | What it does |
|----------|----------|--------------|
| `SECRET_KEY` | yes | Django secret |
| `FIELD_ENCRYPTION_KEY` | yes | Base64 32-byte key that encrypts stored tokens (Google, GitHub) |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `USE_HTTPS` | prod | Hosts, trusted origins and secure cookies |
| `FRONTEND_URL` | yes | Browser app origin, used in e-mails, redirects and push links |
| `LOG_LEVEL` | no | Defaults to `INFO` |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` | prod | PostgreSQL; empty host means SQLite in dev |
| `REDIS_URL` | prod | Celery broker and the realtime channel layer |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL` | prod | SMTP for one-time codes and invitations |
| `CLOUDINARY_URL` | optional | File and image uploads; without it files are kept in the database and served by the API |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI` | optional | Google sign-in, Calendar and Drive |
| `FIREBASE_CREDENTIALS` | optional | Path to the Firebase service-account JSON; empty disables push |
| `MP_ACCESS_TOKEN` | optional | Mercado Pago (task charges) |
| `GEMINI_API_KEY`, `AI_ASSISTANT_MODEL`, `AI_ANALYSIS_*` | optional | AI assistant and file analysis (free for every signed-in user, 60 calls/hour) |
| `GITHUB_APP_ID`, `GITHUB_APP_SLUG`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_APP_PRIVATE_KEY`, `GITHUB_WEBHOOK_SECRET`, `GITHUB_OAUTH_REDIRECT_URI` | optional | GitHub sign-in and repository integration (`docs/GITHUB.md`) |
| `LIVEKIT_URL`, `LIVEKIT_API_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | optional | Video meetings (`docs/REUNIOES.md`) |
| `CALL_RING_SECONDS`, `CALL_MAX_PARTICIPANTS`, `CALL_MAX_HOURS`, `ICE_STUN_URLS`, `TURN_URLS`, `TURN_SECRET` | optional | Chat calls; defaults work locally (`docs/LIGACOES.md`) |
| `RECORDINGS_S3_BUCKET`, `RECORDINGS_S3_REGION`, `RECORDINGS_S3_ENDPOINT`, `RECORDINGS_S3_ACCESS_KEY`, `RECORDINGS_S3_SECRET_KEY`, `MEETING_RECORDING_RETENTION_DAYS` | optional | Recording storage (S3, R2 or MinIO) |
| `MEETING_AI_ENABLED`, `MEETING_AI_LANGUAGE`, `MEETING_AI_MAX_SECONDS`, `MEETING_AI_MAX_BYTES` | optional | Meeting transcription and summary pipeline |
| `WHISPER_MODEL`, `WHISPER_DEVICE`, `WHISPER_COMPUTE_TYPE`, `WHISPER_MODEL_DIR` | optional | faster-whisper settings |
| `OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_CONTEXT_TOKENS` | optional | Local LLM used for meeting summaries |

## External services

| Service | Used for | Cost |
|---------|----------|------|
| PostgreSQL 16 | Main database (prod) | Self-hosted |
| Redis | Celery broker and realtime channel layer | Self-hosted |
| Cloudinary | Uploaded files and images | Free tier |
| SMTP (e.g. Gmail app password) | One-time codes and invitations | Free |
| Google OAuth, Calendar, Drive | Sign-in and calendar/Drive sync | Free |
| Firebase Cloud Messaging | Push notifications | Free |
| Mercado Pago | Task charges | Per transaction |
| GitHub App | Sign-in, repositories, pull requests, webhooks | Free |
| LiveKit (Cloud free tier or self-hosted `livekit-server`) | Video meetings and recording egress | Free tier / self-hosted |
| S3-compatible storage (MinIO self-hosted, or R2) | Meeting recordings | Self-hosted / free tier |
| Ollama + faster-whisper | Meeting summaries and transcription on our own server | Self-hosted |
| Google Gemini | Subscriber AI assistant | Free tier |

Webhooks (`payments/webhook/`, `integrations/github/webhook/`, `meetings/livekit/webhook/`)
are public by design and have their own rate limit (`webhook` scope). GitHub and LiveKit
calls are checked by signature; the Mercado Pago one only triggers a re-read of the
payment from Mercado Pago, so a forged call cannot change a payment. Login, registration and password reset use the `auth` scope.

## Current endpoints

All routes are under `/api/v1/`. Public routes need no login; the rest need the
auth cookies (see the auth section of the project guide).

### Authentication and sessions

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/login/` | Creates a session and sets the auth cookies on the client |
| `POST /api/v1/refresh/` | Rotates the access/refresh tokens |
| `POST /api/v1/me/logout/` | Ends this device's session and clears the cookies |
| `POST /api/v1/me/revoke-sessions/` | Logs out of every device |
| `POST /api/v1/me/deactivate/` | Deactivates the user's own account (`is_active = False`; never deleted) |
| `GET /api/v1/sessions/` | Active sessions of the user, flags the current one |
| `DELETE /api/v1/sessions/<id>/` | Revokes another device's session |

### Users

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/users/me/` | The logged user's data |
| `GET /api/v1/users/list/` | Lists users. Non-staff users see themselves and active members of the organizations they belong to; staff and superusers (`is_staff`, `is_superuser`) see everyone |
| `GET /api/v1/users/<id>/` | One user, with the same visibility rule as the list |

### One-time code flows

Each flow has three steps: **request** (sends a code by e-mail), **verify**
(only checks the code, changes nothing) and **confirm** (applies the change).

| Flow | Endpoints | Notes |
|------|-----------|-------|
| Registration | `POST /api/v1/registration/request/`, `verify/`, `confirm/` | Creates the user inactive (`is_active = False`) and e-mails a code; confirm sets name and password and activates it |
| Password reset | `POST /api/v1/password-reset/request/`, `verify/`, `confirm/` | Always answers "code sent", even if the e-mail does not exist |
| E-mail change | `POST /api/v1/email-change/request/`, `verify/`, `confirm/` | Logged users only; the code goes to the new address; confirm needs the current password |

See [transactional e-mail layouts](docs/EMAIL_LAYOUTS.md) for the existing code and
invitation templates, verification results and remaining visual checks.

## Production and automatic deployment

[deployment/README.md](deployment/README.md) contains the versioned workspace
Compose files, Nginx configuration and dev-branch deployment timer. Production
uses separate volumes and secrets. Merge the deployment changes into `dev` to activate automatic updates on the server.
