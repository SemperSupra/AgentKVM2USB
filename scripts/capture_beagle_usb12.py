from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API_DIR = (
    ROOT
    / ".work"
    / "totalphase"
    / "beagle-api-windows-x86_64-v6.00"
    / "beagle-api-windows-x86_64-v6.00"
    / "python"
)

PID_NAMES = {
    0xE1: "OUT",
    0x69: "IN",
    0xA5: "SOF",
    0x2D: "SETUP",
    0xC3: "DATA0",
    0x4B: "DATA1",
    0x87: "DATA2",
    0x0F: "MDATA",
    0xD2: "ACK",
    0x5A: "NAK",
    0x1E: "STALL",
    0x96: "NYET",
    0x3C: "PRE",
    0x78: "SPLIT",
    0xB4: "PING",
    0xF0: "EXT",
}

TOKEN_PIDS = {"OUT", "IN", "SETUP"}


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def hash_api_files(api_dir: Path) -> dict:
    """Record the vendor API files and version that produced a capture.

    Vendor binaries never enter Git or images; only their hashes and the API
    version string are recorded with the JSONL evidence.
    """
    api_dir = Path(api_dir)
    result: dict = {"api_dir": str(api_dir), "files": []}
    for name in ("beagle_py.py", "beagle.dll", "beagle.so", "libbeagle.so"):
        candidate = api_dir / name
        if candidate.is_file():
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            result["files"].append(
                {"name": name, "sha256": digest, "length": candidate.stat().st_size}
            )
    match = re.search(r"(?i)(v[\d.]+)", str(api_dir))
    if match:
        result["version"] = match.group(1).lower()
    return result


