# Product Scope

What we are building on top of this Django base, and how the data model maps to it.
Full detail: [`RELATORIO-FINAL.md`](RELATORIO-FINAL.md) (pt-BR report) and
[`modelagem-final.dbml`](modelagem-final.dbml) (diagram for dbdiagram.io).
Structure and style rules stay in [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md) and
[`CONVENTIONS.md`](CONVENTIONS.md): everything is a **module inside `core`**.

## 1. Goal

Hackathon 3INFO (IFC Araquari, 2026-10-23/24, 24h): a generic, collaborative Kanban
("GitHub Projects" for any context, not only software).

```
User -> Organization -> Sector (holds the Kanban board) -> Task
```

- **Organization**: workspace. Every user gets a personal one on registration.
- **Sector**: the "project" of the challenge. Has participants, its own statuses (columns) and tasks.
- **Task**: title, description, priority, due date, assignee, checklist, comments, links.

Evaluated: basic requirements working with data created during use, plus **at least one
integration that performs a real operation with an external service**
(pasting a link does not count).

## 2. Priorities

| Flag | Meaning | Rule |
|------|---------|------|
| `P1` | Required by the challenge | Build first; never depends on P2/P3 |
| `P2-A..I` | Differentials | Only after P1 is stable; each block is independent and removable |
| `P3` | Schema only | No implementation planned |

Mark each model with a `# [P1]` / `# [P2-x]` comment.

## 3. Modules (all inside `core/modules/`)

| Flag | Module | Models | State |
|------|--------|--------|-------|
| P1 | `organizations` | `Organization`, `OrganizationMember` | models drafted |
| P1 | `kanban` | `Sector`, `SectorMember`, `Status`, `Task`, `ChecklistItem`, `Comment`, `ResourceLink` | models drafted |
| P2-A | `teams` | `Team`, `TeamMember`, `SectorTeam` | models drafted |
| P2-C | `user_settings` | `UserSettings` | models drafted |
| P2-D | `invitations` | `OrganizationInvite` (e-mail via `send_email_task`) | models drafted |
| P2-F | `calendar_sync` | `UserIntegration` (use `EncryptedTextField`), `TaskCalendarEvent` | models drafted |
| P2-H | `chat` | `ChatChannel`, `ChatChannelMember`, `ChatMessage` (needs P2-A; uses `core/websockets`) | models drafted |
| P2-I | `uploads` | `Attachment` (Cloudinary `UploadService` already exists) | model drafted in `uploads/models/` |
| P3 | `kanban` | `CustomField`, `CustomFieldOption`, `TaskFieldValue`, `SavedView`, `TaskDependency` | models drafted (schema only) |

### Already provided by the base (do NOT recreate)

| DBML table / block | Base feature |
|--------------------|--------------|
| `users` | `core.User` (e-mail login, UUID pk, `is_active` soft delete). Single `name` field (no first/last split); `bio` and `avatar_url` added |
| `user_identities` (P2-B) | `feat/google-auth`: `GoogleAuthService` verifies the ID token, no extra table |
| `notifications`, `push_subscriptions` (P2-E) | `notifications` module: `Notification`, `DeviceToken` (Firebase push). Task/sector ids go in `Notification.data` |
| `plans`, `subscriptions`, `payments`, `payment_events` (P2-G) | `payments` module: Mercado Pago PIX `Payment` + webhook. Subscriptions are not modeled; a plain paid-once `Payment` already counts as a real integration |
| `email_log` | skipped; Celery logs are enough |
| AI | `ai` module (Gemini): extra integration available for free |

## 4. Data rules to implement in services (not in views)

- **Sector access**: effective role is the highest of: direct `SectorMember`; team
  membership via `SectorTeam` (P2-A); org owner/admin (implicit manager); any org member as
  viewer when `is_private=False`. `is_private` defaults to `True`. Roles only add, never deny.
- **Defaults on create** (the SQL used triggers; here use a service inside `transaction.atomic`):
  personal organization + owner membership on registration confirm; manager `SectorMember`
  + statuses "To do / In progress / Done" when a sector is created.
- **`Task.completed_at`**: set when moving into a `done` status, cleared when leaving. One
  service method used everywhere (signals do not run on `bulk_create`/`update`).
- **Status/sector consistency**: Django has no composite FK; `Task.clean()` checks it and the
  service must call it (or add a `RunSQL` constraint).
- **Overdue** = `due_date < today` and `completed_at` is null (`Task.objects.overdue()`).
  **Progress** = tasks with `completed_at` / total tasks of the sector (queryset annotate).
- `Task.assignee` must be an effective participant of the sector (validate in service).
- Search and filters (assignee, status, priority, due date) are queries on `Task`
  (`django-filter` is installed).

## 5. Choices made while mapping to this base

| Topic | Decision | Why |
|-------|----------|-----|
| Base class | `Organization`, `Sector`, `Task` inherit `BaseModel`; `owner` = DBML `created_by` | Reuses UUID, timestamps, soft delete |
| Membership tables | Plain models + `UniqueConstraint` | Django needs a single pk |
| Roles | `TextChoices` inside the model (`Role`) | Fixed enums, no roles table |
| `User` changes | None yet | Auth/model changes need owner approval |
| Migrations | Not generated yet | Shared contract; owner approves, then `makemigrations` in `core/migrations/` |

## 6. Plan (24h)

| Window | Delivery |
|--------|----------|
| to ~12h | Migration + organization/sector CRUD, personal org on registration |
| 12h-18h | Board: statuses, tasks, move cards, checklist, comments, links |
| 18h-22h | Search/filters, overdue, progress, permissions, persistence check |
| 22h-03h | The chosen integration (Mercado Pago already exists; Google Calendar is the alternative) |
| 03h-06h | Demo data, full flow test |
| 06h-08h | Presentation rehearsal, no new features (freeze at 06h) |

Safest cuts, in order: custom fields/views (P3), real-time chat, push.

## 7. Open decisions

1. Which integration is the "effective" one: Mercado Pago (exists) or Google Calendar (new).
2. Split `User.name` into first/last name? (touches auth flows)
3. "Translate and attach documents": attach files (uploads) or translate content (new external API)?
4. Custom roles per organization, or keep the fixed enums?
5. Team size and who owns each module.
