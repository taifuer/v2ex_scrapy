#!/usr/bin/env python3
import argparse
import hashlib
import re
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "analysis" / "v2ex-analysis"
DIST = DASHBOARD / "dist"
ARTIFACT_DIR = ROOT / "dist" / "dashboard-deploy"
REMOTE_RE = re.compile(r"^(?:[A-Za-z0-9._-]+@)?[A-Za-z0-9._-]+$")
REMOTE_PATH_RE = re.compile(r"^/[A-Za-z0-9._/-]+$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
HEALTH_URL_RE = re.compile(
    r"^https?://(?:127\.0\.0\.1|localhost)(?::[0-9]{1,5})?/[A-Za-z0-9._~/-]*$"
)

REMOTE_DEPLOY_SCRIPT = r"""
set -euo pipefail

root="$1"
bundle="$2"
version="$3"
health_url="$4"
override="$5"
keep_releases="$6"
release_dir="$root/.releases"
archive="$release_dir/$bundle"
sidecar="$archive.sha256"
staging="$release_dir/staging-$version-$$"
backup="$root/.dist-previous"

mkdir -p "$release_dir"
exec 9>"$root/.deploy.lock"
flock -n 9 || { echo "Another dashboard deployment is running." >&2; exit 1; }

cd "$release_dir"
sha256sum -c "$(basename "$sidecar")"
rm -rf "$staging"
mkdir -p "$staging"
tar -xzf "$archive" -C "$staging"
test -f "$staging/dist/index.html"
test -f "$staging/dist/dynamic-manifest.json"
test -d "$staging/dist/assets"

cd "$root"
compose=(docker compose -f docker-compose.yml)
if [[ -n "$override" ]]; then
  test -f "$override"
  compose+=(-f "$override")
fi

previous_container="$("${compose[@]}" ps -q dashboard 2>/dev/null || true)"
previous_image=""
if [[ -n "$previous_container" ]]; then
  previous_image="$(docker inspect --format '{{.Image}}' "$previous_container" 2>/dev/null || true)"
  if [[ -n "$previous_image" ]]; then
    docker image tag "$previous_image" v2ex-dashboard:rollback
  fi
fi

rollback() {
  status=$?
  trap - ERR
  set +e
  if [[ -d "$backup" ]]; then
    rm -rf "$root/dist"
    mv "$backup" "$root/dist"
  fi
  if [[ -n "$previous_image" ]]; then
    DASHBOARD_IMAGE_TAG=rollback "${compose[@]}" up -d --force-recreate --no-build
  fi
  rm -rf "$staging"
  echo "Dashboard deployment failed; previous dist and image restored." >&2
  exit "$status"
}
trap rollback ERR

rm -rf "$backup"
if [[ -d "$root/dist" ]]; then
  mv "$root/dist" "$backup"
fi
mv "$staging/dist" "$root/dist"
rmdir "$staging"

DASHBOARD_IMAGE_TAG="$version" "${compose[@]}" build dashboard
DASHBOARD_IMAGE_TAG="$version" "${compose[@]}" up -d --force-recreate dashboard

detail_file="$(find "$root/dist" -maxdepth 1 -type f -name 'dynamic-tag-details-*.json' -printf '%f\n' | sort | head -n 1)"
dashboard_ready() {
  curl --fail --silent "$health_url" >/dev/null \
    && curl --fail --silent "${health_url%/}/dynamic-manifest.json" >/dev/null \
    && { [[ -z "$detail_file" ]] || curl --fail --silent "${health_url%/}/$detail_file" >/dev/null; } \
    && { [[ ! -f "$root/.deploy/baidu-analytics.js" ]] || curl --fail --silent "${health_url%/}/baidu-analytics.js" >/dev/null; }
}

ready=false
for _ in {1..40}; do
  if dashboard_ready; then
    ready=true
    break
  fi
  sleep 1
done
[[ "$ready" == true ]]

rm -rf "$backup"
trap - ERR

while IFS= read -r tag; do
  case "$tag" in
    "$version"|rollback|latest|"<none>") ;;
    *) docker image rm "v2ex-dashboard:$tag" >/dev/null 2>&1 || true ;;
  esac
done < <(docker images v2ex-dashboard --format '{{.Tag}}' | sort -u)

mapfile -t archives < <(ls -1t "$release_dir"/v2ex-dashboard-dist-*.tar.gz 2>/dev/null || true)
if (( ${#archives[@]} > keep_releases )); then
  for old in "${archives[@]:keep_releases}"; do
    rm -f "$old" "$old.sha256"
  done
fi

container_id="$("${compose[@]}" ps -q dashboard)"
image_id="$(docker inspect --format '{{.Image}}' "$container_id")"
printf 'Dashboard ready: %s\nVersion: %s\nContainer: %s\nImage: %s\n' \
  "$health_url" "$version" "$container_id" "$image_id"
"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_arguments(
    remote: str,
    remote_dir: str,
    version: str,
    override: str,
    health_url: str = "http://127.0.0.1:3090/",
) -> None:
    if not REMOTE_RE.fullmatch(remote):
        raise ValueError("remote must use host or user@host without shell characters")
    if not REMOTE_PATH_RE.fullmatch(remote_dir) or ".." in Path(remote_dir).parts:
        raise ValueError("remote directory must be a simple absolute path")
    if not VERSION_RE.fullmatch(version):
        raise ValueError("version is not a valid Docker tag component")
    if not HEALTH_URL_RE.fullmatch(health_url):
        raise ValueError("health URL must use local HTTP(S) without shell characters")
    if override and (
        Path(override).is_absolute()
        or ".." in Path(override).parts
        or not re.fullmatch(r"[A-Za-z0-9._/-]+", override)
    ):
        raise ValueError("compose override must be a simple relative path")


def build_dashboard() -> None:
    manifest = DASHBOARD / "public" / "dynamic-manifest.json"
    if not manifest.exists():
        subprocess.run(
            [str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "scripts" / "fetch_dashboard_data.py")],
            cwd=ROOT,
            check=True,
        )
    if not (DASHBOARD / "node_modules").is_dir():
        subprocess.run(["npm", "ci"], cwd=DASHBOARD, check=True)
    subprocess.run(["npm", "run", "build"], cwd=DASHBOARD, check=True)
    subprocess.run(["npm", "run", "test:budget"], cwd=DASHBOARD, check=True)


def package_dist(dist: Path, output: Path) -> dict:
    required = (dist / "index.html", dist / "dynamic-manifest.json", dist / "assets")
    if not all(path.exists() for path in required):
        raise ValueError("dashboard dist is incomplete")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz", compresslevel=6) as archive:
        archive.add(dist, arcname="dist")
    digest = sha256(output)
    sidecar = output.with_suffix(f"{output.suffix}.sha256")
    sidecar.write_text(f"{digest}  {output.name}\n", encoding="ascii")
    return {
        "archive": output,
        "sidecar": sidecar,
        "sha256": digest,
        "bytes": output.stat().st_size,
    }


def git_version() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--remote", required=True, help="SSH host or user@host")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--remote-dir", required=True)
    parser.add_argument("--version")
    parser.add_argument("--health-url", default="http://127.0.0.1:3090/")
    parser.add_argument("--compose-override", default="docker-compose.override.yml")
    parser.add_argument("--keep-releases", type=int, default=3)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()

    version = args.version or git_version()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.keep_releases < 1:
        parser.error("--keep-releases must be positive")
    try:
        validate_arguments(
            args.remote,
            args.remote_dir,
            version,
            args.compose_override,
            args.health_url,
        )
    except ValueError as exc:
        parser.error(str(exc))

    if not args.skip_build:
        build_dashboard()
    bundle = ARTIFACT_DIR / f"v2ex-dashboard-dist-{version}.tar.gz"
    packaged = package_dist(DIST, bundle)
    print(
        f"Packaged dist: {packaged['bytes']:,} bytes, "
        f"SHA-256 {packaged['sha256']}"
    )

    release_dir = f"{args.remote_dir}/.releases"
    subprocess.run(
        ["ssh", "-p", str(args.port), args.remote, "mkdir", "-p", release_dir],
        check=True,
    )
    subprocess.run(
        [
            "scp",
            "-P",
            str(args.port),
            str(packaged["archive"]),
            str(packaged["sidecar"]),
            f"{args.remote}:{release_dir}/",
        ],
        check=True,
    )
    subprocess.run(
        [
            "ssh",
            "-p",
            str(args.port),
            args.remote,
            "bash",
            "-s",
            "--",
            args.remote_dir,
            bundle.name,
            version,
            args.health_url,
            args.compose_override,
            str(args.keep_releases),
        ],
        input=REMOTE_DEPLOY_SCRIPT,
        text=True,
        check=True,
    )


if __name__ == "__main__":
    main()