def load_beagle_api(api_dir: Path):
    api_dir = api_dir.resolve()
    if not (api_dir / "beagle_py.py").exists():
        raise FileNotFoundError(f"beagle_py.py not found under {api_dir}")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(api_dir))
    sys.path.insert(0, str(api_dir))
    spec = importlib.util.spec_from_file_location("beagle_py", api_dir / "beagle_py.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load Beagle API from {api_dir}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["beagle_py"] = module
    spec.loader.exec_module(module)
    return module


def detect_devices(bg) -> list[dict]:
    num, ports, unique_ids = bg.bg_find_devices_ext(16, 16)
    devices = []
    for i in range(max(0, num)):
        raw_port = int(ports[i])
        in_use = bool(raw_port & bg.BG_PORT_NOT_FREE)
        port = raw_port & ~bg.BG_PORT_NOT_FREE if in_use else raw_port
        unique_id = int(unique_ids[i])
        devices.append(
            {
                "port": int(port),
                "in_use": in_use,
                "unique_id": unique_id,
                "serial": f"{unique_id // 1000000:04d}-{unique_id % 1000000:06d}",
            }
        )
    return devices


def timestamp_to_ns(stamp: int, samplerate_khz: int) -> int:
    if samplerate_khz <= 0:
        return 0
    return int((int(stamp) * 1000) // (samplerate_khz // 1000))


def decode_events(bg, events: int) -> list[str]:
    mapping = [
        ("HOST_DISCONNECT", bg.BG_EVENT_USB_HOST_DISCONNECT),
        ("TARGET_DISCONNECT", bg.BG_EVENT_USB_TARGET_DISCONNECT),
        ("RESET", bg.BG_EVENT_USB_RESET),
        ("HOST_CONNECT", bg.BG_EVENT_USB_HOST_CONNECT),
        ("TARGET_CONNECT_UNRESET", bg.BG_EVENT_USB_TARGET_CONNECT),
    ]
    return [name for name, mask in mapping if events & mask]


def decode_status(bg, status: int) -> list[str]:
    labels = []
    if status == bg.BG_READ_OK:
        labels.append("OK")
    mapping = [
        ("TIMEOUT", bg.BG_READ_TIMEOUT),
        ("MIDDLE_OF_PACKET", bg.BG_READ_ERR_MIDDLE_OF_PACKET),
        ("SHORT_BUFFER", bg.BG_READ_ERR_SHORT_BUFFER),
        ("BAD_SIGNALS", bg.BG_READ_USB_ERR_BAD_SIGNALS),
        ("BAD_SYNC", bg.BG_READ_USB_ERR_BAD_SYNC),
        ("BIT_STUFF", bg.BG_READ_USB_ERR_BIT_STUFF),
        ("FALSE_EOP", bg.BG_READ_USB_ERR_FALSE_EOP),
        ("LONG_EOP", bg.BG_READ_USB_ERR_LONG_EOP),
        ("BAD_PID", bg.BG_READ_USB_ERR_BAD_PID),
        ("BAD_CRC", bg.BG_READ_USB_ERR_BAD_CRC),
    ]
    labels.extend(name for name, mask in mapping if status & mask)
    return labels


def decode_packet_fields(data: list[int]) -> dict:
    if not data:
        return {}

    pid_name = PID_NAMES.get(data[0])
    if pid_name in TOKEN_PIDS and len(data) >= 3:
        token = data[1] | (data[2] << 8)
        return {
            "token_address": token & 0x7F,
            "token_endpoint": (token >> 7) & 0x0F,
        }
    if pid_name == "SOF" and len(data) >= 3:
        token = data[1] | (data[2] << 8)
        return {"sof_frame": token & 0x07FF}
    return {}


def packet_record(bg, index: int, samplerate_khz: int, length: int, status: int, events: int, time_sop: int, packet) -> dict:
    data = list(packet[: max(0, length)])
    pid = data[0] if data else None
    record = {
        "index": index,
        "host_timestamp": utc_now(),
        "time_sop_ns": timestamp_to_ns(time_sop, samplerate_khz),
        "length": int(length),
        "status": int(status),
        "status_labels": decode_status(bg, int(status)),
        "events": int(events),
        "event_labels": decode_events(bg, int(events)),
        "pid": pid,
        "pid_name": PID_NAMES.get(pid),
        "data_hex": " ".join(f"{byte:02x}" for byte in data),
    }
    record.update(decode_packet_fields(data))
    return record


def summarize_capture(path: Path) -> dict:
    pid_counts: dict[str, int] = {}
    event_counts: dict[str, int] = {}
    endpoint_counts: dict[str, int] = {}
    data_packets = 0
    records = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if "pid_name" not in entry:
            continue
        records += 1
        pid_name = entry.get("pid_name") or "EVENT_ONLY"
        pid_counts[pid_name] = pid_counts.get(pid_name, 0) + 1
        if pid_name in {"DATA0", "DATA1", "DATA2", "MDATA"}:
            data_packets += 1
        for label in entry.get("event_labels") or []:
            event_counts[label] = event_counts.get(label, 0) + 1
        if "token_address" in entry and "token_endpoint" in entry:
            key = f"{entry['token_address']}:{entry['token_endpoint']}"
            endpoint_counts[key] = endpoint_counts.get(key, 0) + 1
    return {
        "records": records,
        "pid_counts": dict(sorted(pid_counts.items())),
        "event_counts": dict(sorted(event_counts.items())),
        "endpoint_counts": dict(sorted(endpoint_counts.items())),
        "data_packets": data_packets,
    }


def capture_usb12(api_dir: Path, output: Path, port: int, max_events: int, max_seconds: float, timeout_ms: int, latency_ms: int) -> dict:
    bg = load_beagle_api(api_dir)
    devices = detect_devices(bg)
    output.parent.mkdir(parents=True, exist_ok=True)

    handle = bg.bg_open(port)
    if handle <= 0:
        result = {
            "success": False,
            "error": int(handle),
            "error_text": bg.bg_status_string(handle),
            "devices": devices,
        }
        output.write_text(json.dumps({"event": "open_failed", **result}, sort_keys=True) + "\n", encoding="utf-8")
        return result

    records = 0
    started = time.monotonic()
    metadata = {}
    try:
        samplerate = bg.bg_samplerate(handle, 0)
        bg.bg_timeout(handle, timeout_ms)
        bg.bg_latency(handle, latency_ms)
        bg.bg_target_power(handle, bg.BG_TARGET_POWER_OFF)
        enable_result = bg.bg_enable(handle, bg.BG_PROTOCOL_USB)
        metadata = {
            "event": "capture_start",
            "timestamp": utc_now(),
            "port": port,
            "devices": devices,
            "samplerate_khz": int(samplerate),
            "timeout_ms": timeout_ms,
            "latency_ms": latency_ms,
            "host_interface_high_speed": bool(bg.bg_host_ifce_speed(handle)),
            "enable_result": int(enable_result),
            "vendor_api": hash_api_files(api_dir),
        }
        with output.open("w", encoding="utf-8") as out:
            out.write(json.dumps(metadata, sort_keys=True) + "\n")
            if enable_result != bg.BG_OK:
                return {"success": False, "error": int(enable_result), "error_text": bg.bg_status_string(enable_result), "output": str(output)}

            packet = bg.array_u08(1024)
            timing = bg.array_u32(bg.bg_bit_timing_size(bg.BG_PROTOCOL_USB, 1024))
            while records < max_events and (time.monotonic() - started) < max_seconds:
                length, status, events, time_sop, _duration, _offset, packet, timing = bg.bg_usb2_read_bit_timing(
                    handle, packet, timing
                )
                if length < 0:
                    out.write(
                        json.dumps(
                            {
                                "event": "read_error",
                                "timestamp": utc_now(),
                                "error": int(length),
                                "error_text": bg.bg_status_string(length),
                                "status": int(status),
                                "events": int(events),
                            },
                            sort_keys=True,
                        )
                        + "\n"
                    )
                    break
                if length > 0 or events != 0 or (status != 0 and status != bg.BG_READ_TIMEOUT):
                    records += 1
                    out.write(
                        json.dumps(packet_record(bg, records, int(samplerate), length, status, events, time_sop, packet), sort_keys=True)
                        + "\n"
                    )
            out.write(json.dumps({"event": "capture_stop", "timestamp": utc_now(), "records": records}, sort_keys=True) + "\n")
    finally:
        try:
            bg.bg_disable(handle)
        finally:
            bg.bg_close(handle)

    return {"success": True, "records": records, "output": str(output), "metadata": metadata}


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture USB low/full-speed traffic with a Total Phase Beagle USB 12 analyzer.")
    parser.add_argument("--api-dir", type=Path, default=Path(os.environ.get("TOTALPHASE_BEAGLE_API_DIR", DEFAULT_API_DIR)))
    parser.add_argument("--output", type=Path, default=Path(".work") / "beagle" / "usb12-capture.jsonl")
    parser.add_argument("--summarize-existing", type=Path, help="Summarize an existing Beagle JSONL capture instead of opening hardware.")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--max-events", type=int, default=200)
    parser.add_argument("--max-seconds", type=float, default=10.0)
    parser.add_argument("--timeout-ms", type=int, default=500)
    parser.add_argument("--latency-ms", type=int, default=200)
    args = parser.parse_args()

    if args.summarize_existing:
        print(json.dumps(summarize_capture(args.summarize_existing), indent=2, sort_keys=True))
        return 0

    result = capture_usb12(
        api_dir=args.api_dir,
        output=args.output,
        port=args.port,
        max_events=args.max_events,
        max_seconds=args.max_seconds,
        timeout_ms=args.timeout_ms,
        latency_ms=args.latency_ms,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
