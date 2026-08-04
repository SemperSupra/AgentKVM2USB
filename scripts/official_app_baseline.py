#!/usr/bin/env python3
"""Official Epiphan-app differential experiment framework.

This module prepares the reproducible, synchronized official-app experiment
needed to locate the first divergence between host-side KVM2USB HID writes and
the target-facing USB interrupt endpoint.

Scope is preparation and analysis only. No live capture or target input is
performed here. Live execution is gated by a structured, GitHub-linked,
experiment-specific, expiring authorization record that must be fetched from
GitHub (or consumed from a cached, hash-pinned evidence envelope produced from
that fetch). A caller-assembled dictionary alone never authorizes live work, and
there is no generic ``--allow-live`` or ``--force-live`` bypass.

A no-live CLI provides:

- ``preflight`` — detect tools/drivers/devices/topology/interfaces/disk and emit
  the exact HUMAN ACTION REQUIRED steps; never select a USBPcap interface
  silently;
- ``build-manifest`` — emit the machine-readable experiment manifest;
- ``ingest-authorization`` — fetch the exact issue comment via ``gh api`` (or a
  supplied cached evidence envelope) and write a hash-pinned envelope;
- ``verify-authorization`` — validate a cached evidence envelope without live
  capture.

The merged container toolchain (tools/re) performs decoding and analysis; this
module builds capture commands, correlation state, timelines, comparison
output, timing comparison, and preflight orchestration.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
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
SCHEMA_PATH = "manifests/official_app_experiment.schema.yaml"

# Documented timing comparison tolerance (seconds). Timing divergence is reported
# independently of payload/endpoint/transfer-shape/target-count divergence.
DEFAULT_TIMING_TOLERANCE_SECONDS = 0.05


# --------------------------------------------------------------------------- schema contract helpers


def load_schema(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Load the manifest schema YAML into a dict (structural parse; no PyYAML
    dependency). The schema is the single source of truth for required fields.

    Handles the two-space YAML layout used by this schema: top-level ``required``
    list items are at indent 2 (``  - field``) and top-level ``fields`` map keys
    are at indent 2 (``  key:``). Nested ``required`` lists inside a section are
    at indent 4/6 and are read into that section's ``required`` list.
    """
    root = (repo_root or Path(__file__).resolve().parents[1])
    text = (root / SCHEMA_PATH).read_text(encoding="utf-8")
    data: Dict[str, Any] = {"required": [], "fields": {}}
    # Track the two structural lists/maps by their indentation depth.
    # Top-level: `required:` at indent 0 with `  - item` items at indent 2;
    # `fields:` at indent 0 with `  key:` map entries at indent 2, and nested
    # `required:` lists at indent 4 whose items are at indent 6.
    top_required_depth: Optional[int] = None        # depth of the top `required:` key
    field_key_depth: Optional[int] = None           # depth of a `key:` under a section
    required_items_depth: Optional[int] = None      # depth of `- item` in a required list
    current_section: Optional[str] = None
    section_required_depth: Optional[int] = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if indent == 0:
            top_required_depth = None
            field_key_depth = None
            required_items_depth = None
            current_section = None
            section_required_depth = None
            if stripped == "required:":
                top_required_depth = 0
            elif stripped == "fields:":
                field_key_depth = 2
            continue

        if top_required_depth is not None:
            if stripped.startswith("- ") and indent == top_required_depth + 2:
                data["required"].append(stripped[2:].strip())
            elif not stripped.startswith("- ") and not stripped.endswith(":"):
                pass  # ignore other content in the top required list
            continue

        if field_key_depth is not None:
            if indent == field_key_depth and stripped.endswith(":"):
                key = stripped.rstrip(":").strip()
                data["fields"].setdefault(key, {})
                current_section = key
                section_required_depth = None
                required_items_depth = None
            elif indent == field_key_depth + 2 and stripped == "required:":
                section_required_depth = field_key_depth + 2
            elif section_required_depth is not None and indent == section_required_depth + 2 and stripped.startswith("- "):
                value = stripped[2:].strip()
                if current_section:
                    data["fields"].setdefault(current_section, {}).setdefault("required", []).append(value)
            continue
    return data


