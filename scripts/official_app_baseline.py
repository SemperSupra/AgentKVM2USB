#!/usr/bin/env python3
"""Official Epiphan-app differential experiment framework.

This module prepares the reproducible, synchronized official-app experiment
needed to locate the first divergence between host-side KVM2USB HID writes and
the target-facing USB interrupt endpoint.

Scope is preparation and analysis only. No live capture or target input is
performed here: the live runner refuses to run unless a structured,
GitHub-linked, experiment-specific, expiring authorization record validates
against current GitHub state (or a locally cached, hash-pinned copy of it).
There is no generic ``--allow-live`` bypass.

Everything in this module is deterministic and independently written. Raw
captures, proprietary binaries, decompiled vendor material, credentials, and
restricted evidence stay outside the public repository under ignored/private
paths; only sanitized manifests, hashes, schemas, procedures, and conclusions
are committed. The merged container toolchain (tools/re) performs decoding and
analysis; this module builds capture commands, correlation state, timelines,
comparison output, and preflight orchestration.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EPIPHAN_VID = "2b77"
KVM2USB3_PID = "3661"
TOTAL_PHASE_VID = "1679"
BEAGLE_USB12_PID = "2001"

# The bounded, reversible input sequence for the baseline experiment.
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

AUTHORIZATION_RECORD_FIELD = "authorization_record"
DEFAULT_PRIVATE_ROOT = ".work/evidence"


# --------------------------------------------------------------------------- correlation / timestamps


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def correlation_id(prefix: str = "official-app", now: Optional[dt.datetime] = None) -> str:
    now = now or utc_now()
    return f"{prefix}-{now.strftime('%Y%m%dT%H%M%SZ')}"


def utc_timestamp(now: Optional[dt.datetime] = None) -> str:
    now = now or utc_now()
    return now.isoformat()


def marker_event(event: str, correlation: str, now: Optional[dt.datetime] = None) -> Dict[str, Any]:
    """Build a synchronized event-marker record.

    This is the single marker contract: a marker row carries ``event``,
    ``kind: marker``, and ``marker`` (identical to ``event``) so generators,
    normalizers, and ``align_by_marker`` all agree.
    """
    return {
        "correlation_id": correlation,
        "event": event,
        "marker": event,
        "timestamp_utc": utc_timestamp(now),
        "kind": "marker",
    }


# --------------------------------------------------------------------------- host capture (USBPcap / Wireshark)


def find_usbpcap_cmd() -> Optional[str]:
    """Locate USBPcapCMD.exe without installing anything."""
    for candidate in ("USBPcapCMD.exe",):
        found = shutil.which(candidate)
        if found:
            return found
    for base in (r"C:\Program Files\USBPcap", r"C:\Program Files (x86)\USBPcap"):
        p = Path(base) / "USBPcapCMD.exe"
        if p.is_file():
            return str(p)
    return None


def usbpcap_interfaces(usbpcap_cmd: Optional[str] = None) -> List[str]:
    """Return the installed USBPcap root-hub/device interfaces by running
    ``USBPcapCMD --extcap-interfaces`` (non-live, safe). Returns an empty list
    when the tool is absent."""
    cmd = usbpcap_cmd or find_usbpcap_cmd()
    if not cmd:
        return []
    try:
        result = subprocess.run([cmd, "--extcap-interfaces"], capture_output=True, text=True, timeout=15, check=False)
    except Exception:
        return []
    if result.returncode != 0:
        return []
    interfaces: List[str] = []
    for line in result.stdout.splitlines():
        # Lines like: interface {value=\\.\USBPcap1}{display=USBPcap device 1}
        match = re.search(r"value=([^}]+)", line)
        if match:
            interfaces.append(match.group(1).strip())
    return interfaces


def usbpcap_command(
    interface: str,
    output: Path,
    *,
    usbpcap_cmd: Optional[str] = None,
    buffer_size_mb: int = 128,
) -> List[str]:
    """Construct a host-facing USBPcap capture command (argv list).

    The capture filter model is a USBPcap root-hub/device selection: the
    operator picks the correct ``\\\\.\\USBPcap<N>`` interface from the
    installed extcap interface list. No libpcap capture filter expression is
    passed; VID/PID filtering happens post-capture during decode with a
    Wireshark display filter.
    """
    argv = [usbpcap_cmd or "USBPcapCMD.exe", "-d", interface, "-o", str(output), "-b", str(buffer_size_mb)]
    return argv


def wireshark_tshark_command(
    interface: str,
    output: Path,
    *,
    tshark_cmd: str = "tshark",
) -> List[str]:
    """Construct a host-facing TShark capture command (argv list).

    ``-f`` capture filters are intentionally avoided for USB bus capture; the
    safe capture is the selected interface, and display filtering uses ``-Y``
    post-capture.
    """
    return [tshark_cmd, "-i", interface, "-w", str(output)]


def host_usb_display_filter(epiphan_vid: str = EPIPHAN_VID, kvm2usb_pid: str = KVM2USB3_PID) -> str:
    """Wireshark display filter (-Y) applied during decode, not capture.

    ``usb.idVendor == 0x2b77 && usb.idProduct == 0x3661`` is valid display-filter
    syntax and is applied post-capture in the analysis step.
    """
    return f"usb.idVendor == 0x{epiphan_vid} && usb.idProduct == 0x{kvm2usb_pid}"


def tshark_decode_command(
    pcap: Path,
    *,
    display_filter: Optional[str] = None,
    tshark_cmd: str = "tshark",
    output: Optional[Path] = None,
) -> List[str]:
    """Construct a post-capture TShark decode command using a display filter."""
    argv = [tshark_cmd, "-r", str(pcap)]
    if display_filter:
        argv += ["-Y", display_filter]
    if output:
        argv += ["-w", str(output)]
    else:
        argv += ["-T", "json"]
    return argv


def find_tshark() -> Optional[str]:
    found = shutil.which("tshark")
    return found or None


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
    """Construct a target-facing Beagle USB 12 capture command (argv list)."""
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


def decode_descriptor_endpoint_address(endpoint_address: int) -> Dict[str, int]:
    """Decode a USB *descriptor* endpoint-address byte into number + direction.

    This is descriptor-field decoding only. The IN/OUT direction comes from bit
    7 of the descriptor endpoint address, NOT from a token field. Token
    direction is derived separately from the token PID (see
    ``token_direction_from_pid``).
    """
    return {
        "endpoint_number": endpoint_address & 0x0F,
        "direction": "IN" if (endpoint_address & 0x80) else "OUT",
    }


def token_direction_from_pid(pid_name: Optional[str]) -> Optional[str]:
    """Return the USB token direction from the token PID.

    IN/OUT/SETUP are token PIDs; the direction is carried by the PID, not by any
    endpoint bit. DATA tokens have no token direction.
    """
    upper = (pid_name or "").upper()
    if upper == "IN":
        return "IN"
    if upper == "OUT":
        return "OUT"
    if upper == "SETUP":
        return "SETUP"
    return None


def classify_pid(pid_name: Optional[str]) -> str:
    """Classify a USB PID into a normalized bucket.

    Token PIDs are preserved as ``TOKEN_IN``/``TOKEN_OUT``/``TOKEN_SETUP`` so
    token identity survives normalization and counting.
    """
    if not pid_name:
        return "EVENT_ONLY"
    upper = pid_name.upper()
    if upper == "IN":
        return "TOKEN_IN"
    if upper == "OUT":
        return "TOKEN_OUT"
    if upper == "SETUP":
        return "TOKEN_SETUP"
    if upper in ("DATA0", "DATA1", "DATA2", "MDATA"):
        return "DATA"
    if upper in ("ACK", "NAK", "STALL", "NYET"):
        return "HANDSHAKE"
    if upper in ("SOF", "PRE", "SPLIT", "PING"):
        return "SPECIAL"
    return upper


def in_nak_data_counts(records: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count target-facing IN, NAK, and DATA transactions from Beagle records.

    Accepts records with ``pid_name`` (Beagle JSONL) or the normalized ``class_``
    field. ``TOKEN_IN``/``TOKEN_OUT``/``TOKEN_SETUP`` are preserved.
    """
    counts = {"IN": 0, "OUT": 0, "SETUP": 0, "NAK": 0, "DATA": 0}
    for record in records:
        class_ = record.get("class_")
        if class_:
            if class_ == "TOKEN_IN":
                counts["IN"] += 1
            elif class_ == "TOKEN_OUT":
                counts["OUT"] += 1
            elif class_ == "TOKEN_SETUP":
                counts["SETUP"] += 1
            elif class_ == "NAK":
                counts["NAK"] += 1
            elif class_ == "DATA":
                counts["DATA"] += 1
        else:
            raw = record.get("pid_name")
            if raw == "IN":
                counts["IN"] += 1
            elif raw == "OUT":
                counts["OUT"] += 1
            elif raw == "SETUP":
                counts["SETUP"] += 1
            elif raw == "NAK":
                counts["NAK"] += 1
            elif classify_pid(raw) == "DATA":
                counts["DATA"] += 1
    return counts


