# Existing transactional e-mail layouts

The existing code and organization invitation senders now produce multipart messages:
plain text plus HTML. Delivery still uses the configured Django mailer and existing
Celery tasks, arguments, commit callbacks and retry policy. No new events are sent.
Subjects, recipients, code values and invitation URLs are unchanged. Body copy is pt-BR.

## Templates

`core/templates/emails/base.html` contains the shared, single-column layout with a
600 px maximum width, presentation tables, inline styles and a conditional Outlook
wrapper. It uses the frontend's white/black/subtle gray palette and blue accent,
with system fonts and text branding so no external images or styles are required.

- `code.html` and `code.txt` serve registration, password reset and e-mail change.
  Presentation varies by the three existing subject strings; unknown subjects get a
  generic code message. If those strings change, update both templates and the tests.
- `invitation.html` and `invitation.txt` use only the existing organization name and
  link. The HTML provides an accept button and a visible fallback URL.

HTML autoescaping remains enabled. Plain text intentionally does not escape HTML
entities, keeping the original organization name, code and URL intact. There are no
additional queries, validity claims, preferences, API changes or dependencies.

## Verification

Run in the project's configured Python environment:

```bash
python manage.py test core.tests.test_email_templates core.modules.invitations.tests --noinput
ruff check core/utils/email_token_sender.py core/modules/invitations/tasks/invite.py core/tests/test_email_templates.py core/modules/invitations/tests/test_invite.py
```

Verified on 2026-10-23:

- 17 tests passed using in-memory mail delivery and a test database. Coverage includes
  the three code variants, unchanged subjects/recipients/links, leading zeros, HTML
  escaping, delivery errors, commit-only scheduling, rollback and invitation API flows.
- Ruff passed for the four changed Python files; `git diff --check` passed.
- Chromium checked all four variants at 320, 375 and 600 px: 12 layouts without
  horizontal overflow, plus a long unbroken organization name/link at 320 px.
  Screenshots of registration, invitation and the long-content case were inspected.

The development container lacks `django_extensions`, although current settings list
it. The normal test command stops during app loading. To run the tests above, that
optional app was excluded only in the test process's in-memory `INSTALLED_APPS` list;
no project settings or dependencies were changed. The passing result uses that workaround.

## Pending verification and existing limitations

- The initial e-mail work could not access Figma. The later onboarding work obtained
  the F04/F05 frames, but the e-mail templates have not been visually approved against
  Figma; their palette still follows the frontend code used for the original delivery.
- The invitation URL remains `/invitations/accept?token=…`. The companion frontend
  PR now supplies acceptance, login/registration continuation and account switching.
  Deploy both PRs together; a backend-only deployment cannot supply that page.
- Chromium checks do not establish Gmail/Outlook rendering fidelity. No real e-mails
  were sent, and those clients were not tested.
