#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

env_file=".work/re/.env.re.lock"
[[ -f "$env_file" ]] || env_file=".work/re/.env.re"
if [[ ! -f "$env_file" ]]; then
  echo "Run bootstrap-re-containers.ps1 first." >&2
  exit 2
fi

image="$(awk -F= '$1=="RE_RUNNER_IMAGE" {print substr($0,index($0,"=")+1)}' "$env_file")"
[[ -n "$image" ]] || image="agentkvm2usb/re-runner:1"

usb_path="${BEAGLE_USB_PATH:-}"
if [[ -z "$usb_path" ]]; then
  line="$(lsusb | grep -i -m1 -E 'Total Phase|Beagle' || true)"
  if [[ -z "$line" ]]; then
    cat >&2 <<'MSG'
No Total Phase/Beagle USB device is visible inside WSL.
On Windows, run `usbipd list`, bind the Beagle from an elevated shell if needed,
then run `usbipd attach --wsl --busid <BUSID>`.
MSG
    exit 3
  fi
  bus="$(awk '{print $2}' <<<"$line")"
  dev="$(awk '{gsub(":","",$4); print $4}' <<<"$line")"
  usb_path="/dev/bus/usb/$bus/$dev"
fi
[[ -e "$usb_path" ]] || { echo "USB device path not found: $usb_path" >&2; exit 4; }

api_file="$(find .work/vendor/totalphase/extracted -type f \( -iname 'beagle.py' -o -iname 'libbeagle.so*' -o -iname 'beagle.so' \) 2>/dev/null | head -n 1 || true)"
[[ -n "$api_file" ]] || { echo "No extracted Linux Beagle API was found. Refresh the Total Phase inventory." >&2; exit 5; }
api_dir="$(realpath "$(dirname "$api_file")")"
vendor_root="$(realpath "$repo_root/.work/vendor")"
case "$api_dir" in
  "$vendor_root"/*) relative_api="${api_dir#"$vendor_root/"}" ;;
  *) echo "Resolved Beagle API is outside the staged vendor root: $api_dir" >&2; exit 6 ;;
esac
container_api="/work/vendor/$relative_api"

if [[ $# -eq 0 ]]; then
  set -- python3 /work/scripts/capture_beagle_usb12.py --help
fi

docker run --rm \
  --network none \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --device "$usb_path:$usb_path" \
  --mount type=bind,src="$repo_root/.work/vendor",dst=/work/vendor,readonly \
  --mount type=bind,src="$repo_root/.work/re/output",dst=/work/output \
  --mount type=bind,src="$repo_root/scripts",dst=/work/scripts,readonly \
  --env "PYTHONPATH=$container_api" \
  --env "LD_LIBRARY_PATH=$container_api" \
  --workdir /work \
  "$image" "$@"