# --------------------------------------------------------------------------- normalized timeline


def normalize_host_transfer(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a host-side USB transfer line into a timeline row."""
    ts = record.get("timestamp_utc") or record.get("time") or ""
    return {
        "timestamp_utc": ts,
        "kind": "host_transfer",
        "source": "host",
        "transfer_type": record.get("type") or record.get("transfer") or "unknown",
        "collection": record.get("collection") or record.get("interface"),
        "endpoint": record.get("endpoint"),
        "length": record.get("length"),
        "report_id": record.get("report_id"),
        "payload": record.get("payload"),
        "marker": record.get("marker"),
        "preceding_control": record.get("preceding_control"),
        "preceding_feature": record.get("preceding_feature"),
    }


def normalize_target_transaction(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a target-facing Beagle transaction into a timeline row.

    Token direction is derived from the PID (``token_direction_from_pid``),
    never from an endpoint bit. Descriptor endpoint addresses, when present, are
    decoded separately by ``decode_descriptor_endpoint_address``.
    """
    pid_name = record.get("pid_name")
    class_ = record.get("class_") or classify_pid(pid_name)
    ts = record.get("timestamp_utc") or record.get("time") or record.get("host_timestamp") or ""
    token_address = record.get("token_address")
    token_endpoint = record.get("token_endpoint")
    token = None
    if token_address is not None and token_endpoint is not None:
        token = {
            "address": int(token_address) & 0x7F,
            "endpoint_number": int(token_endpoint) & 0x0F,
            # Direction from PID only; the endpoint field is a number, not a
            # direction-bearing address.
            "direction": token_direction_from_pid(pid_name),
        }
    return {
        "timestamp_utc": ts,
        "kind": "target_transaction",
        "source": "target",
        "class_": class_,
        "pid_name": pid_name,
        "token_direction": token_direction_from_pid(pid_name),
        "length": record.get("length"),
        "token": token,
        "data_hex": record.get("data_hex"),
        "marker": record.get("marker"),
    }


def normalize_app_event(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "timestamp_utc": record.get("timestamp_utc") or record.get("time") or "",
        "kind": "app_event",
        "source": "app",
        "event": record.get("event"),
        "state": record.get("state"),
        "marker": record.get("marker"),
    }


def normalize_video_event(record: Dict[str, Any]) -> Dict[str, Any]:
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
    single sorted timeline."""
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
    follow. A marker row carries both ``marker`` and ``event`` (the unified
    contract), so this works end-to-end with ``marker_event()``."""
    buckets: Dict[str, List[Dict[str, Any]]] = {marker: [] for marker in marker_events}
    current: Optional[str] = None
    for row in records:
        marker = row.get("marker") or row.get("event") if row.get("kind") == "marker" else row.get("marker")
        if marker:
            current = marker
        if current:
            buckets.setdefault(current, []).append(row)
    return buckets


def _first_host_divergence(official_rows: List[Dict[str, Any]], agent_rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Identify the first host-side divergence between official and agent rows.

    Compares transfer type, collection/interface, endpoint, report ID, length,
    payload, preceding control/feature transfers, and timing.
    """
    fields = ("transfer_type", "collection", "endpoint", "report_id", "length",
              "payload", "preceding_control", "preceding_feature")
    max_len = max(len(official_rows), len(agent_rows))
    for i in range(max_len):
        o = official_rows[i] if i < len(official_rows) else {}
        a = agent_rows[i] if i < len(agent_rows) else {}
        for field in fields:
            if o.get(field) != a.get(field):
                return {
                    "index": i,
                    "side": "host",
                    "field": field,
                    "official": o.get(field),
                    "agent": a.get(field),
                    "timestamp_official": o.get("timestamp_utc"),
                    "timestamp_agent": a.get("timestamp_utc"),
                }
    return None


def compare_sessions(
    official_rows: List[Dict[str, Any]],
    agent_rows: List[Dict[str, Any]],
    marker_events: List[str],
) -> Dict[str, Any]:
    """Compare the official-app and AgentKVM2USB normalized timelines.

    Compares both host-side and target-side per stage and identifies the first
    host-side or target-side divergence.
    """
    official = align_by_marker(official_rows, marker_events)
    agent = align_by_marker(agent_rows, marker_events)
    comparison: Dict[str, Any] = {"stages": {}, "summary": {}}
    totals = {f"{side}_{key}": 0 for side in ("official", "agent") for key in ("IN", "OUT", "SETUP", "NAK", "DATA")}
    first_divergence: Optional[Dict[str, Any]] = None
    for marker in marker_events:
        o_host = [r for r in official.get(marker, []) if r.get("kind") == "host_transfer"]
        a_host = [r for r in agent.get(marker, []) if r.get("kind") == "host_transfer"]
        o_tgt = [r for r in official.get(marker, []) if r.get("kind") == "target_transaction"]
        a_tgt = [r for r in agent.get(marker, []) if r.get("kind") == "target_transaction"]
        o_counts = in_nak_data_counts(o_tgt)
        a_counts = in_nak_data_counts(a_tgt)
        for key in ("IN", "OUT", "SETUP", "NAK", "DATA"):
            totals[f"official_{key}"] += o_counts[key]
            totals[f"agent_{key}"] += a_counts[key]
        host_div = _first_host_divergence(o_host, a_host)
        target_div = None
        for key in ("IN", "OUT", "SETUP", "NAK", "DATA"):
            if o_counts[key] != a_counts[key]:
                target_div = {"side": "target", "field": key,
                              "official": o_counts[key], "agent": a_counts[key]}
                break
        if first_divergence is None:
            first_divergence = host_div or target_div
        comparison["stages"][marker] = {
            "official": o_counts,
            "agent": a_counts,
            "host_divergence": host_div,
            "target_divergence": target_div,
        }
    comparison["summary"] = totals
    comparison["first_divergence"] = first_divergence
    return comparison


# --------------------------------------------------------------------------- output path validation


def resolve_output_path(raw: str, private_root: str = DEFAULT_PRIVATE_ROOT, repo_root: Optional[Path] = None) -> Path:
    """Resolve a capture output path and require containment under an approved
    ignored/private root.

    ``repo_root`` defaults to the repository root. Returns the resolved absolute
    path. Raises ValueError when the path escapes the approved root.
    """
    root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    approved = (root / private_root).resolve()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (root / path).resolve()
    else:
        path = path.resolve()
    try:
        path.relative_to(approved)
    except ValueError:
        raise ValueError(f"capture output path {path} is not under approved root {approved}")
    return path


def path_is_git_ignored(path: Path, repo_root: Optional[Path] = None) -> bool:
    """Check whether the resolved path is git-ignored using ``git check-ignore``."""
    root = (repo_root or Path(__file__).resolve().parents[1])
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", str(path)],
            cwd=root, capture_output=True, text=True, timeout=15, check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def verify_output_path(raw: str, private_root: str = DEFAULT_PRIVATE_ROOT, repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Resolve and verify a capture output path under an approved ignored root.

    Returns ``{"ok": bool, "resolved": str, "git_ignored": bool, "errors": [...]}``.
    """
    errors: List[str] = []
    try:
        resolved = resolve_output_path(raw, private_root, repo_root)
    except ValueError as exc:
        return {"ok": False, "resolved": None, "git_ignored": False, "errors": [str(exc)]}
    git_ignored = path_is_git_ignored(resolved, repo_root)
    if not git_ignored:
        errors.append(f"resolved path {resolved} is not git-ignored")
    return {"ok": not errors, "resolved": str(resolved), "git_ignored": git_ignored, "errors": errors}


# --------------------------------------------------------------------------- structured authorization


def build_authorization_record(
    *,
    canonical_issue: int,
    comment_id: str,
    comment_url: str,
    author: str,
    authority: str,
    experiment_id: str,
    allowed_input_sequence: List[str],
    target: str,
    issued_utc: str,
    expires_utc: str,
) -> Dict[str, Any]:
    """Build a structured, GitHub-linked, experiment-specific, expiring
    authorization record. The live runner validates this against current GitHub
    state (or a locally cached, hash-pinned copy)."""
    return {
        "canonical_issue": canonical_issue,
        "comment_id": comment_id,
        "comment_url": comment_url,
        "author": author,
        "authority": authority,
        "experiment_id": experiment_id,
        "allowed_input_sequence": list(allowed_input_sequence),
        "target": target,
        "issued_utc": issued_utc,
        "expires_utc": expires_utc,
    }


def live_capture_authorized(
    record: Optional[Dict[str, Any]],
    *,
    experiment_id: str,
    now_utc: Optional[dt.datetime] = None,
) -> Tuple[bool, str]:
    """Validate a structured authorization record for live capture.

    Returns ``(ok, reason)``. A generic nonempty string is never sufficient:
    the record must be structured, GitHub-linked, experiment-specific, and not
    expired.
    """
    if not isinstance(record, dict):
        return False, "no structured authorization record"
    required = ("canonical_issue", "comment_id", "comment_url", "author", "authority",
                "experiment_id", "allowed_input_sequence", "target", "issued_utc", "expires_utc")
    for field in required:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            return False, f"authorization record missing required field: {field}"
    if str(record.get("experiment_id")) != str(experiment_id):
        return False, f"authorization experiment_id {record.get('experiment_id')!r} != {experiment_id!r}"
    if "generated default authorization" in str(record.get("authority") or "").lower():
        return False, "generic generated authority does not authorize live capture"
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    try:
        issued = dt.datetime.fromisoformat(str(record["issued_utc"]).replace("Z", "+00:00"))
        expires = dt.datetime.fromisoformat(str(record["expires_utc"]).replace("Z", "+00:00"))
    except ValueError:
        return False, "authorization timestamps must be ISO-8601"
    if now < issued:
        return False, "authorization not yet valid"
    if now >= expires:
        return False, f"authorization expired at {record['expires_utc']}"
    return True, "structured authorization record valid"


# --------------------------------------------------------------------------- experiment manifest / gates


def build_manifest(
    *,
    correlation: str,
    operator: str,
    git_commit: Optional[str],
    recovery_base_head: str,
    output_root: str,
    host_interface: Optional[str],
    target_beagle_port: int,
    usbpcap_present: bool,
    tshark_present: bool,
    beagle_windows_api_present: bool,
    official_app_present: bool,
    target_state_note: str,
    authorization_record: Optional[Dict[str, Any]],
    markers: Optional[List[Dict[str, str]]] = None,
    private_root: str = DEFAULT_PRIVATE_ROOT,
) -> Dict[str, Any]:
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
            "output_root": output_root,
            "private_root": private_root,
            "event_markers": markers,
        },
        AUTHORIZATION_RECORD_FIELD: authorization_record,
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
    markers = capture.get("event_markers") or []
    required_markers = {"app_start", "device_selected", "target_enumeration",
                        "capslock_down", "capslock_up", "ordinary_key_down",
                        "ordinary_key_up", "all_keys_release", "app_close"}
    marker_names = {m.get("event") for m in markers if isinstance(m, dict)}
    missing = sorted(required_markers - marker_names)
    if missing:
        errors.append(f"capture.event_markers missing required markers: {', '.join(missing)}")
    return errors


def refuse_prohibited(manifest: Dict[str, Any], requested: str) -> bool:
    """Return True when ``requested`` matches a prohibited persistent-device
    operation recorded in the manifest."""
    requested_lower = requested.lower()
    for item in manifest.get("prohibited") or []:
        item_lower = str(item).lower()
        if requested_lower in item_lower or item_lower in requested_lower:
            return True
    return False


# --------------------------------------------------------------------------- no-live preflight orchestration


def preflight(
    *,
    repo_root: Optional[Path] = None,
    output_root: str = ".work/evidence",
    target_beagle_port: int = 0,
    host_interface: Optional[str] = None,
) -> Dict[str, Any]:
    """No-live workstation preflight/orchestration.

    Detects the official app/driver, USBPcap/extcap, TShark, Beagle API/driver,
    USB identities, disk space, capture interface/root hub, target state, and
    physical topology; generates the manifest and exact commands; and stops with
    ``HUMAN ACTION REQUIRED`` for elevation, installation, recabling, or target
    interaction. Live execution stays disabled.
    """
    root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    usbpcap_cmd = find_usbpcap_cmd()
    tshark = find_tshark()
    interfaces = usbpcap_interfaces(usbpcap_cmd) if usbpcap_cmd else []
    disk = shutil.disk_usage(str(root))
    official_app_present = _detect_official_app()
    beagle_api_present = _detect_beagle_windows_api(root)

    issues: List[str] = []
    if not usbpcap_cmd:
        issues.append("USBPcapCMD not found; install USBPcap (elevated, HUMAN ACTION REQUIRED)")
    if not tshark:
        issues.append("TShark not found; install Wireshark/USBPcap (elevated, HUMAN ACTION REQUIRED)")
    if not interfaces:
        issues.append("no USBPcap extcap interface detected; verify USBPcap installation and root-hub selection")
    if not official_app_present:
        issues.append("official Epiphan application/driver not detected")
    if not beagle_api_present:
        issues.append("Total Phase Beagle Windows API/driver not detected")
    if disk.free < 2 * 1024 * 1024 * 1024:
        issues.append(f"insufficient disk space: {disk.free} bytes free")

    human_actions: List[str] = []
    if not usbpcap_cmd or not tshark:
        human_actions.append("install USBPcap and Wireshark (elevated); do not automate privileged installation")
    if not official_app_present:
        human_actions.append("install the official Epiphan application/driver")
    if not beagle_api_present:
        human_actions.append("install the Total Phase Beagle Windows driver/API")
    if not interfaces:
        human_actions.append("select the correct USBPcap root-hub/device interface after installation")

    return {
        "ok": not issues,
        "detected": {
            "usbpcap_cmd": usbpcap_cmd,
            "tshark": tshark,
            "usbpcap_interfaces": interfaces,
            "official_app_present": official_app_present,
            "beagle_windows_api_present": beagle_api_present,
            "disk_free_bytes": disk.free,
        },
        "issues": issues,
        "human_actions": human_actions,
        "host_interface": host_interface or (interfaces[0] if interfaces else None),
        "commands": {
            "usbpcap": usbpcap_command(interfaces[0], Path(output_root) / "host.pcap") if interfaces else [],
            "beagle": beagle_command(Path(output_root) / "target.jsonl",
                                     api_dir=Path(output_root)) if beagle_api_present else [],
        },
        "live_disabled": True,
        "authorization_required": "a structured, GitHub-linked, expiring authorization record",
    }


def _detect_official_app() -> bool:
    """Detect the official Epiphan KVM App by common install locations. Never
    installs anything."""
    candidates = [
        r"C:\Program Files\Epiphan\KVM2USB",
        r"C:\Program Files (x86)\Epiphan\KVM2USB",
        r"C:\Program Files\Epiphan KVM",
    ]
    return any(Path(p).exists() for p in candidates)


def _detect_beagle_windows_api(root: Path) -> bool:
    """Detect a staged Total Phase Windows Beagle API under .work/vendor."""
    base = root / ".work" / "vendor" / "totalphase"
    if not base.exists():
        return False
    return any(base.rglob("beagle_py.py")) or any(base.rglob("beagle.dll"))
