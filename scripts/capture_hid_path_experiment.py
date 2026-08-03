from __future__ import annotations

import argparse
import datetime
import json
import platform
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import hid

from epiphan_sdk import EpiphanKVM_SDK
from scripts.capture_mi00_experiment import sha256_file, write_json, write_jsonl, write_metadata


EPIPHAN_VID = 0x2B77
KVM2USB3_PID = 0x3661
TOTAL_PHASE_VID = "1679"
BEAGLE_USB12_PID = "2001"


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def default_experiment_id(now: datetime.datetime) -> str:
    return f"hid-path-{now.strftime('%Y%m%dT%H%M%SZ')}"


def git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def hid_descriptors() -> list[dict]:
    descriptors = []
    for device in hid.enumerate(EPIPHAN_VID, KVM2USB3_PID):
        descriptors.append(
            {
                "path": device.get("path").hex() if isinstance(device.get("path"), bytes) else device.get("path"),
                "interface_number": device.get("interface_number"),
                "usage_page": device.get("usage_page"),
                "usage": device.get("usage"),
                "manufacturer_string": device.get("manufacturer_string"),
                "product_string": device.get("product_string"),
                "serial_number": device.get("serial_number"),
            }
        )
    return descriptors


def beagle_analyzer_status() -> dict:
    if platform.system() != "Windows":
        return {"checked": False, "reason": "non-windows-host"}

    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "Get-PnpDevice -PresentOnly | "
            "Where-Object { $_.InstanceId -like 'USB\\VID_1679&PID_2001*' } | "
            "Select-Object Status,Class,FriendlyName,InstanceId,Problem,ConfigManagerErrorCode | "
            "ConvertTo-Json -Compress"
        ),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except Exception as exc:
        return {"checked": True, "error": str(exc)}

    if result.returncode != 0:
        return {"checked": True, "error": result.stderr.strip() or f"exit {result.returncode}"}

    output = result.stdout.strip()
    if not output:
        return {"checked": True, "present": False}

    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return {"checked": True, "present": True, "raw": output}

    devices = parsed if isinstance(parsed, list) else [parsed]
    return {
        "checked": True,
        "present": bool(devices),
        "vid": TOTAL_PHASE_VID,
        "pid": BEAGLE_USB12_PID,
        "devices": devices,
    }


def capture_experiment(
    output_root: Path,
    experiment_id: str | None = None,
    operator: str | None = None,
    macro: str | None = None,
    runtime_root: Path | None = None,
    start_delay_ms: int = 0,
) -> Path:
    now = utc_now()
    experiment_id = experiment_id or default_experiment_id(now)
    experiment_dir = output_root / experiment_id
    experiment_dir.mkdir(parents=True, exist_ok=False)

    runtime_root = runtime_root or experiment_dir / "runtime"
    macro = macro or "PRESS capslock\nDELAY 1000\nPRESS capslock\nDELAY 1000"

    events: list[dict] = [{"event": "start", "timestamp": now.isoformat(), "experiment_id": experiment_id}]

    descriptors = {
        "vid": EPIPHAN_VID,
        "pid": KVM2USB3_PID,
        "hid": hid_descriptors(),
        "beagle_analyzer": beagle_analyzer_status(),
    }
    write_json(experiment_dir / "descriptors.json", descriptors)
    events.append({"event": "descriptors_captured", "timestamp": utc_now().isoformat()})

    sdk = EpiphanKVM_SDK(runtime_root=runtime_root)
    try:
        before_status = sdk.get_status()
        before_screen = sdk.get_screen("hid_path_before", overlay=True)
        events.append(
            {
                "event": "before_status_captured",
                "timestamp": utc_now().isoformat(),
                "status": before_status,
                "screen": before_screen,
            }
        )

        if start_delay_ms > 0:
            events.append(
                {
                    "event": "start_delay",
                    "timestamp": utc_now().isoformat(),
                    "delay_ms": start_delay_ms,
                }
            )
            time.sleep(start_delay_ms / 1000)

        macro_started_at = utc_now()
        macro_result = sdk.run_macro(macro)
        macro_finished_at = utc_now()
        events.append(
            {
                "event": "macro_executed",
                "timestamp": macro_finished_at.isoformat(),
                "started_at": macro_started_at.isoformat(),
                "finished_at": macro_finished_at.isoformat(),
                "macro": macro,
                "result": macro_result,
            }
        )

        after_status = sdk.get_status()
        after_screen = sdk.get_screen("hid_path_after", overlay=True)
        events.append(
            {
                "event": "after_status_captured",
                "timestamp": utc_now().isoformat(),
                "status": after_status,
                "screen": after_screen,
            }
        )
    finally:
        sdk.close()

    write_json(experiment_dir / "before-status.json", before_status)
    write_json(experiment_dir / "macro-result.json", macro_result)
    write_json(experiment_dir / "after-status.json", after_status)
    write_jsonl(experiment_dir / "host-log.jsonl", events)

    output_hashes = {
        name: sha256_file(experiment_dir / name)
        for name in (
            "descriptors.json",
            "before-status.json",
            "macro-result.json",
            "after-status.json",
            "host-log.jsonl",
        )
    }
    metadata = {
        "experiment": {
            "id": experiment_id,
            "objective": "Correlate host-side KVM2USB HID writes with target-side USB analyzer evidence.",
            "operator": operator or "unknown",
            "date": now.strftime("%Y-%m-%d"),
            "git_commit": git_commit(),
            "environment_lock": None,
            "device_serial": None,
            "input_artifacts": [],
            "commands": [
                "scripts/capture_hid_path_experiment.py",
                "EpiphanKVM_SDK.get_status()",
                "EpiphanKVM_SDK.get_screen()",
                "EpiphanKVM_SDK.run_macro()",
            ],
            "outputs": sorted(output_hashes),
            "output_hashes": output_hashes,
            "result": "captured",
            "interpretation": "Host-side HID descriptors, status, macro writes, and screen state captured for Beagle trace correlation.",
            "follow_up": "Compare host macro timestamps to downstream USB HID traffic and target LED/screen response.",
        }
    }
    write_metadata(experiment_dir / "metadata.yaml", metadata)
    return experiment_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture a KVM2USB HID path experiment directory.")
    parser.add_argument("--output-root", type=Path, default=Path(".work") / "experiments")
    parser.add_argument("--experiment-id")
    parser.add_argument("--operator")
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument(
        "--macro",
        default=None,
        help="Macro to execute. Defaults to a reversible Caps Lock on/off probe.",
    )
    parser.add_argument(
        "--start-delay-ms",
        type=int,
        default=0,
        help="Delay before executing the macro, useful when synchronizing with an external USB analyzer.",
    )
    args = parser.parse_args()

    experiment_dir = capture_experiment(
        output_root=args.output_root,
        experiment_id=args.experiment_id,
        operator=args.operator,
        macro=args.macro,
        runtime_root=args.runtime_root,
        start_delay_ms=args.start_delay_ms,
    )
    print(json.dumps({"experiment_dir": str(experiment_dir)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
