#!/usr/bin/env python3
"""Official Epiphan-app differential experiment framework.

This module prepares the reproducible, synchronized official-app experiment
needed to locate the first divergence between host-side KVM2USB HID writes and
the target-facing USB interrupt endpoint.

Scope is preparation and analysis only. No live capture or target input is
performed here: every capture entry point refuses to run unless an explicit
human authorization gate is present in the experiment manifest (or a
``--allow-live`` flag that only a human-authorised orchestration step sets).

Everything in this module is deterministic and independently written. Raw
captures, proprietary binaries, decompiled vendor material, credentials, and
restricted evidence stay outside the public repository under ignored/private
paths; only sanitized manifests, hashes, schemas, procedures, and conclusions
are committed.

The merged container toolchain (tools/re) performs the decoding and analysis;
this module only builds capture commands, correlation state, timelines, and
comparison output.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

EPIPHAN_VID = "2b77"
KVM2USB3_PID = "3661"
TOTAL_PHASE_VID = "1679"
BEAGLE_USB12_PID = "2001"

# The bounded, reversible input sequence for the baseline experiment. Caps Lock
# and one harmless ordinary key are chosen so the target state stays harmless.
DEFAULT_MARKERS: List[Dict[str, str]] = [
    {"event": "app_start", "description": "official Epiphan KvmApp application startup"},
    {"event": "device_selected", "description": "device selection in the official application"},
    {"event": "target_enumeration", "description": "target USB enumeration or re-enumeration"},
    {"event": "capslock_down", "description": "Caps Lock key down"},
    {"event": "capslock_up", "description": "Caps Lock key up"},
    {"event": "ordinary_key_down", "description": "one harmless ordinary key down"},
    {"event": "ordinary_key_up", "description": "one harmless ordinary key up"},
    {"event": "all_keys_release", "description": "explicit all-keys release"},
    {"event": "app_close", "description": "official application close"},
]

AUTHORIZATION_GATE_FIELD = "human_authorization_gate"


# --------------------------------------------------------------------------- correlation / timestamps


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def correlation_id(prefix: str = "official-app", now: Optional[dt.datetime] = None) -> str:
    """Return a capture-session correlation ID: ``<prefix>-<UTC YYYYMMDDTHHMMSSZ>``.

    The timestamp is the session identity and is used to name capture output
    paths so host-side and target-side evidence correlate by directory.
    """
    now = now or utc_now()
    return f"{prefix}-{now.strftime('%Y%m%dT%H%M%SZ')}"


def utc_timestamp(now: Optional[dt.datetime] = None) -> str:
    now = now or utc_now()
    return now.isoformat()


def marker_event(event: str, correlation: str, now: Optional[dt.datetime] = None) -> Dict[str, Any]:
    """Build a synchronized event-marker record.

    These markers are the alignment anchor between the host capture, the target
    Beagle capture, the application state log, and the video/signal state.
    """
    return {
        "correlation_id": correlation,
        "event": event,
        "timestamp_utc": utc_timestamp(now),
        "kind": "marker",
    }


# --------------------------------------------------------------------------- host capture (USBPcap / Wireshark)


def usbpcap_command(
    interface: str,
    output: Path,
    *,
    filter_expr: Optional[str] = None,
    usbpcap_cmd: str = "USBPcapCMD.exe",
    buffer_size_mb: int = 128,
) -> List[str]:
    """Construct a host-facing USBPcap capture command (argv list).

    USBPcapCMD syntax: ``USBPcapCMD.exe -d \\\\.\\USBPcap<N> -o out.pcap
    -f <filter> -b <buffer>``. ``-f`` may be omitted to capture all traffic on
    the selected host interface.
    """
    argv = [usbpcap_cmd, "-d", interface, "-o", str(output), "-b", str(buffer_size_mb)]
    if filter_expr:
        argv += ["-f", filter_expr]
    return argv


def wireshark_tshark_command(
    interface: str,
    output: Path,
    *,
    filter_expr: Optional[str] = None,
    tshark_cmd: str = "tshark",
) -> List[str]:
    """Construct a host-facing Wireshark/TShark capture command (argv list)."""
    argv = [tshark_cmd, "-i", interface, "-w", str(output)]
    if filter_expr:
        argv += ["-f", filter_expr]
    return argv


def host_usb_filter(epiphan_vid: str = EPIPHAN_VID, kvm2usb_pid: str = KVM2USB3_PID) -> str:
    """BPF-like capture filter targeting the KVM2USB host interface.

    BPF syntax varies by backend; this expression matches common USBPcap and
    tshark ``usb`` dissector conventions for the KVM2USB device address. An
    empty or unsupported filter is acceptable; the operator records which
    backend and interface was used.
    """
    return f"usb.idVendor == 0x{epiphan_vid} && usb.idProduct == 0x{kvm2usb_pid}"


# --------------------------------------------------------------------------- target capture (Beagle-12)


def beagle_command(
    output: Path,
    *,
    api_dir: Path,
    port: int = 0,
    max_events: int = 5000,
    max_seconds: float = 60.0,
    timeout_ms: int = 500,
    latency_ms: int = 200,
    python: str = "python",
    capture_script: str = "scripts/capture_beagle_usb12.py",
) -> List[str]:
    """Construct a target-facing Beagle USB 12 capture command (argv list).

    Uses the merged capture_beagle_usb12.py so decoding stays in the container
    toolchain. ``--output`` must resolve under an ignored capture root.
    """
    return [
        python,
        capture_script,
        "--api-dir",
        str(api_dir),
        "--output",
        str(output),
        "--port",
        str(port),
        "--max-events",
        str(max_events),
        "--max-seconds",
        str(max_seconds),
        "--timeout-ms",
        str(timeout_ms),
        "--latency-ms",
        str(latency_ms),
    ]


# --------------------------------------------------------------------------- descriptor / endpoint decoding


def decode_token_address(token_address: int, token_endpoint: int) -> Dict[str, int]:
    """Decode a USB token address/endpoint pair into a normalized record."""
    return {
        "address": token_address & 0x7F,
        "endpoint": token_endpoint & 0x0F,
        "direction": "IN" if (token_endpoint & 0x80) else "OUT",
    }


def classify_pid(pid_name: Optional[str]) -> str:
    """Classify a USB PID into a normalized bucket used by the timeline."""
    if not pid_name:
        return "EVENT_ONLY"
    upper = pid_name.upper()
    if upper in ("DATA0", "DATA1", "DATA2", "MDATA"):
        return "DATA"
    if upper in ("IN", "OUT", "SETUP"):
        return "TOKEN"
    if upper in ("ACK", "NAK", "STALL", "NYET"):
        return "HANDSHAKE"
    if upper in ("SOF", "PRE", "SPLIT", "PING"):
        return "SPECIAL"
    return upper


def in_nak_data_counts(records: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count target-facing IN, NAK, and DATA transactions from Beagle records.

    Accepts records with either ``pid_name`` (Beagle JSONL) or the normalized
    ``class_`` field produced by this module. ``DATA0``/``DATA1``/``DATA2``/
    ``MDATA`` all classify as DATA; ``TOKEN_IN`` and ``IN`` count as IN.
    """
    counts = {"IN": 0, "NAK": 0, "DATA": 0}
    for record in records:
        class_ = record.get("class_")
        raw_pid = record.get("pid_name")
        if class_:
            if class_ in ("IN", "TOKEN_IN"):
                counts["IN"] += 1
            elif class_ == "NAK":
                counts["NAK"] += 1
            elif class_ == "DATA":
                counts["DATA"] += 1
        elif raw_pid:
            if raw_pid == "IN":
                counts["IN"] += 1
            elif raw_pid == "NAK":
                counts["NAK"] += 1
            elif classify_pid(raw_pid) == "DATA":
                counts["DATA"] += 1
    return counts


