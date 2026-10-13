# Code Conventions

See [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md) for structure, business rules and feature branches.

Everything (code, comments, commits, branch names, docs, API messages) is written in **English**.

## Branches

| Prefix | Use |
|--------|-----|
| `feat/<kebab-name>` | New feature (`feat/google-auth`) |
| `fix/<kebab-name>` | Bug fix (`fix/session-refresh`) |
| `docs/<kebab-name>` | Docs only |
| `chore/<kebab-name>` | Tooling, deps, CI |

Never commit directly to `main`. Open a PR.

## Commits

[Conventional Commits](https://www.conventionalcommits.org): `<type>(<scope>): <imperative summary>`

```
feat(payments): add Mercado Pago checkout endpoint
fix(core): drop missing updated_at from session update
```

## Project layout

One Django app per domain. Inside an app, split by layer, one module per subject:

```
<app>/
  models/<subject>.py
  serializers/<subject>.py
  services/<subject>.py      # business logic
  views/<subject>.py         # HTTP only: validate -> call service -> respond
  permissions/<subject>.py
  middleware/<subject>.py
  tasks/<subject>.py         # Celery tasks
  utils/<subject>.py
  admin.py
  urls.py                    # feature apps only
  response_messages.py       # every user-facing message (MSG_*)
  tests/test_<subject>.py
```

- A self-contained feature (payments, chat...) gets its own app with the same
  layered folders, so its migrations never collide with `core`. Its routes live
  in `<app>/urls.py` with `app_name`.
- Views never touch business rules; they call a service.
- Services raise DRF exceptions (`ValidationError`, `NotFound`, ...).
- Settings shared by all environments go in `app/settings/base.py`; env-specific in `dev.py` / `prod.py`.
- Secrets come from environment variables (`os.getenv`), never hard-coded. Document new ones in `.env.example`.

## Naming

| Thing | Style | Example |
|-------|-------|---------|
| Module / package | `snake_case` | `password_reset.py` |
| Class | `PascalCase` | `PasswordReset` |
| Function / method / variable | `snake_case` | `send_email_token` |
| Constant | `UPPER_SNAKE_CASE` | `CODE_LIFETIME` |
| Private helper | leading `_` | `_create_user` |
| Model | singular noun | `UserSession` |
| Serializer | `<Subject><Action>Serializer` | `PasswordResetConfirmSerializer` |
| View | `<Subject><Action>View` | `RegistrationRequestView` |
| Service | `<Subject>Service`, static/class methods named as verbs | `SessionService.revoke_all_sessions` |
| Permission | `Is<Rule>` / `Has<Rule>` | `IsUserOwner`, `HasRole` |
| Celery task | verb phrase, `_task` suffix | `send_email_task` |
| Response message | `MSG_<MEANING>` wrapped in `gettext_lazy` | `MSG_CODE_SENT` |
| URL path | `kebab-case`, plural nouns, trailing slash | `/api/password-reset/request/` |
| URL name | `kebab-case` | `password-reset-request` |
| Env var | `UPPER_SNAKE_CASE`, prefixed by service | `CLOUDINARY_URL`, `MP_ACCESS_TOKEN` |
| Test | `test_<behavior>` | `test_login_with_wrong_password_fails` |

## Models

- Translatable `verbose_name` on fields: `models.CharField(_("name"), ...)`.
- Timestamps: `created_at` (`auto_now_add`), `updated_at` (`auto_now`).
- Prefer soft-delete (`is_active=False`) over deleting users.

## API

- JSON keys in `snake_case`.
- Messages: `{"detail": MSG_...}`.
- Every view documented with `@extend_schema(summary=..., request=..., responses=...)`.

## Tooling

- `ruff check .` and `ruff format .` must pass (enforced by pre-commit and CI).
- Add dependencies with `pdm add <pkg>` so `pdm.lock` stays in sync.
