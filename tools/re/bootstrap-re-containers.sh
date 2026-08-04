#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

: "${ALLOW_COMMUNITY_GHIDRA:=0}"
: "${SKIP_UPSTREAM_BUILDS:=0}"
: "${GHIDRA_VERSION:=12.1.2}"
: "${BINWALK_VERSION:=3.1.0}"

mkdir -p .work/re/{input,output,projects,cache,upstream} .work/vendor
chmod a+rwx .work/re/output .work/re/projects .work/re/cache
env_file=".work/re/.env.re"
cp -n .env.re.example "$env_file" 2>/dev/null || true

docker version >/dev/null
docker compose version >/dev/null

pull_images=(
  "radare/radare2:6.1.8"
  "anchore/syft:v1.19.0"
  "aquasec/trivy:0.57.1"
)
for image in "${pull_images[@]}"; do
  docker pull "$image"
done

# Prime the Trivy database while networking is allowed. Runtime scans use this cache with networking disabled.
mkdir -p .work/re/cache/trivy
if ! docker run --rm \
  --mount type=bind,src="$repo_root/.work/re/cache/trivy",dst=/root/.cache/trivy \
  aquasec/trivy:0.57.1 image --download-db-only; then
  echo "WARNING: Trivy database prefetch failed; offline vulnerability scans will be unavailable until it succeeds." >&2
fi

docker compose --env-file "$env_file" -f compose.re.yml build runner

if ! docker image inspect "agentkvm2usb/ghidra:${GHIDRA_VERSION}-upstream" >/dev/null 2>&1; then
  if [[ "$SKIP_UPSTREAM_BUILDS" == "1" ]]; then
    if [[ "$ALLOW_COMMUNITY_GHIDRA" == "1" ]]; then
      docker pull "blacktop/ghidra:${GHIDRA_VERSION}"
      sed -i "s|^GHIDRA_IMAGE=.*|GHIDRA_IMAGE=blacktop/ghidra:${GHIDRA_VERSION}|" "$env_file"
    else
      echo "Ghidra image is absent and upstream builds were skipped." >&2
      exit 2
    fi
  else
    GHIDRA_VERSION="$GHIDRA_VERSION" BINWALK_VERSION="$BINWALK_VERSION" bash tools/re/build-upstream-images.sh ghidra
  fi
fi

if ! docker image inspect "agentkvm2usb/binwalk:${BINWALK_VERSION}-upstream" >/dev/null 2>&1; then
  if [[ "$SKIP_UPSTREAM_BUILDS" != "1" ]]; then
    GHIDRA_VERSION="$GHIDRA_VERSION" BINWALK_VERSION="$BINWALK_VERSION" bash tools/re/build-upstream-images.sh binwalk
  else
    echo "Binwalk image is absent and upstream builds were skipped." >&2
    exit 3
  fi
fi

python3 tools/re/write-image-lock.py --env-file "$env_file" --locked-env .work/re/.env.re.lock --output .work/re/images.lock.json

docker compose --env-file "$env_file" -f compose.re.yml config >/dev/null

echo "Bootstrap complete. Immutable runtime references were written to .work/re/.env.re.lock and .work/re/images.lock.json."
