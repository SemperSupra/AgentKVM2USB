#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

: "${GHIDRA_VERSION:=12.1.2}"
: "${BINWALK_VERSION:=3.1.0}"

target="${1:-all}"
for command in docker git curl unzip python3 sha256sum awk find; do
  command -v "$command" >/dev/null 2>&1 || { echo "Required command is missing: $command" >&2; exit 127; }
done
upstream="$repo_root/.work/re/upstream"
mkdir -p "$upstream"

build_ghidra() {
  local tag="Ghidra_${GHIDRA_VERSION}_build"
  local metadata="$upstream/ghidra-${GHIDRA_VERSION}-release.json"
  python3 - "$tag" "$metadata" <<'PY'
import json, re, sys, urllib.request

tag, output = sys.argv[1:]
url = f"https://api.github.com/repos/NationalSecurityAgency/ghidra/releases/tags/{tag}"
request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "AgentKVM2USB-bootstrap"})
with urllib.request.urlopen(request) as response:
    release = json.load(response)
assets = [a for a in release.get("assets", []) if re.match(r"ghidra_.*_PUBLIC_.*\.zip$", a["name"], re.I)]
if len(assets) != 1:
    raise SystemExit(f"Expected one Ghidra release ZIP, found {len(assets)}")
body = release.get("body") or ""
match = re.search(r"SHA-256:\s*`?([0-9a-fA-F]{64})", body)
if not match:
    raise SystemExit("Ghidra release body did not contain an SHA-256 value")
result = {
    "tag": tag,
    "asset_name": assets[0]["name"],
    "asset_url": assets[0]["browser_download_url"],
    "sha256": match.group(1).lower(),
    "release_url": release["html_url"],
}
with open(output, "w", encoding="utf-8") as handle:
    json.dump(result, handle, indent=2)
PY

  local asset_name asset_url expected_sha
  asset_name="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["asset_name"])' "$metadata")"
  asset_url="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["asset_url"])' "$metadata")"
  expected_sha="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' "$metadata")"
  local zip_path="$upstream/$asset_name"
  if [[ ! -f "$zip_path" ]] || ! echo "$expected_sha  $zip_path" | sha256sum --check --status; then
    rm -f "$zip_path"
    curl --fail --location --retry 3 --output "$zip_path" "$asset_url"
  fi
  echo "$expected_sha  $zip_path" | sha256sum --check

  local extract_root="$upstream/ghidra-${GHIDRA_VERSION}"
  rm -rf "$extract_root"
  mkdir -p "$extract_root"
  unzip -q "$zip_path" -d "$extract_root"
  local release_dir
  release_dir="$(find "$extract_root" -mindepth 1 -maxdepth 1 -type d -name 'ghidra_*' | head -n 1)"
  [[ -n "$release_dir" ]] || { echo "Extracted Ghidra release directory not found" >&2; exit 3; }
  (cd "$release_dir" && bash docker/build-docker-image.sh)

  local version release source_image
  version="$(awk -F= '$1=="application.version" {print $2}' "$release_dir/Ghidra/application.properties" | tr -d '\r')"
  release="$(awk -F= '$1=="application.release.name" {print $2}' "$release_dir/Ghidra/application.properties" | tr -d '\r')"
  source_image="ghidra/ghidra:${version}_${release}"
  docker tag "$source_image" "agentkvm2usb/ghidra:${GHIDRA_VERSION}-upstream"
}

build_binwalk() {
  local source="$upstream/binwalk-${BINWALK_VERSION}"
  if [[ ! -d "$source/.git" ]]; then
    rm -rf "$source"
    git clone --depth 1 --branch "v${BINWALK_VERSION}" https://github.com/ReFirmLabs/binwalk.git "$source"
  else
    git -C "$source" fetch --depth 1 origin "v${BINWALK_VERSION}"
    git -C "$source" checkout --detach FETCH_HEAD
  fi
  docker build --pull --tag "agentkvm2usb/binwalk:${BINWALK_VERSION}-upstream" "$source"
}

case "$target" in
  ghidra) build_ghidra ;;
  binwalk) build_binwalk ;;
  all) build_ghidra; build_binwalk ;;
  *) echo "Usage: $0 [ghidra|binwalk|all]" >&2; exit 64 ;;
esac
