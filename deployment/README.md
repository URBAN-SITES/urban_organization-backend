# Workspace deployment

This directory versions the infrastructure for both sibling repositories.
`compose.dev.yml` and `compose.prod.yml` live at the workspace root when used
manually; copy `deploy/` beside them. See [operations](deploy/README.md).
Secrets remain only on the server and are never committed.

## Automatic production updates

The user systemd timer runs `deploy/update.sh` every two minutes. It fetches the
`main` branch of both repositories, exports exact commits under `releases/`, builds
both images, starts Compose with health checks and verifies both HTTPS endpoints.
Development checkouts and their uncommitted changes are preserved. Builds that
fail do not replace running containers. Failures after migrations/startup require
manual investigation; database changes are not automatically rolled back.

The implementation PRs target `dev`. Merge them before merging the release PRs
from `dev` into `main`. Automation waits until backend `main` contains this
infrastructure and frontend `main` contains its Dockerfile. A push to `dev` or a PR branch does not trigger production.
The scheduler deploys main directly; required CI checks should protect main.

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
