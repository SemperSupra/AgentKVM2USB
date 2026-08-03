#!/usr/bin/env python3
"""Emit structured AgentKVM2USB hardware diagnostics as JSON."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from epiphan_sdk import EpiphanKVM_SDK


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wait-sec",
        type=float,
        default=6.0,
        help="Seconds to wait for a captured frame before reporting no frame.",
    )
    parser.add_argument(
        "--capture",
        action="store_true",
        help="Save one snapshot with overlays and include its absolute path.",
    )
    parser.add_argument(
        "--prefix",
        default="hardware_probe",
        help="Snapshot filename prefix when --capture is used.",
    )
    return parser.parse_args()


def probe(wait_sec: float, capture: bool, prefix: str) -> dict:
    sdk = EpiphanKVM_SDK()
    try:
        deadline = time.time() + max(wait_sec, 0)
        frame_shape = None
        while time.time() <= deadline:
            frame = sdk.get_processed_frame()
            if frame is not None:
                frame_shape = list(frame.shape)
                break
            time.sleep(0.2)

        snapshot = sdk.get_screen(prefix=prefix, overlay=True) if capture else None
        status = sdk.get_status()
        return {
            "hid": {
                "keyboard": sdk.kb_dev is not None,
                "mouse": sdk.mouse_dev is not None,
                "touch": sdk.touch_dev is not None,
                "system": sdk.sys_dev is not None,
            },
            "hidDiscovery": sdk.hid_discovery.as_dict() if sdk.hid_discovery else None,
            "hidDiagnostics": [diagnostic.as_dict() for diagnostic in sdk.hid_diagnostics],
            "hidConnectionReady": sdk.hid_connection_ready,
            "currentCameraName": sdk.current_camera_name,
            "cameras": [
                {"index": index, "name": name}
                for index, name in sdk.list_available_cameras()
            ],
            "frameShape": frame_shape,
            "status": status,
            "snapshot": str(Path(snapshot).resolve()) if snapshot else None,
        }
    finally:
        sdk.close()


def main() -> int:
    args = parse_args()
    print(json.dumps(probe(args.wait_sec, args.capture, args.prefix), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