# --------------------------------------------------------------------------- normalized timeline


def normalize_host_transfer(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a host-side USB transfer line into a timeline row.

    Accepts a dict with ``timestamp_utc``/``time``, ``type``/``transfer``,
    ``endpoint``, ``length``, and optional ``report_id``/``payload``.
    """
    ts = record.get("timestamp_utc") or record.get("time") or ""
    return {
        "timestamp_utc": ts,
        "kind": "host_transfer",
        "source": "host",
        "transfer_type": record.get("type") or record.get("transfer") or "unknown",
        "endpoint": record.get("endpoint"),
        "length": record.get("length"),
        "report_id": record.get("report_id"),
        "payload": record.get("payload"),
        "marker": record.get("marker"),
    }


def normalize_target_transaction(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a target-facing Beagle transaction into a timeline row."""
    pid = record.get("class_") or classify_pid(record.get("pid_name"))
    ts = record.get("timestamp_utc") or record.get("time") or record.get("host_timestamp") or ""
    token = decode_token_address(
        int(record.get("token_address") or 0),
        int(record.get("token_endpoint") or 0),
    ) if (record.get("token_address") is not None and record.get("token_endpoint") is not None) else None
    return {
        "timestamp_utc": ts,
        "kind": "target_transaction",
        "source": "target",
        "class_": pid,
        "pid_name": record.get("pid_name"),
        "length": record.get("length"),
        "token": token,
        "data_hex": record.get("data_hex"),
    }


def normalize_app_event(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize an application-state event into a timeline row."""
    return {
        "timestamp_utc": record.get("timestamp_utc") or record.get("time") or "",
        "kind": "app_event",
        "source": "app",
        "event": record.get("event"),
        "state": record.get("state"),
        "marker": record.get("marker"),
    }


def normalize_video_event(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a video/signal-state or screenshot marker into a timeline row."""
    return {
        "timestamp_utc": record.get("timestamp_utc") or record.get("time") or "",
        "kind": "video_event",
        "source": "video",
        "event": record.get("event"),
        "resolution": record.get("resolution"),
        "signal_active": record.get("signal_active"),
        "screenshot": record.get("screenshot"),
        "marker": record.get("marker"),
    }


def normalize_timeline(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize a mixed list of host, target, app, and video records into a
    single sorted timeline. Rows are sorted by ``timestamp_utc`` when present."""
    rows: List[Dict[str, Any]] = []
    for record in records:
        kind = record.get("kind")
        source = record.get("source")
        if kind == "host_transfer" or (source == "host" and not kind):
            rows.append(normalize_host_transfer(record))
        elif kind == "target_transaction" or (source == "target" and not kind):
            rows.append(normalize_target_transaction(record))
        elif kind == "app_event" or (source == "app" and not kind):
            rows.append(normalize_app_event(record))
        elif kind == "video_event" or (source == "video" and not kind):
            rows.append(normalize_video_event(record))
        else:
            rows.append(dict(record))
    rows.sort(key=lambda r: r.get("timestamp_utc") or "")
    return rows


# --------------------------------------------------------------------------- comparison output


def align_by_marker(records: List[Dict[str, Any]], marker_events: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """Partition normalized timeline rows by the synchronized event marker they
    follow, so official-app and AgentKVM2USB sessions can be compared per stage.

    Returns a dict mapping each marker event to the rows recorded after it up to
    the next marker.
    """
    buckets: Dict[str, List[Dict[str, Any]]] = {marker: [] for marker in marker_events}
    current: Optional[str] = None
    for row in records:
        marker = row.get("marker")
        if marker:
            current = marker
        if current:
            buckets.setdefault(current, []).append(row)
    return buckets


def compare_sessions(
    official_rows: List[Dict[str, Any]],
    agent_rows: List[Dict[str, Any]],
    marker_events: List[str],
) -> Dict[str, Any]:
    """Compare the official-app and AgentKVM2USB normalized timelines.

    Produces a sanitized comparison output keyed by stage marker: target IN/NAK/
    DATA counts and any host transfer length/report differences per stage.
    """
    official = align_by_marker(official_rows, marker_events)
    agent = align_by_marker(agent_rows, marker_events)
    comparison: Dict[str, Any] = {"stages": {}, "summary": {}}
    totals = {"official_IN": 0, "official_NAK": 0, "official_DATA": 0,
              "agent_IN": 0, "agent_NAK": 0, "agent_DATA": 0}
    for marker in marker_events:
        o = in_nak_data_counts(official.get(marker, []))
        a = in_nak_data_counts(agent.get(marker, []))
        for key in ("IN", "NAK", "DATA"):
            totals[f"official_{key}"] += o[key]
            totals[f"agent_{key}"] += a[key]
        comparison["stages"][marker] = {
            "official": o,
            "agent": a,
            "data_divergence": o["DATA"] != a["DATA"],
        }
    comparison["summary"] = totals
    comparison["first_divergence_hypothesis"] = (
        "Target-facing IN/NAK with zero DATA in both sessions indicates "
        "forwarding/activation is not happening at the device state level; "
        "a host-side report encoding difference would appear as a different "
        "host transfer payload before the target endpoint."
    )
    return comparison


# --------------------------------------------------------------------------- experiment manifest / gates


def build_manifest(
    *,
    correlation: str,
    operator: str,
    git_commit: Optional[str],
    recovery_base_head: str,
    output_root: Path,
    host_interface: Optional[str],
    target_beagle_port: int,
    usbpcap_present: bool,
    tshark_present: bool,
    beagle_windows_api_present: bool,
    official_app_present: bool,
    target_state_note: str,
    human_authorization_gate: Optional[str],
    markers: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Build the machine-readable experiment manifest.

    ``human_authorization_gate`` must be a non-empty string naming the GitHub
    issue/comment or human action that authorizes the live capture; a live
    capture is refused without it.
    """
    markers = markers or DEFAULT_MARKERS
    return {
        "schema": "manifests/official_app_experiment.schema.yaml",
        "experiment": {
            "id": correlation,
            "objective": (
                "Locate the first divergence between host-side KVM2USB HID "
                "writes and the target-facing USB interrupt endpoint using a "
                "known-good official Epiphan application baseline."
            ),
            "operator": operator,
            "date": correlation.split("-")[-1][:8],
            "git_commit": git_commit,
            "recovery_base_head": recovery_base_head,
        },
        "environment": {
            "host_interface": host_interface,
            "target_beagle_port": target_beagle_port,
            "usbpcap_present": bool(usbpcap_present),
            "tshark_present": bool(tshark_present),
            "beagle_windows_api_present": bool(beagle_windows_api_present),
            "official_app_present": bool(official_app_present),
            "target_state_note": target_state_note,
        },
        "capture": {
            "correlation_id": correlation,
            "output_root": str(output_root),
            "ignored": True,
            "event_markers": markers,
        },
        AUTHORIZATION_GATE_FIELD: human_authorization_gate,
        "prohibited": [
            "unknown vendor OUT control transfers",
            "firmware writes",
            "FPGA writes",
            "EDID writes",
            "flash operations",
            "other persistent-device actions",
        ],
    }


def validate_manifest(manifest: Dict[str, Any]) -> List[str]:
    """Validate a manifest against the required fields. Returns error strings."""
    errors: List[str] = []
    experiment = manifest.get("experiment") or {}
    for field in ("id", "objective", "operator", "date", "git_commit", "recovery_base_head"):
        if not experiment.get(field):
            errors.append(f"experiment.{field} is required")
    capture = manifest.get("capture") or {}
    if not capture.get("correlation_id"):
        errors.append("capture.correlation_id is required")
    if capture.get("ignored") is not True:
        errors.append("capture output must be under an ignored path (capture.ignored == true)")
    markers = capture.get("event_markers") or []
    required_markers = {"app_start", "device_selected", "target_enumeration",
                        "capslock_down", "capslock_up", "ordinary_key_down",
                        "ordinary_key_up", "all_keys_release", "app_close"}
    marker_names = {m.get("event") for m in markers if isinstance(m, dict)}
    missing = sorted(required_markers - marker_names)
    if missing:
        errors.append(f"capture.event_markers missing required markers: {', '.join(missing)}")
    return errors


def live_capture_authorized(manifest: Dict[str, Any]) -> bool:
    """Return True only when an explicit human authorization gate is recorded.

    Generated or default text never satisfies this gate; the field must be a
    non-empty string naming a GitHub issue/comment or human action.
    """
    gate = manifest.get(AUTHORIZATION_GATE_FIELD)
    return isinstance(gate, str) and bool(gate.strip())


def refuse_prohibited(manifest: Dict[str, Any], requested: str) -> bool:
    """Return True when ``requested`` matches a prohibited persistent-device
    operation recorded in the manifest.

    Matching is bidirectional containment so "EDID write" is caught by the
    recorded "EDID writes" item and vice versa. A harmless input like "Caps Lock
    key" does not match any prohibited item.
    """
    requested_lower = requested.lower()
    for item in manifest.get("prohibited") or []:
        item_lower = str(item).lower()
        if requested_lower in item_lower or item_lower in requested_lower:
            return True
    return False
