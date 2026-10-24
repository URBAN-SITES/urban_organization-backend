# Push test cross-check (2026-10-24)

> Historical first review. The subsequent branch review and additional organization
> and task-status events are documented in [PUSH_NOTIFICATIONS.md](PUSH_NOTIFICATIONS.md).

Reviewed the backend `fix/notifications` checkout and the read-only frontend
`frontend-resenha-coders` checkout on `dev`. No frontend files were changed.
This review supersedes local configuration assumptions in the earlier
`NOTIFICATIONS_INTEGRATION.md`; it does not verify a deployed server.

## Contract compatibility

The frontend sends the correct requests through its cookie/CSRF-aware axios client:

- `POST /api/v1/notifications/devices/` with `{token}` before enabling the test button.
- `POST /api/v1/notifications/send/` with `{token, title, body}`.
- `DELETE /api/v1/notifications/devices/` with `{token}` in the JSON body.

The test endpoint returns `{message_id}` after Firebase accepts the message. It does
not create an inbox item or broadcast `notification.created`. Not seeing a new inbox
item after clicking the test button is therefore expected, not a delivery failure.

The backend sends an FCM `notification` payload, compatible with both the frontend's
`onMessage` listener and the Firebase-initialized PWA worker. A separate manual
`showNotification` handler is not required for background delivery with this payload;
adding one can duplicate notifications.

## Frontend findings (not changed)

1. **Foreground and background are different acceptance tests.**
   `src/modules/notifications/stores/notifications.ts` receives foreground messages
   with `onMessage`; `composables/useNotificationSession.ts` shows a Vue Sonner toast.
   Firebase does not automatically show an operating-system notification while an
   application tab is visible. The success toast from
   `components/notificationComp.vue` only confirms HTTP success, not receipt. Look
   separately for the received message toast titled `ResenhaCoders`.
2. **Development has no push worker by design.** `vite.config.ts` sets
   `devOptions.enabled=false`. On a fresh origin, `npm run dev` cannot pass push
   activation. The composable reports this explicitly. Use a build/preview or HTTPS
   deployment, and check Application > Service Workers for an active `/sw.js`.
3. **Default preview is not an end-to-end local environment.** The current frontend
   `.env` points the built API client at `http://127.0.0.1:8000/api/v1/`. Preview
   normally runs on port 4173, which is not in the backend's trusted-origin allowlist;
   preview also has no API/WebSocket proxy configured. Using `localhost` for the UI
   and `127.0.0.1` for the API also breaks the intended same-site cookie setup.
   For a local HTTP push test with this existing API URL, build and use
   `npm run preview -- --host 127.0.0.1 --port 5173 --strictPort`, opening exactly
   `http://127.0.0.1:5173`, with the backend on `127.0.0.1:8000`. This tests FCM,
   not preview WebSocket delivery. A different compiled API URL requires a matching
   origin/proxy arrangement. Do not globally relax CORS or CSRF to bypass this.
4. **Browser activation is not the global account preference.** The notification
   store's `pushEnabled` only checks its token. The settings screen independently
   updates `push_enabled` through `/api/v1/users/me/settings/`. A token may be
   registered and the test button visible while the account blocks all push. The
   frontend should distinguish these states and explain the global preference.
5. The service discards the successful `message_id`; retaining it for diagnostics
   would help correlate browser tests. Its existing unit tests mock HTTP/Firebase,
   so passing those tests is not proof of device delivery.

## Local configuration observed

The frontend `.env` has populated Firebase configuration and VAPID variables. This
does not validate those values or the already-built assets. Vite embeds these values
at build time, including in the worker; changing them requires a rebuild.

This backend checkout has no `.env`, no conventional `firebase-credentials.json`,
and no `FIREBASE_CREDENTIALS` in the process environment. A local send returns 503
until a valid service-account file is configured. No credentials were created or
copied, and project consistency could not be verified. The production Compose secret
path is separate and was not tested live.

## Backend corrections

- Record individual multicast failures with notification ID, device index, error
  type/code, and batch success/failure counts. Do not include token or message text
  in these new structured fields. Record skipped sends when credentials are absent.
- Preserve tokens on `SenderIdMismatchError`: this indicates incompatible project
  credentials/token provenance, not proof that a device registration expired.
  Log it so configuration can be corrected without silently losing registrations.
- Remove expired/unregistered tokens on the test path as well as the automatic path.
  Keep tokens for transient provider errors.
- Return a distinct 403 explanation for account-level push opt-out rather than
  incorrectly asking an already-registered browser to register again.
- Log test acceptance, provider failures, and credential initialization failures.

Request/response shapes and HTTP status codes remain compatible. No dependencies,
migrations, authentication behavior or global settings were changed. Delivery is
still best-effort, synchronous after commit, and without automatic retry.

## Browser acceptance procedure

1. Configure valid backend credentials from the same Firebase project as the
   frontend/VAPID configuration. Rebuild the frontend after configuration changes.
2. Use HTTPS production or the local preview arrangement above. Log in on that
   origin, enable the account preference and activate this browser's push.
3. Confirm registration returns 204, then click the test button. Inspect
   `POST /api/v1/notifications/send/`: 200 with `message_id` means Firebase accepted
   it; 403 means ownership/preference, 503 means backend configuration, and 502
   means provider rejection. Check the response detail and backend logs.
4. With the page visible, expect a received-message toast, not an OS notification.
5. For a deterministic background test, schedule the existing button click from
   DevTools, then hide **all tabs/windows for the application origin** before it runs:

   ```js
   setTimeout(() => {
     Array.from(document.querySelectorAll('button'))
       .find((button) => button.textContent?.includes('Enviar push de teste'))
       ?.click()
   }, 5000)
   ```

   Keep the browser running. Expect an OS notification if browser/OS permissions
   allow it; check notification-center/Do Not Disturb settings too. A visible second
   app tab can route receipt to foreground instead.
6. Separately test automatic delivery: assign a real task to a different active
   account with a registered device. Expect an inbox item, realtime delivery where
   WebSockets are configured, and FCM delivery. Self-assignment intentionally does
   not notify.

Live device delivery remains unverified until these browser checks are performed.

## Automated verification

- Combined backend notifications/Kanban/chat/user-settings suite: 105 tests passed.
  This run started before the two additional cookie/CSRF contract tests were added;
  both are included in the subsequent notification-only run below.
- Backend notification suite: 26 tests passed, including a real JWT cookie/session
  and enforced CSRF registration/send/removal contract test. Firebase calls are mocked.
- Frontend existing notification suite: 6 tests passed with
  `node --test src/modules/notifications/__tests__/notifications.spec.ts`.
- `manage.py check`, `ruff check .`, notification-module format check and
  `git diff --check` passed.

Backend commands used an explicit test-only `SECRET_KEY`, empty
`FIREBASE_CREDENTIALS`, and the CI Fernet fixture key from
`.github/workflows/ruff.yml`. Tests that exercise push explicitly override credentials
and mock provider calls. No live push was sent.
