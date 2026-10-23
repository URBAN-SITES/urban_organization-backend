# Workspace deployment

This directory versions the infrastructure for both sibling repositories.
`compose.dev.yml` and `compose.prod.yml` live at the workspace root when used
manually; copy `deploy/` beside them. See [operations](deploy/README.md).
Secrets remain only on the server and are never committed.

## Automatic production updates

The user systemd timer runs `deploy/update.sh` every two minutes. It fetches the
`dev` branch of both repositories, exports exact commits under `releases/`, builds
both images, starts Compose with health checks and verifies both HTTPS endpoints.
Development checkouts and their uncommitted changes are preserved. Builds that
fail do not replace running containers. Failures after migrations/startup require
manual investigation; database changes are not automatically rolled back.

Merge both deployment implementation PRs into `dev`. Automation waits until
backend `dev` contains this infrastructure and frontend `dev` contains its
Dockerfile, then deploys exact commits from both `dev` branches. Updates to `main`
or feature branches do not trigger production. The scheduler deploys dev directly;
required CI checks should protect dev.

Initial installation (as the server user):

```sh
cp backend-resenha/deployment/update.sh deploy/update.sh
mkdir -p ~/.config/systemd/user
cp backend-resenha/deployment/resenha-deploy.{service,timer} ~/.config/systemd/user/
loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now resenha-deploy.timer
```

Inspect or trigger updates:

```sh
systemctl --user list-timers resenha-deploy.timer
journalctl --user -u resenha-deploy.service -n 100
systemctl --user start resenha-deploy.service
bash deploy/update.sh --check
```

Old release source directories and images are retained for investigation. Monitor
disk usage and remove obsolete build artifacts deliberately. Production volumes
are shared across releases and must never be deleted by cleanup.

## Firebase Admin credentials

Keep the private service-account JSON at `backend-resenha/firebase-credentials.json`
(ignored by Git and Docker). Set `FIREBASE_CREDENTIALS_FILE` in the server
`.env.prod` to its absolute path so release snapshots can mount it read-only in
backend and worker at `/run/secrets/firebase_admin`. Do not place private keys,
OAuth client secrets or payment access tokens in any `VITE_*` variable.
