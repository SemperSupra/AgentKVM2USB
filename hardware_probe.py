#!/usr/bin/env python3
"""Emit structured AgentKVM2USB hardware diagnostics as JSON."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import cv2
import hid
import numpy as np

from epiphan_sdk import EpiphanKVM_SDK


EPIPHAN_VID = 0x2B77
KVM2USB3_PID = 0x3661
NONBLACK_RATIO_THRESHOLD = 0.0001


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
    parser.add_argument(
        "--include-dshow-options",
        action="store_true",
        help="Use ffmpeg to include DirectShow-advertised video modes on Windows.",
    )
    parser.add_argument(
        "--measure-sec",
        type=float,
        default=0.0,
        help="Seconds to measure frame cadence after the first frame is available.",
    )
    parser.add_argument(
        "--include-mi00",
        action="store_true",
        help="Include guarded read-only MI_00 WinUSB/libusb config-interface status.",
    )
    parser.add_argument(
        "--libusb-dll",
        help="Optional explicit libusb-1.0.dll path for --include-mi00.",
    )
    return parser.parse_args()


def hid_collections() -> list[dict]:
    collections = []
    for device in hid.enumerate(EPIPHAN_VID, KVM2USB3_PID):
        collections.append(
            {
                "interface": device.get("interface_number"),
                "usagePage": _hex_or_none(device.get("usage_page")),
                "usage": _hex_or_none(device.get("usage")),
                "manufacturer": device.get("manufacturer_string"),
                "product": device.get("product_string"),
            }
        )
    return collections


def _hex_or_none(value) -> str | None:
    return hex(value) if value is not None else None


def camera_state(sdk: EpiphanKVM_SDK) -> dict:
    cap = sdk.cap
    opened = bool(cap and cap.isOpened())
    state = {
        "name": sdk.current_camera_name,
        "opened": opened,
    }
    if not opened:
        return state

    state.update(
        {
            "backend": cap.getBackendName() if hasattr(cap, "getBackendName") else None,
            "width": _number_or_none(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": _number_or_none(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": _number_or_none(cap.get(cv2.CAP_PROP_FPS)),
            "fourcc": _fourcc(cap.get(cv2.CAP_PROP_FOURCC)),
        }
    )
    return state


def _number_or_none(value: float):
    return value if value >= 0 else None


def _fourcc(value: float) -> dict:
    code = int(value)
    text = "".join(chr((code >> (8 * i)) & 0xFF) for i in range(4))
    text = text if text.strip("\x00") else None
    return {"int": code, "text": text}


def frame_stats(frame) -> dict | None:
    if frame is None:
        return None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return {
        "shape": list(frame.shape),
        "mean": round(float(gray.mean()), 3),
        "std": round(float(gray.std()), 3),
        "min": int(gray.min()),
        "max": int(gray.max()),
        "nonBlackRatio": round(float(np.count_nonzero(gray > 10) / gray.size), 6),
    }


def measure_frame_cadence(sdk: EpiphanKVM_SDK, duration_sec: float) -> dict | None:
    if duration_sec <= 0:
        return None

    observed_frames = 0
    timestamps = []
    first = None
    last = None
    last_seq = None
    deadline = time.time() + duration_sec
    while time.time() < deadline:
        with sdk._lock:
            frame = sdk.latest_frame.copy() if sdk.latest_frame is not None else None
            seq = sdk.latest_frame_seq
            frame_at = sdk.latest_frame_at
        if frame is None:
            time.sleep(0.01)
            continue
        if seq == last_seq:
            time.sleep(0.002)
            continue
        last_seq = seq
        observed_frames += 1
        timestamps.append(frame_at or time.time())
        if first is None:
            first = frame.copy()
        last = frame.copy()

    intervals = [b - a for a, b in zip(timestamps, timestamps[1:])]
    return {
        "durationSec": duration_sec,
        "observedFrames": observed_frames,
        "measuredFps": round(observed_frames / duration_sec, 3) if duration_sec else None,
        "meanIntervalMs": round(sum(intervals) / len(intervals) * 1000, 3) if intervals else None,
        "minIntervalMs": round(min(intervals) * 1000, 3) if intervals else None,
        "maxIntervalMs": round(max(intervals) * 1000, 3) if intervals else None,
        "firstLastAbsDiffMean": round(float(np.mean(cv2.absdiff(first, last))), 6)
        if first is not None and last is not None
        else None,
    }


def effective_signal(status: dict, stats: dict | None, mi00: dict | None = None) -> dict:
    hid_active = bool(status.get("is_signal_active"))
    mi00_input = ((mi00 or {}).get("requests", {}).get("input_status") or {}).get("parsed") or {}
    mi00_active = bool(mi00_input.get("is_signal_active"))
    frame_present = stats is not None
    frame_nonblank = bool(
        stats
        and stats["nonBlackRatio"] >= NONBLACK_RATIO_THRESHOLD
        and stats["max"] > 10
    )
    return {
        "active": hid_active or mi00_active or frame_nonblank,
        "hidActive": hid_active,
        "mi00Active": mi00_active,
        "framePresent": frame_present,
        "frameNonBlank": frame_nonblank,
        "reason": _effective_signal_reason(hid_active, frame_present, frame_nonblank, mi00_active),
    }


def _effective_signal_reason(hid_active: bool, frame_present: bool, frame_nonblank: bool, mi00_active: bool = False) -> str:
    if hid_active and mi00_active and frame_nonblank:
        return "hid_mi00_and_frame"
    if hid_active and frame_nonblank:
        return "hid_and_frame"
    if hid_active and mi00_active:
        return "hid_and_mi00"
    if hid_active:
        return "hid_report"
    if mi00_active and frame_nonblank:
        return "mi00_and_frame"
    if mi00_active:
        return "mi00_report"
    if frame_nonblank:
        return "frame_content"
    if frame_present:
        return "blank_frame"
    return "no_frame"


def dshow_options(device_name: str | None) -> dict | None:
    if not device_name or not shutil.which("ffmpeg"):
        return None

    command = [
        "ffmpeg",
        "-hide_banner",
        "-list_options",
        "true",
        "-f",
        "dshow",
        "-i",
        f"video={_strip_camera_tag(device_name)}",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    text = "\n".join(part for part in (result.stdout, result.stderr) if part)
    return {
        "tool": "ffmpeg",
        "returnCode": result.returncode,
        "modes": parse_dshow_options(text),
    }


def _strip_camera_tag(name: str) -> str:
    return re.sub(r"^\[[^\]]+\]\s*", "", name)


def parse_dshow_options(text: str) -> list[dict]:
    modes = []
    pattern = re.compile(
        r"pixel_format=(?P<pixel_format>\S+)\s+"
        r"min s=(?P<width>\d+)x(?P<height>\d+)\s+"
        r"fps=(?P<min_fps>[\d.]+)\s+"
        r"max s=(?P<max_width>\d+)x(?P<max_height>\d+)\s+"
        r"fps=(?P<max_fps>[\d.]+)"
    )
    for match in pattern.finditer(text):
        mode = {
            "pixelFormat": match.group("pixel_format"),
            "width": int(match.group("width")),
            "height": int(match.group("height")),
            "minFps": float(match.group("min_fps")),
            "maxFps": float(match.group("max_fps")),
        }
        if mode not in modes:
            modes.append(mode)
    return modes


def probe(
    wait_sec: float,
    capture: bool,
    prefix: str,
    include_dshow_options: bool,
    measure_sec: float,
    include_mi00: bool,
    libusb_dll: str | None,
) -> dict:
    sdk = EpiphanKVM_SDK()
    try:
        deadline = time.time() + max(wait_sec, 0)
        frame = None
        while time.time() <= deadline:
            frame = sdk.get_processed_frame()
            if frame is not None:
                break
            time.sleep(0.2)

        snapshot = sdk.get_screen(prefix=prefix, overlay=True) if capture else None
        status = sdk.get_status()
        stats = frame_stats(frame)
        cadence = measure_frame_cadence(sdk, measure_sec)
        dshow = dshow_options(sdk.current_camera_name) if include_dshow_options else None
        mi00 = sdk.get_config_status(libusb_dll=libusb_dll) if include_mi00 else None
        return {
            "hid": {
                "keyboard": sdk.kb_dev is not None,
                "mouse": sdk.mouse_dev is not None,
                "touch": sdk.touch_dev is not None,
                "system": sdk.sys_dev is not None,
                "collections": hid_collections(),
            },
            "currentCameraName": sdk.current_camera_name,
            "cameraState": camera_state(sdk),
            "directShowOptions": dshow,
            "cameras": [
                {"index": index, "name": name}
                for index, name in sdk.list_available_cameras()
            ],
            "frameShape": stats["shape"] if stats else None,
            "frameStats": stats,
            "frameCadence": cadence,
            "status": status,
            "mi00": mi00,
            "effectiveSignal": effective_signal(status, stats, mi00),
            "snapshot": str(Path(snapshot).resolve()) if snapshot else None,
        }
    finally:
        sdk.close()


def main() -> int:
    args = parse_args()
    print(
        json.dumps(
            probe(
                args.wait_sec,
                args.capture,
                args.prefix,
                args.include_dshow_options,
                args.measure_sec,
                args.include_mi00,
                args.libusb_dll,
            ),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