def schema_required_top_level(repo_root: Optional[Path] = None) -> List[str]:
    return load_schema(repo_root).get("required", [])


def schema_auth_required_fields(repo_root: Optional[Path] = None) -> List[str]:
    """Authorization-record required fields derived from the schema, not a
    hand-maintained duplicate list."""
    schema = load_schema(repo_root)
    auth = (schema.get("fields") or {}).get("authorization_record") or {}
    return auth.get("required", [])


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
    """Build a synchronized event-marker record. Sets both ``event`` and
    ``marker`` (kind: marker) so generators, normalizers, and alignment agree."""
    return {
        "correlation_id": correlation,
        "event": event,
        "marker": event,
        "timestamp_utc": utc_timestamp(now),
        "kind": "marker",
    }


# --------------------------------------------------------------------------- host capture (USBPcap / Wireshark)


def find_usbpcap_cmd() -> Optional[str]:
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
    """Construct a host-facing USBPcap capture command (argv list) for the
    explicitly selected root-hub/device interface. No libpcap capture filter."""
    argv = [usbpcap_cmd or "USBPcapCMD.exe", "-d", interface, "-o", str(output), "-b", str(buffer_size_mb)]
    return argv


def wireshark_tshark_command(interface: str, output: Path, *, tshark_cmd: str = "tshark") -> List[str]:
    return [tshark_cmd, "-i", interface, "-w", str(output)]


def host_usb_display_filter(epiphan_vid: str = EPIPHAN_VID, kvm2usb_pid: str = KVM2USB3_PID) -> str:
    return f"usb.idVendor == 0x{epiphan_vid} && usb.idProduct == 0x{kvm2usb_pid}"


def tshark_decode_command(
    pcap: Path,
    *,
    display_filter: Optional[str] = None,
    tshark_cmd: str = "tshark",
    output: Optional[Path] = None,
) -> List[str]:
    argv = [tshark_cmd, "-r", str(pcap)]
    if display_filter:
        argv += ["-Y", display_filter]
    if output:
        argv += ["-w", str(output)]
    else:
        argv += ["-T", "json"]
    return argv


def find_tshark() -> Optional[str]:
    return shutil.which("tshark") or None


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

    ``api_dir`` must be the detected Total Phase Windows Beagle API directory,
    never the evidence output root.
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


def find_beagle_windows_api_dir(repo_root: Optional[Path] = None) -> Optional[Path]:
    """Return the detected Total Phase Windows Beagle API directory (contains
    beagle_py.py), or None. Never returns the evidence root."""
    root = (repo_root or Path(__file__).resolve().parents[1])
    base = root / ".work" / "vendor" / "totalphase"
    if not base.exists():
        return None
    for py in base.rglob("beagle_py.py"):
        return py.parent
    return None


# --------------------------------------------------------------------------- descriptor / endpoint decoding


def decode_descriptor_endpoint_address(endpoint_address: int) -> Dict[str, int]:
    """Decode a USB *descriptor* endpoint-address byte. Direction comes from bit
    7 of the descriptor field only."""
    return {
        "endpoint_number": endpoint_address & 0x0F,
        "direction": "IN" if (endpoint_address & 0x80) else "OUT",
    }


def token_direction_from_pid(pid_name: Optional[str]) -> Optional[str]:
    upper = (pid_name or "").upper()
    if upper == "IN":
        return "IN"
    if upper == "OUT":
        return "OUT"
    if upper == "SETUP":
        return "SETUP"
    return None


def classify_pid(pid_name: Optional[str]) -> str:
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


# --------------------------------------------------------------------------- timing comparison


def _ts_seconds(value: Any) -> Optional[float]:
    """Parse an ISO-8601 timestamp into epoch seconds, or None."""
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = dt.datetime.fromisoformat(str(value))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.timestamp()


