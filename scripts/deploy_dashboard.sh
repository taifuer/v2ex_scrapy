#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DASHBOARD="$ROOT/analysis/v2ex-analysis"
HEALTH_URL="${DASHBOARD_HEALTH_URL:-http://127.0.0.1:3090/}"
COMPOSE=(docker compose -f "$DASHBOARD/docker-compose.yml")
COMPOSE_OVERRIDE="${DASHBOARD_COMPOSE_OVERRIDE:-$DASHBOARD/docker-compose.override.yml}"

if [[ -f "$COMPOSE_OVERRIDE" ]]; then
    COMPOSE+=(-f "$COMPOSE_OVERRIDE")
fi

cd "$DASHBOARD"

if [[ ! -d node_modules || package-lock.json -nt node_modules/.package-lock.json ]]; then
  npm ci
fi

npm run build
"${COMPOSE[@]}" build
"${COMPOSE[@]}" up -d --force-recreate

for attempt in {1..20}; do
  if curl --fail --silent "$HEALTH_URL" >/dev/null 2>&1; then
    container_id="$("${COMPOSE[@]}" ps -q dashboard)"
    image_id="$(docker inspect --format '{{.Image}}' "$container_id")"
    printf 'Dashboard is ready: %s\nContainer: %s\nImage: %s\n' "$HEALTH_URL" "$container_id" "$image_id"
    exit 0
  fi
  sleep 1
done

"${COMPOSE[@]}" ps
printf 'Dashboard health check failed: %s\n' "$HEALTH_URL" >&2
exit 1
