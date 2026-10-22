# Production deployment

Run commands from the workspace root. Existing Cloudflare Tunnel routes must point
`4000.michalski.app` to `http://localhost:4000` and `3009.michalski.app` to
`http://localhost:3009`. TLS terminates at Cloudflare. Both listeners bind only to
loopback; Nginx sets the trusted HTTPS proxy header. Do not expose them publicly.

The frontend serves its compiled Vue assets and proxies `/api/`, `/admin/`,
`/static/` and `/ws/` to Django. Its API base is `https://4000.michalski.app/api/v1`, so browser authentication
and CSRF cookies stay on the frontend host. The backend hostname also exposes
Django directly for API clients and documentation.

Keep backend credentials in `backend-resenha/.env`, including a strong `SECRET_KEY`.
Set a stable `FIELD_ENCRYPTION_KEY` before storing encrypted fields. Keep public
frontend configuration in `frontend-resenha/.env.local`; all `VITE_*` values are
public and embedded at build time. Google OAuth must authorize the production
origin. Firebase and Mapbox require their own configuration.

Copy `.env.prod.example` to `.env.prod` and choose a unique database password and
strong `DJANGO_PROD_SECRET_KEY` (overrides the development key) if
setting up another server. Preserve this password across deployments; editing it
does not change an existing database password.

```sh
docker compose --env-file frontend-resenha/.env.local --env-file .env.prod -f compose.prod.yml config -q
docker compose --env-file frontend-resenha/.env.local --env-file .env.prod -f compose.prod.yml up --build -d
docker compose --env-file .env.prod -f compose.prod.yml ps
docker compose --env-file .env.prod -f compose.prod.yml logs --tail=100 backend worker
```

Only Nginx is exposed. PostgreSQL, Redis and Celery use the internal network.
Migrations run before Daphne starts. Keep one Daphne process with the current
in-memory WebSocket channel layer; use a shared layer before adding replicas.
Database, Redis and uploaded media have persistent volumes. Rebuild after changing
frontend configuration. Environment files are excluded from build contexts.

## Backup

```sh
mkdir -p backups
docker compose --env-file .env.prod -f compose.prod.yml exec -T db pg_dump -U app -d app > backups/app.sql
```

Copy database backups, media and encryption keys off the server and verify restores.
No automatic backup schedule is installed. `down` retains volumes; `down -v` deletes
production data.

## Current verification

Both public HTTPS hosts respond. Browser verification passed email/password login,
secure HttpOnly JWT cookies, authenticated profile reads, CSRF-protected updates and
refresh-token rotation. A regression test covers session rotation and activity.

Firebase public configuration is installed on the server and service worker
activation was verified. Real push delivery was not tested and requires backend
service-account configuration. Mapbox needs a public key. Google OAuth requires
the production origin to be authorized in Google Cloud Console.
These integrations were not validated by deployment. Dependency installation reports
10 existing high-severity audit findings; no automatic dependency upgrades were applied.