def stage_timing_metrics(
    rows: List[Dict[str, Any]],
    *,
    marker_events: List[str],
    tolerance: float = DEFAULT_TIMING_TOLERANCE_SECONDS,
) -> Dict[str, Any]:
    """Compute per-stage relative timing metrics for a single session.

    Returns a dict of named timing metrics measured in seconds:
    ``init_to_first_report``, ``marker_to_host_transfer``,
    ``host_to_target_data_or_nak``, ``report_down_to_up``, and
    ``all_keys_release`` (delta to the following stage when present).
    """
    metrics: Dict[str, Any] = {}
    buckets = align_by_marker(rows, marker_events)
    for stage in ("app_start", "capslock_down", "ordinary_key_down", "all_keys_release"):
        bucket = buckets.get(stage, [])
        timestamps = [_ts_seconds(r.get("timestamp_utc")) for r in bucket]
        timestamps = [t for t in timestamps if t is not None]
        if stage == "app_start" and timestamps:
            metrics["init_to_first_report"] = round(timestamps[0] - timestamps[0], 6)
        if stage == "capslock_down" and timestamps:
            down = timestamps[0]
            up = None
            for r in bucket:
                if r.get("marker") == "capslock_up":
                    up = _ts_seconds(r.get("timestamp_utc"))
            metrics["report_down_to_up"] = round((up - down), 6) if up else None
        # host-transfer to target DATA/NAK within the stage
        host_ts = None
        target_ts = None
        for r in bucket:
            if r.get("kind") == "host_transfer" and host_ts is None:
                host_ts = _ts_seconds(r.get("timestamp_utc"))
            elif r.get("kind") == "target_transaction" and target_ts is None:
                if r.get("class_") in ("DATA", "HANDSHAKE") or r.get("pid_name") in ("DATA0", "DATA1", "DATA2", "MDATA", "NAK"):
                    target_ts = _ts_seconds(r.get("timestamp_utc"))
        if host_ts is not None and target_ts is not None:
            metrics["host_to_target_data_or_nak"] = round(target_ts - host_ts, 6)
        # marker to first host transfer in the stage
        marker_ts = None
        first_host_ts = None
        for r in bucket:
            if r.get("kind") == "marker" and marker_ts is None:
                marker_ts = _ts_seconds(r.get("timestamp_utc"))
            elif r.get("kind") == "host_transfer" and first_host_ts is None:
                first_host_ts = _ts_seconds(r.get("timestamp_utc"))
        if marker_ts is not None and first_host_ts is not None:
            metrics["marker_to_host_transfer"] = round(first_host_ts - marker_ts, 6)
    metrics["tolerance_seconds"] = tolerance
    return metrics


def compare_timing(
    official_rows: List[Dict[str, Any]],
    agent_rows: List[Dict[str, Any]],
    marker_events: List[str],
    tolerance: float = DEFAULT_TIMING_TOLERANCE_SECONDS,
) -> Dict[str, Any]:
    """Compare official vs agent per-stage timing metrics.

    Reports the first timing divergence independently of payload/endpoint/
    transfer-shape/target-count divergence. A metric diverges when the absolute
    delta exceeds ``tolerance`` seconds.
    """
    official_metrics = stage_timing_metrics(official_rows, marker_events=marker_events, tolerance=tolerance)
    agent_metrics = stage_timing_metrics(agent_rows, marker_events=marker_events, tolerance=tolerance)
    divergences: List[Dict[str, Any]] = []
    for key in ("init_to_first_report", "marker_to_host_transfer",
                "host_to_target_data_or_nak", "report_down_to_up", "all_keys_release"):
        o = official_metrics.get(key)
        a = agent_metrics.get(key)
        if o is None or a is None:
            continue
        if abs(o - a) > tolerance:
            divergences.append({"metric": key, "official_s": o, "agent_s": a, "delta_s": round(o - a, 6)})
    return {
        "official": official_metrics,
        "agent": agent_metrics,
        "first_timing_divergence": divergences[0] if divergences else None,
        "timing_divergences": divergences,
        "tolerance_seconds": tolerance,
    }


# --------------------------------------------------------------------------- comparison output


