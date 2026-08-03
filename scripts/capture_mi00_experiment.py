from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from epiphan_sdk import EpiphanKVM_SDK
from mi00_probe import probe_summary


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def default_experiment_id(now: datetime.datetime) -> str:
    return f"mi00-readonly-{now.strftime('%Y%m%dT%H%M%SZ')}"


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, events: list[dict]) -> None:
    path.write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in events), encoding="utf-8")


def write_metadata(path: Path, metadata: dict) -> None:
    lines = ["experiment:"]
    for key, value in metadata["experiment"].items():
        if isinstance(value, list):
            lines.append(f"  {key}:")
            for item in value:
                lines.append(f"    - {item}")
        elif isinstance(value, dict):
            lines.append(f"  {key}:")
            for nested_key, nested_value in value.items():
                lines.append(f"    {nested_key}: {nested_value}")
        elif value is None:
            lines.append(f"  {key}: null")
        else:
            lines.append(f"  {key}: {json.dumps(value)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def capture_experiment(
    output_root: Path,
    experiment_id: str | None = None,
    operator: str | None = None,
    libusb_dll: str | None = None,
) -> Path:
    now = utc_now()
    experiment_id = experiment_id or default_experiment_id(now)
    experiment_dir = output_root / experiment_id
    experiment_dir.mkdir(parents=True, exist_ok=False)

    events = []
    events.append({"event": "start", "timestamp": now.isoformat(), "experiment_id": experiment_id})

    descriptors = probe_summary(libusb_dll=libusb_dll)
    write_json(experiment_dir / "descriptors.json", descriptors)
    events.append({"event": "descriptors_captured", "timestamp": utc_now().isoformat()})

    sdk = EpiphanKVM_SDK()
    try:
        device_status = sdk.get_status()
        mi00_status = sdk.get_config_status(libusb_dll=libusb_dll)
    finally:
        sdk.close()

    write_json(experiment_dir / "device-status.json", device_status)
    write_json(experiment_dir / "mi00-status.json", mi00_status)
    events.append({"event": "device_status_captured", "timestamp": utc_now().isoformat()})
    events.append({"event": "mi00_status_captured", "timestamp": utc_now().isoformat()})

    write_jsonl(experiment_dir / "host-log.jsonl", events)

    output_hashes = {
        name: sha256_file(experiment_dir / name)
        for name in ("descriptors.json", "device-status.json", "mi00-status.json", "host-log.jsonl")
    }
    metadata = {
        "experiment": {
            "id": experiment_id,
            "objective": "Capture guarded read-only KVM2USB MI_00 status for protocol confirmation.",
            "operator": operator or "unknown",
            "date": now.strftime("%Y-%m-%d"),
            "git_commit": git_commit(),
            "environment_lock": None,
            "device_serial": descriptors.get("serial_number"),
            "input_artifacts": [],
            "commands": [
                "scripts/capture_mi00_experiment.py",
                "probe_summary(libusb_dll=...)",
                "EpiphanKVM_SDK.get_status()",
                "EpiphanKVM_SDK.get_config_status()",
            ],
            "outputs": sorted(output_hashes),
            "output_hashes": output_hashes,
            "result": "captured",
            "interpretation": "Read-only MI_00 status captured without vendor OUT/update requests.",
            "follow_up": "Correlate with USBPcap official configuration-tool traces.",
        }
    }
    write_metadata(experiment_dir / "metadata.yaml", metadata)
    return experiment_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture a guarded read-only MI_00 experiment directory.")
    parser.add_argument("--output-root", type=Path, default=Path(".work") / "experiments")
    parser.add_argument("--experiment-id")
    parser.add_argument("--operator")
    parser.add_argument("--libusb-dll")
    args = parser.parse_args()

    experiment_dir = capture_experiment(
        output_root=args.output_root,
        experiment_id=args.experiment_id,
        operator=args.operator,
        libusb_dll=args.libusb_dll,
    )
    print(json.dumps({"experiment_dir": str(experiment_dir)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
