# Django REST Framework Base Project Template

Django 6.1 + DRF backend with e-mail/JWT authentication (HttpOnly cookies),
session control and one-time-code flows, ready to extend.

## Documentation

| Doc | What's in it |
|-----|--------------|
| [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md) | Stack, running locally, folder structure, auth, business rules, known issues |
| [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) | Branches, commits, naming and code style |
| [`docs/TEAM_WORKFLOW.md`](docs/TEAM_WORKFLOW.md) | Issues, PRs, collisions, splitting large tasks |
| [`docs/FEATURE_BRANCHES.md`](docs/FEATURE_BRANCHES.md) | Optional `feat/*` branches and how to combine them |
| [`AGENTS.md`](AGENTS.md) | Rules for AI agents working in this repo |

Interactive API docs: `/api/docs/urls/` (Swagger) and `/api/docs/schema/` (OpenAPI).

## Quick start

```bash
pdm install
cp .env.example .env            # fill SECRET_KEY at least
pdm run manage.py migrate
pdm run dev
```

## Current endpoints

All routes are under `/api/`. Public routes need no login; the rest need the
auth cookies (see the auth section of the project guide).

### Authentication and sessions

| Endpoint | Description |
|----------|-------------|
| `POST /api/login/` | Creates a session and sets the auth cookies on the client |
| `POST /api/refresh/` | Rotates the access/refresh tokens |
| `POST /api/me/logout/` | Ends this device's session and clears the cookies |
| `POST /api/me/revoke-sessions/` | Logs out of every device |
| `POST /api/me/deactivate/` | Deactivates the user's own account (`is_active = False`; never deleted) |
| `GET /api/sessions/` | Active sessions of the user, flags the current one |
| `DELETE /api/sessions/<id>/` | Revokes another device's session |

### Users

| Endpoint | Description |
|----------|-------------|
| `GET /api/users/me/` | The logged user's data |
| `GET /api/users/list/` | Lists users. Non-staff users only see active ones (`is_active`); staff and superusers (`is_staff`, `is_superuser`) see everyone |

### One-time code flows

Each flow has three steps: **request** (sends a code by e-mail), **verify**
(only checks the code, changes nothing) and **confirm** (applies the change).

| Flow | Endpoints | Notes |
|------|-----------|-------|
| Registration | `POST /api/registration/request/`, `verify/`, `confirm/` | Creates the user inactive (`is_active = False`) and e-mails a code; confirm sets name and password and activates it |
| Password reset | `POST /api/password-reset/request/`, `verify/`, `confirm/` | Always answers "code sent", even if the e-mail does not exist |
| E-mail change | `POST /api/email-change/request/`, `verify/`, `confirm/` | Logged users only; the code goes to the new address; confirm needs the current password |

## To do

- [ ] Log the user out as soon as the e-mail or password changes.
- [ ] Visual template for the e-mailed codes, plus a mail sending profile in the `MAILERS` setting.
- [ ] Add docstrings to classes and functions.
- [ ] Improve the use of drf-spectacular.
