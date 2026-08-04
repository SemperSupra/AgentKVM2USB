#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

image="${1:?Usage: scan-re-image.sh IMAGE [OUTPUT_BASENAME]}"
base="${2:-$(sed 's#[/:@]#_#g' <<<"$image")}"
env_file=".work/re/.env.re.lock"
[[ -f "$env_file" ]] || env_file=".work/re/.env.re"
mkdir -p .work/re/input .work/re/output .work/re/cache/trivy
archive=".work/re/input/${base}.docker.tar"
trap 'rm -f "$archive"' EXIT

docker image inspect "$image" >/dev/null
docker save --output "$archive" "$image"

docker compose --env-file "$env_file" -f compose.re.yml run --rm \
  syft "docker-archive:/input/${base}.docker.tar" \
  -o "cyclonedx-json=/output/${base}.sbom.cdx.json" \
  -o "spdx-json=/output/${base}.sbom.spdx.json"

docker compose --env-file "$env_file" -f compose.re.yml run --rm \
  trivy image --input "/input/${base}.docker.tar" \
  --skip-db-update \
  --format json \
  --output "/output/${base}.trivy.json"

printf 'SBOM and vulnerability reports written under %s/.work/re/output\n' "$repo_root"
