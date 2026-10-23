#!/usr/bin/env bash
set -euo pipefail

workspace=${RESENHA_WORKSPACE:-/srv/apps/hackathon-2026}
cd "$workspace"
mkdir -p deploy releases
exec 9>deploy/update.lock
flock -n 9 || exit 0

for repo in backend-resenha frontend-resenha; do
    git -C "$repo" fetch --quiet origin refs/heads/dev:refs/remotes/origin/dev
done
backend_sha=$(git -C backend-resenha rev-parse origin/dev)
frontend_sha=$(git -C frontend-resenha rev-parse origin/dev)
revision="$backend_sha-$frontend_sha"

if ! git -C backend-resenha cat-file -e "$backend_sha:deployment/compose.prod.yml" 2>/dev/null ||
   ! git -C frontend-resenha cat-file -e "$frontend_sha:Dockerfile" 2>/dev/null; then
    echo 'Waiting for deployment PRs to reach both dev branches; production unchanged.'
    exit 0
fi
if [[ ${1:-} == --check ]]; then
    echo "Available dev revisions: $revision"
    exit 0
fi
if [[ -f deploy/current-revision ]] && [[ $(cat deploy/current-revision) == "$revision" ]]; then
    exit 0
fi

release="$workspace/releases/$revision"
mkdir -p "$release/backend-resenha" "$release/frontend-resenha"
git -C backend-resenha archive "$backend_sha" | tar -x -C "$release/backend-resenha"
git -C frontend-resenha archive "$frontend_sha" | tar -x -C "$release/frontend-resenha"
cp "$release/backend-resenha/deployment/compose.prod.yml" "$release/compose.prod.yml"
mkdir -p "$release/deploy"
cp "$release/backend-resenha/deployment/deploy/"* "$release/deploy/"
ln -sfn "$workspace/.env.prod" "$release/.env.prod"
ln -sfn "$workspace/backend-resenha/.env" "$release/backend-resenha/.env"
ln -sfn "$workspace/frontend-resenha/.env.local" "$release/frontend-resenha/.env.local"

compose=(docker compose --project-directory "$release"
    --env-file "$release/frontend-resenha/.env.local"
    --env-file "$release/.env.prod" -f "$release/compose.prod.yml")
echo "Building dev revisions: $revision"
"${compose[@]}" config -q
# Build both images before replacing any running application containers.
"${compose[@]}" build
"${compose[@]}" up -d --wait --wait-timeout 180
for url in https://4000.michalski.app/ https://3009.michalski.app/admin/login/; do
    curl --fail --silent --show-error --retry 5 --retry-all-errors --retry-delay 2 --max-time 20 -o /dev/null "$url"
done
printf '%s\n' "$revision" > deploy/current-revision
ln -sfn "$release" deploy/current-release
# Keep the scheduler entrypoint in sync with the successfully deployed backend.
cp "$release/backend-resenha/deployment/update.sh" deploy/update.sh.next
chmod 755 deploy/update.sh.next
mv deploy/update.sh.next deploy/update.sh
echo "Deployed dev revisions: $revision"
