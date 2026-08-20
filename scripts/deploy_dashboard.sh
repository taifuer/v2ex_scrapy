#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DASHBOARD="$ROOT/analysis/v2ex-analysis"
HEALTH_URL="${DASHBOARD_HEALTH_URL:-http://127.0.0.1:3090/}"
COMPOSE=(docker compose -f "$DASHBOARD/docker-compose.yml")
COMPOSE_OVERRIDE="${DASHBOARD_COMPOSE_OVERRIDE:-$DASHBOARD/docker-compose.override.yml}"
export DASHBOARD_IMAGE_TAG="${DASHBOARD_IMAGE_TAG:-$(git -C "$ROOT" rev-parse --short=12 HEAD)}"

if [[ -f "$COMPOSE_OVERRIDE" ]]; then
    COMPOSE+=(-f "$COMPOSE_OVERRIDE")
fi

cd "$DASHBOARD"

if [[ -n "${DASHBOARD_DATA_ARCHIVE:-}" ]]; then
  if [[ ! -f "$DASHBOARD_DATA_ARCHIVE" ]]; then
    printf 'Dashboard data archive does not exist: %s\n' "$DASHBOARD_DATA_ARCHIVE" >&2
    exit 1
  fi
  "$ROOT/.venv/bin/python" "$ROOT/scripts/install_dashboard_data.py" \
    "$DASHBOARD_DATA_ARCHIVE" --target "$DASHBOARD/public"
elif [[ ! -f "$DASHBOARD/public/dynamic-manifest.json" ]]; then
  "$ROOT/.venv/bin/python" "$ROOT/scripts/fetch_dashboard_data.py"
fi

previous_container="$("${COMPOSE[@]}" ps -q dashboard 2>/dev/null || true)"
previous_image=""
if [[ -n "$previous_container" ]]; then
  previous_image="$(docker inspect --format '{{.Image}}' "$previous_container" 2>/dev/null || true)"
  if [[ -n "$previous_image" ]]; then
    docker image tag "$previous_image" v2ex-dashboard:rollback
  fi
fi

if [[ ! -d node_modules || package-lock.json -nt node_modules/.package-lock.json ]]; then
  npm ci
fi

npm run build
"${COMPOSE[@]}" build
"${COMPOSE[@]}" up -d --force-recreate

detail_file="$(find "$DASHBOARD/dist" -maxdepth 1 -type f -name 'dynamic-tag-details-*.json' -printf '%f\n' | sort | head -n 1)"

dashboard_ready() {
  curl --fail --silent "$HEALTH_URL" >/dev/null 2>&1 \
    && curl --fail --silent "${HEALTH_URL%/}/dynamic-manifest.json" >/dev/null 2>&1 \
    && { [[ -z "$detail_file" ]] || curl --fail --silent "${HEALTH_URL%/}/$detail_file" >/dev/null 2>&1; }
}

for attempt in {1..30}; do
  if dashboard_ready; then
    container_id="$("${COMPOSE[@]}" ps -q dashboard)"
    image_id="$(docker inspect --format '{{.Image}}' "$container_id")"
    printf 'Dashboard is ready: %s\nCommit tag: %s\nContainer: %s\nImage: %s\n' "$HEALTH_URL" "$DASHBOARD_IMAGE_TAG" "$container_id" "$image_id"
    exit 0
  fi
  sleep 1
done

"${COMPOSE[@]}" ps
"${COMPOSE[@]}" logs --tail 80 dashboard || true
printf 'Dashboard health check failed: %s\n' "$HEALTH_URL" >&2

if [[ -n "$previous_image" ]]; then
  printf 'Restoring previous dashboard image: %s\n' "$previous_image" >&2
  DASHBOARD_IMAGE_TAG=rollback "${COMPOSE[@]}" up -d --force-recreate --no-build
  for attempt in {1..20}; do
    if dashboard_ready; then
      printf 'Previous dashboard image restored successfully.\n' >&2
      exit 1
    fi
    sleep 1
  done
  printf 'Rollback health check also failed.\n' >&2
fi
exit 1