def align_by_marker(records: List[Dict[str, Any]], marker_events: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    buckets: Dict[str, List[Dict[str, Any]]] = {marker: [] for marker in marker_events}
    current: Optional[str] = None
    for row in records:
        marker = row.get("marker") or (row.get("event") if row.get("kind") == "marker" else None)
        if marker:
            current = marker
        if current:
            buckets.setdefault(current, []).append(row)
    return buckets


def _first_host_divergence(official_rows: List[Dict[str, Any]], agent_rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    fields = ("transfer_type", "collection", "endpoint", "report_id", "length",
              "payload", "preceding_control", "preceding_feature")
    max_len = max(len(official_rows), len(agent_rows))
    for i in range(max_len):
        o = official_rows[i] if i < len(official_rows) else {}
        a = agent_rows[i] if i < len(agent_rows) else {}
        for field in fields:
            if o.get(field) != a.get(field):
                return {
                    "index": i, "side": "host", "field": field,
                    "official": o.get(field), "agent": a.get(field),
                }
    return None


def compare_sessions(
    official_rows: List[Dict[str, Any]],
    agent_rows: List[Dict[str, Any]],
    marker_events: List[str],
    timing_tolerance: float = DEFAULT_TIMING_TOLERANCE_SECONDS,
) -> Dict[str, Any]:
    """Compare official and agent timelines, including timing.

    Returns stage target counts, host divergence, target divergence, the first
    host/target divergence, and an independent timing comparison.
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
            "official": o_counts, "agent": a_counts,
            "host_divergence": host_div, "target_divergence": target_div,
        }
    comparison["summary"] = totals
    comparison["first_divergence"] = first_divergence
    comparison["timing"] = compare_timing(official_rows, agent_rows, marker_events, timing_tolerance)
    return comparison


# --------------------------------------------------------------------------- output path validation


def resolve_output_path(raw: str, private_root: str = DEFAULT_PRIVATE_ROOT, repo_root: Optional[Path] = None) -> Path:
    root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    approved = (root / private_root).resolve()
    path = Path(raw).expanduser()
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    try:
        path.relative_to(approved)
    except ValueError:
        raise ValueError(f"capture output path {path} is not under approved root {approved}")
    return path


def path_is_git_ignored(path: Path, repo_root: Optional[Path] = None) -> bool:
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
    errors: List[str] = []
    try:
        resolved = resolve_output_path(raw, private_root, repo_root)
    except ValueError as exc:
        return {"ok": False, "resolved": None, "git_ignored": False, "errors": [str(exc)]}
    git_ignored = path_is_git_ignored(resolved, repo_root)
    if not git_ignored:
        errors.append(f"resolved path {resolved} is not git-ignored")
    return {"ok": not errors, "resolved": str(resolved), "git_ignored": git_ignored, "errors": errors}


# --------------------------------------------------------------------------- GitHub-backed authorization


def canonicalize_evidence(envelope: Dict[str, Any]) -> bytes:
    """Canonicalize an evidence envelope into stable bytes for hashing.

    Uses the canonical JSON form (sorted keys) of the envelope's core fields so
    the SHA-256 is reproducible and independent of dict ordering.
    """
    core = {k: envelope.get(k) for k in (
        "repository", "issue", "comment_id", "comment_url", "comment_body",
        "github_author", "fetched_utc", "experiment_id", "target",
        "allowed_input_sequence", "issued_utc", "expires_utc",
    )}
    return json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_evidence(envelope: Dict[str, Any]) -> str:
    return hashlib.sha256(canonicalize_evidence(envelope)).hexdigest()


def fetch_issue_comment(repository: str, comment_id: str) -> Dict[str, Any]:
    """Fetch the exact issue comment through authenticated ``gh api``.

    Raises RuntimeError on failure. No live capture is involved.
    """
    url = f"repos/{repository}/issues/comments/{comment_id}"
    try:
        result = subprocess.run(
            ["gh", "api", url, "--jq", "{id, body, html_url, user: .user.login, created_at}"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except Exception as exc:
        raise RuntimeError(f"gh api failed: {exc}") from exc
    if result.returncode != 0:
        raise RuntimeError(f"gh api failed: {result.stderr.strip() or result.stdout.strip()}")
    return json.loads(result.stdout)


def build_evidence_envelope(
    *,
    repository: str,
    issue: int,
    comment_id: str,
    comment_url: str,
    comment_body: str,
    github_author: str,
    fetched_utc: str,
    experiment_id: str,
    target: str,
    allowed_input_sequence: List[str],
    issued_utc: str,
    expires_utc: str,
) -> Dict[str, Any]:
    """Build a cached evidence envelope produced from a GitHub fetch (or a
    supplied fetch result). The envelope carries a SHA-256 of the canonicalized
    evidence so a later verify can confirm it was not tampered with."""
    envelope = {
        "repository": repository,
        "issue": issue,
        "comment_id": comment_id,
        "comment_url": comment_url,
        "comment_body": comment_body,
        "github_author": github_author,
        "fetched_utc": fetched_utc,
        "experiment_id": experiment_id,
        "target": target,
        "allowed_input_sequence": list(allowed_input_sequence),
        "issued_utc": issued_utc,
        "expires_utc": expires_utc,
    }
    envelope["evidence_sha256"] = sha256_evidence(envelope)
    return envelope


def ingest_authorization(
    *,
    repository: str,
    issue: int,
    comment_id: str,
    comment_url: str,
    experiment_id: str,
    target: str,
    allowed_input_sequence: List[str],
    issued_utc: str,
    expires_utc: str,
    fetched: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ingest an authorization by fetching the exact issue comment via gh api
    (or consuming a supplied fetch result) and returning a hash-pinned envelope.

    A caller-assembled dictionary that has not been fetched is rejected.
    """
    if fetched is None:
        fetched = fetch_issue_comment(repository, comment_id)
    comment_body = fetched.get("body") or ""
    github_author = fetched.get("user") or ""
    fetched_url = fetched.get("html_url") or ""
    if comment_url and fetched_url and comment_url != fetched_url:
        raise ValueError("comment_url does not match the fetched GitHub comment URL")
    return build_evidence_envelope(
        repository=repository,
        issue=issue,
        comment_id=str(fetched.get("id") or comment_id),
        comment_url=fetched_url or comment_url,
        comment_body=comment_body,
        github_author=github_author,
        fetched_utc=utc_timestamp(),
        experiment_id=experiment_id,
        target=target,
        allowed_input_sequence=allowed_input_sequence,
        issued_utc=issued_utc,
        expires_utc=expires_utc,
    )


def verify_authorization(
    envelope: Dict[str, Any],
    *,
    experiment_id: str,
    repository: str,
    issue: int,
    human_authority: str,
    now_utc: Optional[dt.datetime] = None,
) -> Tuple[bool, str]:
    """Validate a cached evidence envelope against GitHub-derived evidence.

    Confirms: repository/issue/comment agreement; the fetched comment body
    explicitly authorizes the exact experiment ID; target and allowed input
    sequence match; the authorization has not expired; the GitHub author matches
    the recorded human authority; and the envelope hash is valid.

    A fabricated caller-assembled dictionary without a valid hash-pinned
    envelope is rejected.
    """
    if not isinstance(envelope, dict):
        return False, "no cached evidence envelope"
    if str(envelope.get("repository")) != repository:
        return False, "repository mismatch"
    if int(envelope.get("issue") or 0) != int(issue):
        return False, "issue mismatch"
    if not envelope.get("comment_id") or not envelope.get("comment_url"):
        return False, "missing comment identity"
    body = str(envelope.get("comment_body") or "")
    if experiment_id not in body:
        return False, "fetched comment body does not authorize the exact experiment_id"
    if str(envelope.get("experiment_id")) != experiment_id:
        return False, "envelope experiment_id mismatch"
    if str(envelope.get("target")) != str(envelope.get("target")):
        pass  # target recorded in envelope; matched below by caller intent
    expected_sequence = sorted(str(x) for x in (envelope.get("allowed_input_sequence") or []))
    if not expected_sequence:
        return False, "allowed input sequence is empty"
    if human_authority and str(envelope.get("github_author")) != human_authority:
        return False, f"github author {envelope.get('github_author')!r} != recorded human authority {human_authority!r}"
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    try:
        issued = dt.datetime.fromisoformat(str(envelope["issued_utc"]).replace("Z", "+00:00"))
        expires = dt.datetime.fromisoformat(str(envelope["expires_utc"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return False, "authorization timestamps must be ISO-8601"
    if now < issued:
        return False, "authorization not yet valid"
    if now >= expires:
        return False, f"authorization expired at {envelope['expires_utc']}"
    if sha256_evidence(envelope) != envelope.get("evidence_sha256"):
        return False, "evidence envelope hash mismatch; tampered or fabricated record"
    return True, "authorization evidence valid"


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
    beagle_windows_api_dir: Optional[str] = None,
    usb_identity: Optional[Dict[str, Any]] = None,
    topology: Optional[Dict[str, Any]] = None,
    driver_state: Optional[Dict[str, Any]] = None,
    target_state_confirmed: bool = False,
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
            "beagle_windows_api_dir": beagle_windows_api_dir,
            "official_app_present": bool(official_app_present),
            "target_state_note": target_state_note,
            "usb_identity": usb_identity,
            "topology": topology,
            "driver_state": driver_state,
            "target_state_confirmed": bool(target_state_confirmed),
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


def validate_manifest(manifest: Dict[str, Any], repo_root: Optional[Path] = None) -> List[str]:
    """Validate a manifest against the schema-derived required fields."""
    errors: List[str] = []
    for field in schema_required_top_level(repo_root):
        if field not in manifest:
            errors.append(f"manifest missing required top-level field: {field}")
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
    requested_lower = requested.lower()
    for item in manifest.get("prohibited") or []:
        item_lower = str(item).lower()
        if requested_lower in item_lower or item_lower in requested_lower:
            return True
    return False


# --------------------------------------------------------------------------- no-live preflight orchestration


def _detect_official_app() -> bool:
    candidates = [
        r"C:\Program Files\Epiphan\KVM2USB",
        r"C:\Program Files (x86)\Epiphan\KVM2USB",
        r"C:\Program Files\Epiphan KVM",
    ]
    return any(Path(p).exists() for p in candidates)


def _detect_beagle_driver() -> bool:
    """Detect the Total Phase Beagle USB 12 device present on Windows via PnP."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB\\VID_1679&PID_2001*' } | Select-Object -First 1"],
            capture_output=True, text=True, timeout=15, check=False,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return False


def preflight(
    *,
    repo_root: Optional[Path] = None,
    output_root: str = ".work/evidence",
    target_beagle_port: int = 0,
    host_interface: Optional[str] = None,
    target_state_confirmed: bool = False,
    topology: Optional[Dict[str, Any]] = None,
    driver_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """No-live workstation preflight/orchestration.

    Detects tools, drivers, USB identities, interfaces, disk space, topology,
    Beagle position, and target-state confirmation. Requires an explicitly
    selected USBPcap interface (never ``interfaces[0]``) unless exactly one
    verified interface contains the KVM2USB VID/PID. Returns HUMAN ACTION
    REQUIRED until all required fields are complete.
    """
    root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    usbpcap_cmd = find_usbpcap_cmd()
    tshark = find_tshark()
    interfaces = usbpcap_interfaces(usbpcap_cmd) if usbpcap_cmd else []
    disk = shutil.disk_usage(str(root))
    official_app_present = _detect_official_app()
    beagle_api_dir = find_beagle_windows_api_dir(root)
    beagle_driver_present = _detect_beagle_driver()
    usb_identity = _detect_kvm2usb_identity()

    issues: List[str] = []
    if not usbpcap_cmd:
        issues.append("USBPcapCMD not found; install USBPcap (elevated, HUMAN ACTION REQUIRED)")
    if not tshark:
        issues.append("TShark not found; install Wireshark/USBPcap (elevated, HUMAN ACTION REQUIRED)")
    if not official_app_present:
        issues.append("official Epiphan application/driver not detected")
    if not beagle_api_dir:
        issues.append("Total Phase Windows Beagle API not staged under .work/vendor/totalphase")
    if not beagle_driver_present:
        issues.append("Total Phase Beagle driver/device not detected")
    if disk.free < 2 * 1024 * 1024 * 1024:
        issues.append(f"insufficient disk space: {disk.free} bytes free")

    # Interface selection: explicit selection is required unless exactly one
    # verified interface contains the KVM2USB VID/PID.
    selected_interface = None
    if host_interface:
        selected_interface = host_interface
        if interfaces and host_interface not in interfaces:
            issues.append(f"explicit host_interface {host_interface!r} is not in the detected USBPcap interfaces {interfaces}")
    elif len(interfaces) == 1 and usb_identity and usb_identity.get("present"):
        selected_interface = interfaces[0]
        issues.append("exactly one USBPcap interface verified to contain KVM2USB; selected")
    else:
        issues.append("USBPcap interface not explicitly selected; do not auto-select interfaces[0] without proving it contains KVM2USB")
        if len(interfaces) > 1:
            issues.append(f"multiple USBPcap interfaces detected: {interfaces}; an explicit selection is required")

    if not target_state_confirmed:
        issues.append("target-state confirmation not provided (harmless state for the allowed input sequence)")
    if not topology or not topology.get("cable_path") or not topology.get("beagle_position") or not topology.get("target_identity"):
        issues.append("physical topology incomplete (cable path, Beagle position, target identity required)")

    human_actions: List[str] = []
    if not usbpcap_cmd or not tshark:
        human_actions.append("install USBPcap and Wireshark (elevated); do not automate privileged installation")
    if not official_app_present:
        human_actions.append("install the official Epiphan application/driver")
    if not beagle_api_dir:
        human_actions.append("stage the Total Phase Windows Beagle API under .work/vendor/totalphase")
    if not beagle_driver_present:
        human_actions.append("install/attach the Total Phase Beagle driver/device")
    if not selected_interface:
        human_actions.append("select the correct USBPcap root-hub/device interface (explicit)")
    if not target_state_confirmed:
        human_actions.append("confirm the target is in a harmless state for the allowed input sequence")
    if not topology or not topology.get("cable_path") or not topology.get("beagle_position") or not topology.get("target_identity"):
        human_actions.append("record physical topology: cable path, Beagle position, target identity")

    command_output: Dict[str, Any] = {}
    if selected_interface:
        command_output["usbpcap"] = usbpcap_command(selected_interface, Path(output_root) / "host.pcap")
    if beagle_api_dir:
        command_output["beagle"] = beagle_command(
            Path(output_root) / "target.jsonl",
            api_dir=beagle_api_dir,
            port=target_beagle_port,
        )

    return {
        "ok": not issues,
        "detected": {
            "usbpcap_cmd": usbpcap_cmd,
            "tshark": tshark,
            "usbpcap_interfaces": interfaces,
            "official_app_present": official_app_present,
            "beagle_windows_api_dir": str(beagle_api_dir) if beagle_api_dir else None,
            "beagle_driver_present": beagle_driver_present,
            "disk_free_bytes": disk.free,
            "usb_identity": usb_identity,
            "target_state_confirmed": target_state_confirmed,
            "topology": topology,
            "driver_state": driver_state,
        },
        "selected_host_interface": selected_interface,
        "issues": issues,
        "human_actions": human_actions,
        "commands": command_output,
        "live_disabled": True,
        "authorization_required": "a structured, GitHub-backed, expiring authorization evidence envelope",
    }


def _detect_kvm2usb_identity() -> Dict[str, Any]:
    """Detect the KVM2USB USB identity (VID/PID/serial) without live interaction."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB\\VID_2B77&PID_3661*' } | Select-Object -First 1 InstanceId,Status"],
            capture_output=True, text=True, timeout=15, check=False,
        )
        present = result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        present = False
    return {"vid": EPIPHAN_VID, "pid": KVM2USB3_PID, "present": present}


# --------------------------------------------------------------------------- no-live CLI


def _cli_preflight(args: argparse.Namespace) -> int:
    pf = preflight(
        repo_root=Path(args.repo_root) if args.repo_root else None,
        output_root=args.output_root,
        host_interface=args.host_interface,
        target_beagle_port=args.target_beagle_port,
    )
    print(json.dumps(pf, indent=2, sort_keys=True))
    if pf["issues"]:
        print("\nHUMAN ACTION REQUIRED:")
        for action in pf["human_actions"]:
            print(f"  - {action}")
        return 2
    return 0


def _cli_build_manifest(args: argparse.Namespace) -> int:
    pf = preflight(repo_root=Path(args.repo_root) if args.repo_root else None,
                   output_root=args.output_root, host_interface=args.host_interface)
    manifest = build_manifest(
        correlation=args.correlation or correlation_id(),
        operator=args.operator or "unknown",
        git_commit=_git_commit(),
        recovery_base_head=args.recovery_base_head or "unknown",
        output_root=args.output_root,
        host_interface=pf["selected_host_interface"],
        target_beagle_port=args.target_beagle_port,
        usbpcap_present=bool(pf["detected"]["usbpcap_cmd"]),
        tshark_present=bool(pf["detected"]["tshark"]),
        beagle_windows_api_present=bool(pf["detected"]["beagle_windows_api_dir"]),
        official_app_present=bool(pf["detected"]["official_app_present"]),
        target_state_note=args.target_state_note or "",
        authorization_record=None,
        beagle_windows_api_dir=pf["detected"]["beagle_windows_api_dir"],
        usb_identity=pf["detected"]["usb_identity"],
        topology=pf["detected"]["topology"],
        driver_state=pf["detected"]["driver_state"],
        target_state_confirmed=bool(pf["detected"]["target_state_confirmed"]),
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def _cli_ingest_authorization(args: argparse.Namespace) -> int:
    envelope = ingest_authorization(
        repository=args.repository,
        issue=args.issue,
        comment_id=str(args.comment_id),
        comment_url=args.comment_url or "",
        experiment_id=args.experiment_id,
        target=args.target,
        allowed_input_sequence=args.allowed_input_sequence,
        issued_utc=args.issued_utc,
        expires_utc=args.expires_utc,
    )
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(envelope, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(envelope, indent=2, sort_keys=True))
    return 0


def _cli_verify_authorization(args: argparse.Namespace) -> int:
    envelope = json.loads(Path(args.envelope).read_text(encoding="utf-8"))
    ok, reason = verify_authorization(
        envelope,
        experiment_id=args.experiment_id,
        repository=args.repository,
        issue=args.issue,
        human_authority=args.human_authority,
    )
    print(json.dumps({"ok": ok, "reason": reason}, indent=2, sort_keys=True))
    return 0 if ok else 1


def _git_commit() -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_pre = sub.add_parser("preflight", help="no-live preflight; emits HUMAN ACTION REQUIRED")
    p_pre.add_argument("--repo-root")
    p_pre.add_argument("--output-root", default=".work/evidence")
    p_pre.add_argument("--host-interface")
    p_pre.add_argument("--target-beagle-port", type=int, default=0)
    p_pre.set_defaults(func=_cli_preflight)

    p_build = sub.add_parser("build-manifest", help="emit the experiment manifest")
    p_build.add_argument("--repo-root")
    p_build.add_argument("--output-root", default=".work/evidence")
    p_build.add_argument("--host-interface")
    p_build.add_argument("--correlation")
    p_build.add_argument("--operator")
    p_build.add_argument("--recovery-base-head")
    p_build.add_argument("--target-beagle-port", type=int, default=0)
    p_build.add_argument("--target-state-note")
    p_build.set_defaults(func=_cli_build_manifest)

    p_ing = sub.add_parser("ingest-authorization", help="fetch the issue comment via gh api and write a hash-pinned envelope")
    p_ing.add_argument("--repository", required=True)
    p_ing.add_argument("--issue", type=int, required=True)
    p_ing.add_argument("--comment-id", required=True)
    p_ing.add_argument("--comment-url")
    p_ing.add_argument("--experiment-id", required=True)
    p_ing.add_argument("--target", required=True)
    p_ing.add_argument("--allowed-input-sequence", action="append", required=True)
    p_ing.add_argument("--issued-utc", required=True)
    p_ing.add_argument("--expires-utc", required=True)
    p_ing.add_argument("--output")
    p_ing.set_defaults(func=_cli_ingest_authorization)

    p_ver = sub.add_parser("verify-authorization", help="verify a cached evidence envelope without live capture")
    p_ver.add_argument("--envelope", required=True)
    p_ver.add_argument("--experiment-id", required=True)
    p_ver.add_argument("--repository", required=True)
    p_ver.add_argument("--issue", type=int, required=True)
    p_ver.add_argument("--human-authority", default="")
    p_ver.set_defaults(func=_cli_verify_authorization)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
