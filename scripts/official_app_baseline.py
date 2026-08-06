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

    Handles the two-space YAML layout used by this schema:
    - top-level ``required`` list items at indent 2;
    - top-level ``fields`` map section keys at indent 2;
    - a section's ``required`` list at indent 4 with items at indent 6;
    - a section's nested ``fields`` sub-map keys at indent 6, and a sub-field's
      ``required`` list at indent 8 with items at indent 10.

    Section required lists are exposed as ``fields[<section>]["required"]`` and
    nested sub-field required lists as ``fields[<section>]["fields"][<sub>]["required"]``.
    """
    root = (repo_root or Path(__file__).resolve().parents[1])
    text = (root / SCHEMA_PATH).read_text(encoding="utf-8")
    data: Dict[str, Any] = {"required": [], "fields": {}}
    top_required = False
    current_section: Optional[str] = None
    section_node: Optional[Dict[str, Any]] = None
    section_required = False
    section_in_fields = False
    current_sub: Optional[str] = None
    sub_node: Optional[Dict[str, Any]] = None
    sub_required = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if indent == 0:
            top_required = (stripped == "required:")
            current_section = None
            section_node = None
            section_required = False
            section_in_fields = False
            current_sub = None
            sub_node = None
            sub_required = False
            continue

        if top_required:
            if indent == 2 and stripped.startswith("- "):
                data["required"].append(stripped[2:].strip())
            continue

        if indent == 2 and stripped.endswith(":"):
            # A new top-level section key under `fields:`.
            key = stripped.rstrip(":").strip()
            section_node = data["fields"].setdefault(key, {})
            current_section = key
            section_required = False
            section_in_fields = False
            current_sub = None
            sub_node = None
            sub_required = False
            continue

        if section_node is None:
            continue

        if indent == 4:
            if stripped == "required:":
                section_required = True
                current_sub = None
                sub_node = None
                sub_required = False
                continue
            if stripped == "fields:":
                section_required = False
                section_in_fields = True
                current_sub = None
                sub_node = None
                sub_required = False
                continue
            # Other field metadata (type, description, nullable) at indent 4.
            continue

        if section_required and indent == 6 and stripped.startswith("- "):
            section_node.setdefault("required", []).append(stripped[2:].strip())
            continue

        if section_in_fields and indent == 6 and stripped.endswith(":"):
            key = stripped.rstrip(":").strip()
            sub_node = section_node.setdefault("fields", {}).setdefault(key, {})
            current_sub = key
            sub_required = False
            continue

        if sub_node is None:
            continue

        if indent == 8:
            if stripped == "required:":
                sub_required = True
                continue
            if stripped == "fields:":
                sub_required = False
                continue
            continue

        if sub_required and indent == 10 and stripped.startswith("- "):
            sub_node.setdefault("required", []).append(stripped[2:].strip())
            continue
    return data


def schema_required_top_level(repo_root: Optional[Path] = None) -> List[str]:
    return load_schema(repo_root).get("required", [])


def schema_section_required(section: str, repo_root: Optional[Path] = None) -> List[str]:
    """Required fields of one schema section (experiment, environment, capture,
    authorization_record), derived from the schema rather than a hand-maintained
    duplicate list."""
    schema = load_schema(repo_root)
    sec = (schema.get("fields") or {}).get(section) or {}
    return sec.get("required", [])


def schema_auth_required_fields(repo_root: Optional[Path] = None) -> List[str]:
    """Authorization-record required fields derived from the schema, not a
    hand-maintained duplicate list."""
    return schema_section_required("authorization_record", repo_root)


def schema_auth_block_required_fields(repo_root: Optional[Path] = None) -> List[str]:
    """Required fields of the nested ``authorization_block`` inside the
    authorization-record envelope, derived from the schema."""
    schema = load_schema(repo_root)
    auth = (schema.get("fields") or {}).get("authorization_record") or {}
    block = (auth.get("fields") or {}).get("authorization_block") or {}
    return block.get("required", [])


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
    if upper == "NAK":
        # NAK identity is preserved through normalization/counting; it must not
        # be conflated with ACK/STALL/NYET handshakes.
        return "NAK"
    if upper in ("ACK", "STALL", "NYET"):
        return "HANDSHAKE"
    if upper in ("SOF", "PRE", "SPLIT", "PING"):
        return "SPECIAL"
    return upper


def in_nak_data_counts(records: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count IN/OUT/SETUP/NAK/DATA/HANDSHAKE target transactions.

    Normalized records carry a ``class_`` (which preserves NAK separately from
    the ACK/STALL/NYET HANDSHAKE class after ``classify_pid``); raw records are
    classified on the fly. ACK/STALL/NYET increment ``HANDSHAKE``, never NAK.
    """
    counts = {"IN": 0, "OUT": 0, "SETUP": 0, "NAK": 0, "DATA": 0, "HANDSHAKE": 0}
    for record in records:
        pid = record.get("pid_name")
        class_ = record.get("class_") or classify_pid(pid)
        if class_ == "TOKEN_IN":
            counts["IN"] += 1
        elif class_ == "TOKEN_OUT":
            counts["OUT"] += 1
        elif class_ == "TOKEN_SETUP":
            counts["SETUP"] += 1
        elif class_ == "NAK":
            counts["NAK"] += 1
        elif class_ == "HANDSHAKE":
            counts["HANDSHAKE"] += 1
        elif class_ == "DATA":
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


def _sort_key_ts(row: Dict[str, Any]) -> float:
    ts = _ts_seconds(row.get("timestamp_utc"))
    return ts if ts is not None else float("inf")


def _find_first(rows: List[Dict[str, Any]], predicate) -> Optional[float]:
    """Return the earliest timestamp (epoch seconds) in ``rows`` matching a
    predicate, or None when unavailable. ``rows`` must be time-ordered."""
    for r in rows:
        if predicate(r):
            ts = _ts_seconds(r.get("timestamp_utc"))
            if ts is not None:
                return ts
    return None


def _find_first_strictly_after(
    rows: List[Dict[str, Any]], predicate, after_ts: Optional[float]
) -> Optional[float]:
    """Return the earliest timestamp in ``rows`` matching ``predicate`` whose
    timestamp is strictly after ``after_ts``, or None. ``rows`` must be
    time-ordered."""
    if after_ts is None:
        return None
    for r in rows:
        ts = _ts_seconds(r.get("timestamp_utc"))
        if ts is not None and ts > after_ts and predicate(r):
            return ts
    return None


def _is_target_data(row: Dict[str, Any]) -> bool:
    """A target DATA transaction (never a NAK or other handshake)."""
    return row.get("kind") == "target_transaction" and (
        row.get("class_") == "DATA" or row.get("pid_name") in ("DATA0", "DATA1", "DATA2", "MDATA")
    )


def _is_target_nak(row: Dict[str, Any]) -> bool:
    """A target NAK transaction (never ACK/STALL/NYET or DATA)."""
    return row.get("kind") == "target_transaction" and (
        row.get("class_") == "NAK" or row.get("pid_name") == "NAK"
    )


def _is_target_data_or_nak(row: Dict[str, Any]) -> bool:
    return _is_target_data(row) or _is_target_nak(row)


def stage_timing_metrics(
    rows: List[Dict[str, Any]],
    *,
    marker_events: List[str],
    tolerance: float = DEFAULT_TIMING_TOLERANCE_SECONDS,
) -> Dict[str, Any]:
    """Compute nested per-stage relative timing metrics for a single session.

    Metrics are stored under unique keys so earlier stages are never overwritten.
    A metric value is present only when both endpoints are measured; unavailable
    evidence is absent and is never confused with a measured zero duration.

    Measured pairs (seconds), each with strictly-after selection so an event is
    never paired with an earlier one:
    - ``app_start.marker_to_first_host_report`` (first host report after app start)
    - ``<stage>.marker_to_first_host_transfer``
    - ``<stage>.host_to_first_target_data_or_nak`` (first DATA/NAK after the host
      transfer)
    - ``capslock.down_to_up``
    - ``ordinary_key.down_to_up``
    - ``all_keys_release.last_key_release_to_all_keys_release``
    - ``init_to_first_target_data`` (first real DATA after app start, never a NAK)

    The returned dict also carries ``_endpoints`` (metric path -> (start_ts,
    end_ts)) used to order timing divergences chronologically from actual event
    timestamps.
    """
    metrics: Dict[str, Any] = {}
    endpoints: Dict[str, Tuple[float, float]] = {}
    ordered = sorted(rows, key=_sort_key_ts)
    buckets = align_by_marker(ordered, marker_events)

    def record(section: str, metric: str, start_ts: Optional[float], end_ts: Optional[float]) -> None:
        if start_ts is not None and end_ts is not None:
            value = round(end_ts - start_ts, 6)
            if section:
                metrics.setdefault(section, {})[metric] = value
            else:
                metrics[metric] = value
            endpoints[f"{section}.{metric}" if section else metric] = (start_ts, end_ts)

    def marker_ts(name: str) -> Optional[float]:
        for r in ordered:
            if r.get("kind") == "marker" and (r.get("event") or r.get("marker")) == name:
                ts = _ts_seconds(r.get("timestamp_utc"))
                if ts is not None:
                    return ts
        return None

    def first_host_after(ts: Optional[float]) -> Optional[float]:
        return _find_first_strictly_after(ordered, lambda r: r.get("kind") == "host_transfer", ts)

    # app_start marker -> first host report (strictly after app start)
    app_start_ts = marker_ts("app_start")
    record("app_start", "marker_to_first_host_report", app_start_ts, first_host_after(app_start_ts))

    # init (first app_start marker) -> first real target DATA across the full
    # timeline. Requires DATA specifically; a NAK is never target DATA.
    first_data = _find_first_strictly_after(ordered, _is_target_data, app_start_ts)
    record("", "init_to_first_target_data", app_start_ts, first_data)

    # Per-stage: marker -> first host transfer; host transfer -> first DATA/NAK
    # that is strictly after that host transfer (a target event that precedes the
    # host transfer is never selected).
    for stage in marker_events:
        bucket = buckets.get(stage, [])
        stage_ts = marker_ts(stage)
        host_ts = _find_first_strictly_after(bucket, lambda r: r.get("kind") == "host_transfer", stage_ts)
        record(stage, "marker_to_first_host_transfer", stage_ts, host_ts)
        target_ts = _find_first_strictly_after(bucket, _is_target_data_or_nak, host_ts)
        record(stage, "host_to_first_target_data_or_nak", host_ts, target_ts)

    # Cross-marker intervals (search the full timeline, not a single bucket)
    record("capslock", "down_to_up", marker_ts("capslock_down"), marker_ts("capslock_up"))
    record("ordinary_key", "down_to_up", marker_ts("ordinary_key_down"), marker_ts("ordinary_key_up"))
    all_release = marker_ts("all_keys_release")
    last_key_release = None
    for name in ("ordinary_key_up", "capslock_up"):
        ts = marker_ts(name)
        if ts is not None and (last_key_release is None or ts > last_key_release):
            last_key_release = ts
    record("all_keys_release", "last_key_release_to_all_keys_release", last_key_release, all_release)

    metrics["_endpoints"] = endpoints
    metrics["tolerance_seconds"] = tolerance
    return metrics


def compare_timing(
    official_rows: List[Dict[str, Any]],
    agent_rows: List[Dict[str, Any]],
    marker_events: List[str],
    tolerance: float = DEFAULT_TIMING_TOLERANCE_SECONDS,
) -> Dict[str, Any]:
    """Compare official vs agent timing metrics.

    Metrics are compared independently with the configured tolerance. Only
    metrics present in both sessions are compared; unavailable evidence is
    reported but not treated as a divergence. The chronologically first timing
    divergence is ordered by the actual metric endpoint timestamps (the measured
    interval's start, then its end), falling back to metric definition order only
    as a tiebreak — never a fixed list order alone.
    """
    official_metrics = stage_timing_metrics(official_rows, marker_events=marker_events, tolerance=tolerance)
    agent_metrics = stage_timing_metrics(agent_rows, marker_events=marker_events, tolerance=tolerance)
    official_endpoints = official_metrics.get("_endpoints") or {}
    agent_endpoints = agent_metrics.get("_endpoints") or {}

    divergences: List[Dict[str, Any]] = []
    metric_paths: List[Tuple[str, str]] = []
    # Definition order used only to disambiguate identical endpoint timestamps.
    metric_paths.append(("app_start", "marker_to_first_host_report"))
    metric_paths.append(("app_start", "host_to_first_target_data_or_nak"))
    for stage in marker_events:
        if stage == "app_start":
            continue
        metric_paths.append((stage, "marker_to_first_host_transfer"))
        metric_paths.append((stage, "host_to_first_target_data_or_nak"))
    metric_paths.append(("", "init_to_first_target_data"))
    metric_paths.append(("capslock", "down_to_up"))
    metric_paths.append(("ordinary_key", "down_to_up"))
    metric_paths.append(("all_keys_release", "last_key_release_to_all_keys_release"))

    for index, (section, metric) in enumerate(metric_paths):
        path = f"{section}.{metric}" if section else metric
        if section:
            o = (official_metrics.get(section) or {}).get(metric)
            a = (agent_metrics.get(section) or {}).get(metric)
        else:
            o = official_metrics.get(metric)
            a = agent_metrics.get(metric)
        if o is None or a is None:
            continue
        if abs(o - a) > tolerance:
            # Use the actual interval start/end timestamps for chronological
            # ordering; fall back to definition order only on a tie.
            start_ts = official_endpoints.get(path, (float("inf"),))[0]
            end_ts = official_endpoints.get(path, (float("inf"), float("inf")))[1]
            divergences.append({
                "metric": path,
                "official_s": o, "agent_s": a, "delta_s": round(o - a, 6),
                "start_ts": start_ts, "end_ts": end_ts, "definition_order": index,
            })

    divergences.sort(key=lambda d: (d["start_ts"], d["end_ts"], d["definition_order"]))
    # Drop the internal ordering keys from the public divergence records.
    public_divergences = [
        {k: v for k, v in d.items() if k not in ("start_ts", "end_ts", "definition_order")}
        for d in divergences
    ]

    return {
        "official": official_metrics,
        "agent": agent_metrics,
        "first_timing_divergence": public_divergences[0] if public_divergences else None,
        "timing_divergences": public_divergences,
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
    count_keys = ("IN", "OUT", "SETUP", "NAK", "DATA", "HANDSHAKE")
    totals = {f"{side}_{key}": 0 for side in ("official", "agent") for key in count_keys}
    first_divergence: Optional[Dict[str, Any]] = None
    for marker in marker_events:
        o_host = [r for r in official.get(marker, []) if r.get("kind") == "host_transfer"]
        a_host = [r for r in agent.get(marker, []) if r.get("kind") == "host_transfer"]
        o_tgt = [r for r in official.get(marker, []) if r.get("kind") == "target_transaction"]
        a_tgt = [r for r in agent.get(marker, []) if r.get("kind") == "target_transaction"]
        o_counts = in_nak_data_counts(o_tgt)
        a_counts = in_nak_data_counts(a_tgt)
        for key in count_keys:
            totals[f"official_{key}"] += o_counts[key]
            totals[f"agent_{key}"] += a_counts[key]
        host_div = _first_host_divergence(o_host, a_host)
        target_div = None
        for key in count_keys:
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
        "repository", "issue", "comment_id", "comment_url", "issue_url",
        "repository_url", "comment_body", "github_author", "fetched_utc",
        "experiment_id", "target", "allowed_input_sequence", "issued_utc",
        "expires_utc", "authority",
    )}
    core["authorization_block"] = envelope.get("authorization_block")
    return json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_evidence(envelope: Dict[str, Any]) -> str:
    return hashlib.sha256(canonicalize_evidence(envelope)).hexdigest()


def fetch_issue_comment(repository: str, comment_id: str) -> Dict[str, Any]:
    """Fetch the exact issue comment through authenticated ``gh api``.

    Returns the full comment including id, body, html_url, issue_url,
    repository_url, author, created_at, and updated_at. Raises RuntimeError on
    failure. No live capture is involved.
    """
    url = f"repos/{repository}/issues/comments/{comment_id}"
    try:
        result = subprocess.run(
            ["gh", "api", url, "--jq",
             "{id, body, html_url, issue_url, repository_url, created_at, updated_at, "
             "user: .user.login}"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except Exception as exc:
        raise RuntimeError(f"gh api failed: {exc}") from exc
    if result.returncode != 0:
        raise RuntimeError(f"gh api failed: {result.stderr.strip() or result.stdout.strip()}")
    return json.loads(result.stdout)


_ISSUE_URL_RE = re.compile(
    r"(?:repos/|github\.com/)(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<issue>\d+)"
)


def _issue_url_matches(issue_url: str, repository: str, issue: int) -> bool:
    """Return True when ``issue_url`` identifies the same repository and issue.

    Accepts both the GitHub API issue URL (``/repos/{owner}/{repo}/issues/{n}``)
    and the html issue URL (``github.com/{owner}/{repo}/issues/{n}``). An empty
    or unparseable URL never matches.
    """
    m = _ISSUE_URL_RE.search(issue_url or "")
    if not m:
        return False
    expected = repository.split("/")
    return [m.group("owner"), m.group("repo")] == expected and int(m.group("issue")) == int(issue)


def parse_authorization_block(body: str) -> Dict[str, Any]:
    """Parse the single machine-readable fenced JSON authorization block from a
    fetched comment body.

    The block must contain repository, issue, experiment_id, target,
    allowed_input_sequence, issued_utc, expires_utc, and authority. Exactly one
    fenced JSON block is accepted; multiple blocks are rejected rather than
    silently taking the first. Raises ValueError when the block is absent,
    malformed, ambiguous, or when issued_utc does not precede expires_utc.
    """
    fences = re.findall(r"```json\s*(\{.*?\})\s*```", body, flags=re.DOTALL)
    if not fences:
        raise ValueError("no fenced JSON authorization block found in the comment body")
    if len(fences) > 1:
        raise ValueError("multiple fenced JSON authorization blocks found; exactly one is required")
    try:
        block = json.loads(fences[0])
    except json.JSONDecodeError as exc:
        raise ValueError(f"authorization block is not valid JSON: {exc}") from exc
    required = ("repository", "issue", "experiment_id", "target",
                "allowed_input_sequence", "issued_utc", "expires_utc", "authority")
    for field in required:
        value = block.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError(f"authorization block missing required field: {field}")
    if not isinstance(block.get("allowed_input_sequence"), list) or not block["allowed_input_sequence"]:
        raise ValueError("authorization block allowed_input_sequence must be a non-empty list")
    try:
        issued = dt.datetime.fromisoformat(str(block["issued_utc"]).replace("Z", "+00:00"))
        expires = dt.datetime.fromisoformat(str(block["expires_utc"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise ValueError("authorization block issued_utc/expires_utc must be ISO-8601") from exc
    if issued >= expires:
        raise ValueError("authorization block issued_utc must precede expires_utc")
    return block


def _authority_references(authority: Any, author: str) -> bool:
    """Return True when the authority string names the given GitHub author (the
    approved human authority), so an authority can never be an unchecked
    arbitrary string."""
    return bool(authority) and author in str(authority)


def build_evidence_envelope(
    *,
    repository: str,
    issue: int,
    comment_id: str,
    comment_url: str,
    issue_url: str,
    repository_url: str,
    comment_body: str,
    github_author: str,
    fetched_utc: str,
    authorization_block: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a cached evidence envelope from a fetched comment and its parsed
    authorization block.

    All authorized values are taken from ``authorization_block`` (parsed from
    the fetched comment body). Caller values must never be mixed in here. The
    envelope stores the raw fetched evidence, the parsed block, fetched UTC, and
    a SHA-256 hash of the canonicalized evidence.
    """
    envelope = {
        "repository": repository,
        "issue": issue,
        "comment_id": comment_id,
        "comment_url": comment_url,
        "issue_url": issue_url,
        "repository_url": repository_url,
        "comment_body": comment_body,
        "github_author": github_author,
        "fetched_utc": fetched_utc,
        "authorization_block": authorization_block,
        "experiment_id": authorization_block["experiment_id"],
        "target": authorization_block["target"],
        "allowed_input_sequence": list(authorization_block["allowed_input_sequence"]),
        "issued_utc": authorization_block["issued_utc"],
        "expires_utc": authorization_block["expires_utc"],
        "authority": authorization_block["authority"],
    }
    envelope["evidence_sha256"] = sha256_evidence(envelope)
    return envelope


def ingest_authorization(
    *,
    repository: str,
    issue: int,
    comment_id: str,
    fetched: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ingest an authorization by fetching the exact issue comment via gh api
    and parsing every authorized value from the comment body.

    Caller arguments may only name the repository/issue/comment to fetch; they
    never supply or override authorization values. A caller-assembled dictionary
    cannot be used here because all values come from the fetched comment body.
    """
    if fetched is None:
        fetched = fetch_issue_comment(repository, comment_id)
    if not isinstance(fetched, dict):
        raise ValueError("fetched comment evidence must be a dict from gh api")
    comment_body = fetched.get("body") or ""
    github_author = fetched.get("user") or ""
    fetched_id = str(fetched.get("id") or "")
    if not fetched_id:
        raise ValueError("fetched comment has no id; cannot establish comment identity")
    if str(comment_id) != fetched_id:
        raise ValueError(
            f"fetched comment id {fetched_id!r} does not match the requested comment id {comment_id!r}"
        )
    fetched_url = fetched.get("html_url") or ""
    issue_url = fetched.get("issue_url") or ""
    repository_url = fetched.get("repository_url") or ""
    if repository_url and repository_url.rstrip("/").split("/")[-2:] != repository.split("/"):
        raise ValueError("repository_url does not match the requested repository")
    if issue_url and not _issue_url_matches(issue_url, repository, issue):
        raise ValueError(f"issue_url {issue_url!r} does not identify {repository} issue {issue}")
    block = parse_authorization_block(comment_body)
    if str(block.get("repository")) != repository:
        raise ValueError("authorization block repository does not match the requested repository")
    if int(block.get("issue")) != int(issue):
        raise ValueError("authorization block issue does not match the requested issue")
    return build_evidence_envelope(
        repository=repository,
        issue=issue,
        comment_id=fetched_id,
        comment_url=fetched_url,
        issue_url=issue_url,
        repository_url=repository_url,
        comment_body=comment_body,
        github_author=github_author,
        fetched_utc=utc_timestamp(),
        authorization_block=block,
    )


def verify_authorization(
    envelope: Dict[str, Any],
    *,
    experiment_id: str,
    repository: str,
    issue: int,
    human_authority: str,
    now_utc: Optional[dt.datetime] = None,
    refetch: bool = True,
    fetched: Optional[Dict[str, Any]] = None,
    expected_comment_id: Optional[str] = None,
    expected_target: Optional[str] = None,
    expected_allowed_input_sequence: Optional[List[str]] = None,
    expected_issued_utc: Optional[str] = None,
    expected_expires_utc: Optional[str] = None,
    expected_issue_url: Optional[str] = None,
) -> Tuple[bool, str]:
    """Verify a cached evidence envelope against GitHub evidence.

    By default, re-fetches the current comment via gh api and compares it to the
    cached envelope. ``refetch=False`` uses the cached envelope only and must be
    explicitly identified as cached evidence. Confirms repository, issue URL,
    comment ID/URL, GitHub author, experiment ID, target, exact allowed input
    sequence, issued/expiry UTC, the authority contract, and the envelope hash —
    all derived from the parsed comment body.

    ``human_authority`` is mandatory: it is the approved human authority (the
    GitHub login that must have posted the comment). The GitHub author must equal
    it, and ``authorization_block.authority`` must reference it, so an authority
    can never be an unchecked arbitrary string. The ``expected_*`` arguments are
    caller-supplied expected values used only for comparison; they never create
    or override authorization values.
    """
    if not isinstance(envelope, dict):
        return False, "no cached evidence envelope"
    if not human_authority:
        return False, "human_authority (approved authority) is required and cannot be empty"
    if str(envelope.get("repository")) != repository:
        return False, "repository mismatch"
    if int(envelope.get("issue") or 0) != int(issue):
        return False, "issue mismatch"
    if not envelope.get("comment_id"):
        return False, "missing comment identity"
    if expected_comment_id is not None and str(envelope.get("comment_id")) != str(expected_comment_id):
        return False, (
            f"envelope comment id {envelope.get('comment_id')!r} "
            f"!= expected comment id {expected_comment_id!r}"
        )
    envelope_issue_url = envelope.get("issue_url") or ""
    if envelope_issue_url and not _issue_url_matches(envelope_issue_url, repository, issue):
        return False, f"envelope issue_url {envelope_issue_url!r} does not identify {repository} issue {issue}"
    if expected_issue_url is not None and envelope_issue_url != expected_issue_url:
        return False, f"envelope issue_url {envelope_issue_url!r} != expected {expected_issue_url!r}"
    block = envelope.get("authorization_block")
    if not isinstance(block, dict):
        return False, "no parsed authorization block in envelope"
    if str(block.get("repository")) != str(envelope.get("repository")):
        return False, "authorization block repository differs from envelope repository"
    if int(block.get("issue") or 0) != int(envelope.get("issue") or 0):
        return False, "authorization block issue differs from envelope issue"
    if str(block.get("experiment_id")) != experiment_id:
        return False, f"comment authorization experiment_id {block.get('experiment_id')!r} != {experiment_id!r}"
    if not block.get("target") or not block.get("allowed_input_sequence"):
        return False, "authorization block target/sequence is empty"
    if expected_target is not None and str(block.get("target")) != expected_target:
        return False, f"authorization target {block.get('target')!r} != expected {expected_target!r}"
    if expected_allowed_input_sequence is not None:
        expected_seq = sorted(str(x) for x in expected_allowed_input_sequence)
        actual_seq = sorted(str(x) for x in block.get("allowed_input_sequence") or [])
        if actual_seq != expected_seq:
            return False, "authorization allowed input sequence does not match the expected sequence"
    if expected_issued_utc is not None and str(block.get("issued_utc")) != expected_issued_utc:
        return False, f"authorization issued_utc {block.get('issued_utc')!r} != expected {expected_issued_utc!r}"
    if expected_expires_utc is not None and str(block.get("expires_utc")) != expected_expires_utc:
        return False, f"authorization expires_utc {block.get('expires_utc')!r} != expected {expected_expires_utc!r}"
    # GitHub author validation is mandatory: the comment must have been posted by
    # the approved human authority.
    if str(envelope.get("github_author")) != human_authority:
        return False, f"github author {envelope.get('github_author')!r} != recorded human authority {human_authority!r}"
    # The authority named in the block must reference the approved authority and
    # agree with the envelope's recorded authority; it is never an unchecked
    # arbitrary string.
    block_authority = str(block.get("authority") or "")
    if not _authority_references(block_authority, human_authority):
        return False, (
            f"authorization block authority {block_authority!r} does not reference "
            f"the approved authority {human_authority!r}"
        )
    if str(envelope.get("authority") or "") != block_authority:
        return False, "envelope authority differs from the authorization block authority"

    if refetch:
        current = fetched or fetch_issue_comment(repository, str(envelope.get("comment_id")))
        if str(current.get("id") or "") != str(envelope.get("comment_id")):
            return False, "current GitHub comment id differs from cached evidence"
        if (current.get("html_url") or "") != (envelope.get("comment_url") or ""):
            return False, "current GitHub comment url differs from cached evidence"
        if (current.get("user") or "") != (envelope.get("github_author") or ""):
            return False, "current GitHub author differs from cached evidence"
        if (current.get("body") or "") != (envelope.get("comment_body") or ""):
            return False, "current GitHub comment body differs from cached evidence"
        # The re-fetched body must parse to the same authorization values.
        try:
            current_block = parse_authorization_block(current.get("body") or "")
        except ValueError:
            return False, "current GitHub comment does not contain a valid authorization block"
        if current_block != block:
            return False, "current GitHub authorization block differs from cached evidence"

    now = now_utc or dt.datetime.now(dt.timezone.utc)
    try:
        issued = dt.datetime.fromisoformat(str(block["issued_utc"]).replace("Z", "+00:00"))
        expires = dt.datetime.fromisoformat(str(block["expires_utc"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return False, "authorization timestamps must be ISO-8601"
    if issued >= expires:
        return False, "authorization issued_utc must precede expires_utc"
    if now < issued:
        return False, "authorization not yet valid"
    if now >= expires:
        return False, f"authorization expired at {block['expires_utc']}"
    if sha256_evidence(envelope) != envelope.get("evidence_sha256"):
        return False, "evidence envelope hash mismatch; tampered or fabricated record"
    suffix = "" if refetch else " (cached evidence — not re-fetched from GitHub)"
    return True, "authorization evidence valid" + suffix


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
    """Validate a manifest against the schema-derived required fields.

    Validates the top-level required fields and the nested schema-required
    fields of ``experiment``, ``environment``, ``capture``, and — when present
    and non-null — ``authorization_record``. Every nested required list comes
    from the schema, not a hand-maintained duplicate.
    """
    errors: List[str] = []
    for field in schema_required_top_level(repo_root):
        if field not in manifest:
            errors.append(f"manifest missing required top-level field: {field}")

    def check_section(section: str) -> Dict[str, Any]:
        value = manifest.get(section)
        if not isinstance(value, dict):
            errors.append(f"{section} must be an object")
            return {}
        for field in schema_section_required(section, repo_root):
            if field not in value:
                errors.append(f"{section}.{field} is required")
        return value

    experiment = check_section("experiment")
    for field in ("id", "objective", "operator", "date", "git_commit", "recovery_base_head"):
        if not experiment.get(field):
            errors.append(f"experiment.{field} is required")

    environment = check_section("environment")
    # host_interface and beagle_windows_api_dir are schema-nullable, so only key
    # presence is checked above; the object fields must be meaningful when the
    # experiment is to be runnable.
    for field in ("usb_identity", "topology", "driver_state"):
        if environment.get(field) is None:
            errors.append(f"environment.{field} must not be null")

    capture = check_section("capture")
    if not capture.get("correlation_id"):
        errors.append("capture.correlation_id is required")
    markers = capture.get("event_markers") or []
    required_markers = {m["event"] for m in DEFAULT_MARKERS}
    marker_names = {m.get("event") for m in markers if isinstance(m, dict)}
    missing = sorted(required_markers - marker_names)
    if missing:
        errors.append(f"capture.event_markers missing required markers: {', '.join(missing)}")
    for m in markers:
        if isinstance(m, dict):
            for field in ("event", "description"):
                if not m.get(field):
                    errors.append(f"capture.event_markers item missing {field}: {m!r}")

    auth = manifest.get(AUTHORIZATION_RECORD_FIELD)
    if auth is not None:
        if not isinstance(auth, dict):
            errors.append("authorization_record must be an object when present")
        else:
            for field in schema_auth_required_fields(repo_root):
                if not auth.get(field):
                    errors.append(f"authorization_record.{field} is required")
            block = auth.get("authorization_block")
            if not isinstance(block, dict):
                errors.append("authorization_record.authorization_block must be an object")
            else:
                for field in schema_auth_block_required_fields(repo_root):
                    if not block.get(field):
                        errors.append(f"authorization_record.authorization_block.{field} is required")
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


def _mapping_entry_maps_kvm2usb(
    entry: Any, usb_identity: Optional[Dict[str, Any]] = None
) -> bool:
    """Return True when a mapping record associates an interface with the
    KVM2USB device specifically, not merely with some USB device.

    A record is accepted when it explicitly declares the KVM2USB mapping
    (``kvm2usb: true`` or ``device: kvm2usb``, e.g. a reviewed mapping record)
    or when its ``device_instance`` carries the KVM2USB VID/PID, matched
    case-insensitively against the detected identity and defaulting to the known
    Epiphan/KVM2USB IDs. Device-identity detection alone is never treated as
    interface association.
    """
    if not isinstance(entry, dict):
        return False
    if entry.get("kvm2usb") is True or str(entry.get("device", "")).strip().lower() == "kvm2usb":
        return True
    instance = str(entry.get("device_instance") or "").upper()
    if not instance:
        return False
    vid = str((usb_identity or {}).get("vid") or EPIPHAN_VID).upper()
    pid = str((usb_identity or {}).get("pid") or KVM2USB3_PID).upper()
    return f"VID_{vid}" in instance and f"PID_{pid}" in instance


# Accepted driver-state evidence values. Anything else — including ``unknown`` or
# a missing value — is rejected so driver evidence cannot be silently skipped.
_ACCEPTED_DRIVER_STATES = ("detected", "present", "installed", "ok", "ready", "available")


def _driver_evidence_ok(driver_state: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    """Return (ok, reason) for complete, accepted official-app and Beagle driver
    evidence. Missing or ``unknown`` (or any unrecognized) values are rejected."""
    if not isinstance(driver_state, dict):
        return False, "driver-state evidence required: official_app and beagle driver status"
    for key in ("official_app", "beagle"):
        value = driver_state.get(key)
        normalized = str(value).strip().lower() if value is not None else ""
        if not normalized or normalized == "unknown":
            return False, f"driver-state evidence incomplete: driver_state.{key} is missing or 'unknown'"
        if normalized not in _ACCEPTED_DRIVER_STATES:
            return False, (
                f"driver-state evidence not accepted: driver_state.{key} = {value!r}; "
                f"expected one of {', '.join(_ACCEPTED_DRIVER_STATES)}"
            )
    return True, ""


def preflight(
    *,
    repo_root: Optional[Path] = None,
    output_root: str = ".work/evidence",
    target_beagle_port: int = 0,
    host_interface: Optional[str] = None,
    target_state_confirmed: bool = False,
    topology: Optional[Dict[str, Any]] = None,
    driver_state: Optional[Dict[str, Any]] = None,
    interface_mapping: Optional[Dict[str, Any]] = None,
    offline_only: bool = False,
) -> Dict[str, Any]:
    """No-live workstation preflight/orchestration that fails closed.

    Detects tools, drivers, USB identities, interfaces, disk space, topology,
    Beagle position, target-state confirmation, driver-state evidence, and output
    root containment.

    Interface selection is evidence-backed and workstation-grounded: an interface
    qualifies only when its mapping evidence associates it with the KVM2USB
    device (a PnP/extcap/mapping record) AND it is present in the detected
    USBPcap interface list. A mapped-but-absent interface is rejected. A global
    device-presence check alone never proves association.

    A runnable preflight additionally requires current KVM2USB device presence
    (unless ``offline_only`` is selected), complete accepted official-app and
    Beagle driver-state evidence (missing/``unknown`` rejected), and an output
    root that is contained under the approved ignored/private root and
    git-ignored. Capture commands are emitted only when every related gate
    passes. Returns HUMAN ACTION REQUIRED until all gates pass.
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
    identity_present = bool(usb_identity and usb_identity.get("present"))

    # interface_mapping maps a USBPcap interface to the KVM2USB device instance.
    # Example: {"\\\\.\\USBPcap1": {"device_instance": "USB\\VID_2B77&PID_3661\\...", "evidence": "pnp-root-hub"}}
    # An interface is positively mapped only when the record associates it with
    # the KVM2USB device (matching VID/PID/instance or an explicit reviewed
    # mapping marker); a record for some other device never counts.
    mapping = interface_mapping or {}
    positively_mapped = [
        name for name, entry in mapping.items()
        if _mapping_entry_maps_kvm2usb(entry, usb_identity)
    ]
    # Mappings must reference interfaces actually detected on the workstation;
    # a mapped-but-absent interface is rejected, never silently ignored.
    absent_mapped = [name for name in positively_mapped if name not in interfaces]
    available_mapped = [name for name in positively_mapped if name in interfaces]

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
    if absent_mapped:
        issues.append(
            "interface->KVM2USB mapping references USBPcap interfaces not detected "
            f"on this workstation: {absent_mapped}"
        )

    # Interface selection: only interfaces present AND positively mapped qualify.
    selected_interface = None
    if host_interface:
        if host_interface in available_mapped:
            # Explicit selection is honored only when mapping evidence associates
            # the interface with the KVM2USB device and the interface exists here.
            selected_interface = host_interface
        elif host_interface in positively_mapped:
            issues.append(
                f"explicit host_interface {host_interface!r} is mapped to KVM2USB "
                "but is not a detected USBPcap interface on this workstation"
            )
        elif host_interface in interfaces:
            issues.append(
                f"explicit host_interface {host_interface!r} has no mapping evidence "
                "associating it with the KVM2USB device; provide interface_mapping"
            )
        else:
            issues.append(f"explicit host_interface {host_interface!r} is not a detected USBPcap interface")
    elif len(available_mapped) == 1:
        # Auto-select only when exactly one interface is positively mapped AND
        # present on the workstation.
        selected_interface = available_mapped[0]
    else:
        if not identity_present:
            issues.append("KVM2USB device identity not detected; cannot associate any interface")
        issues.append(
            "USBPcap interface not selected: require interface->KVM2USB mapping evidence "
            "for an interface present on this workstation; do not infer from global device presence"
        )
        if len(available_mapped) > 1:
            issues.append(f"multiple mapped USBPcap interfaces: {available_mapped}; an explicit selection is required")

    # Runnable preflight requires the KVM2USB device currently present unless an
    # offline-only mode is selected.
    if selected_interface and not identity_present and not offline_only:
        issues.append(
            "KVM2USB device not currently detected; runnable preflight requires the "
            "device present (or select offline-only mode)"
        )

    if not target_state_confirmed:
        issues.append("target-state confirmation not provided (harmless state for the allowed input sequence)")
    if not topology or not topology.get("cable_path") or not topology.get("beagle_position") or not topology.get("target_identity"):
        issues.append("physical topology incomplete (cable path, Beagle position, target identity required)")

    # Complete accepted driver-state evidence is required; missing/`unknown`
    # values are rejected rather than silently recorded.
    driver_ok, driver_reason = _driver_evidence_ok(driver_state)
    if not driver_ok:
        issues.append(driver_reason)

    # Output root must be contained under the approved ignored/private root and
    # git-ignored, both for preflight and before any manifest output.
    output_path_result = verify_output_path(output_root, repo_root=root)
    if not output_path_result["ok"]:
        issues.append(
            f"capture output root {output_root!r} is not under an approved ignored/private root: "
            + "; ".join(output_path_result["errors"])
        )

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
        human_actions.append(
            "provide interface->KVM2USB mapping evidence for an interface present on this "
            "workstation (PnP root-hub/extcap/mapping record) and select the interface"
        )
    if selected_interface and not identity_present and not offline_only:
        human_actions.append("attach the KVM2USB device (or select offline-only mode)")
    if not target_state_confirmed:
        human_actions.append("confirm the target is in a harmless state for the allowed input sequence")
    if not topology or not topology.get("cable_path") or not topology.get("beagle_position") or not topology.get("target_identity"):
        human_actions.append("record physical topology: cable path, Beagle position, target identity")
    if not driver_ok:
        human_actions.append("record complete accepted official-app and Beagle driver-state evidence")
    if not output_path_result["ok"]:
        human_actions.append("use an output root under the approved ignored/private evidence root (.work/...)")

    # Capture commands are emitted only after every related gate passes.
    command_output: Dict[str, Any] = {}
    if not issues:
        command_output["usbpcap"] = usbpcap_command(selected_interface, Path(output_root) / "host.pcap")
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
            "interface_mapping": mapping,
            "offline_only": offline_only,
        },
        "selected_host_interface": selected_interface,
        "issues": issues,
        "human_actions": human_actions,
        "commands": command_output,
        "live_disabled": True,
        "authorization_required": "a structured, GitHub-backed, expiring authorization evidence envelope",
    }


def _detect_kvm2usb_identity() -> Dict[str, Any]:
    """Detect the KVM2USB USB identity (VID/PID/serial) without live interaction.

    This is device-identity detection only; it does NOT prove which USBPcap
    interface/root hub contains the device. Interface association requires a
    mapping evidence record (interface_mapping).
    """
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


def _preflight_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    """Build a preflight report from CLI arguments, including the completeness
    gates (target-state, topology, driver-state, interface mapping)."""
    topology = None
    if args.cable_path or args.beagle_position or args.target_identity:
        topology = {
            "cable_path": args.cable_path or "",
            "beagle_position": args.beagle_position or "",
            "target_identity": args.target_identity or "",
        }
    driver_state = None
    if args.official_app_driver or args.beagle_driver:
        driver_state = {
            "official_app": args.official_app_driver or "unknown",
            "beagle": args.beagle_driver or "unknown",
        }
    interface_mapping = None
    if args.interface_mapping:
        interface_mapping = json.loads(args.interface_mapping)
    return preflight(
        repo_root=Path(args.repo_root) if args.repo_root else None,
        output_root=args.output_root,
        host_interface=args.host_interface,
        target_beagle_port=args.target_beagle_port,
        target_state_confirmed=args.target_state_confirmed,
        topology=topology,
        driver_state=driver_state,
        interface_mapping=interface_mapping,
        offline_only=bool(getattr(args, "offline_only", False)),
    )


def _cli_preflight(args: argparse.Namespace) -> int:
    pf = _preflight_from_args(args)
    print(json.dumps(pf, indent=2, sort_keys=True))
    if pf["issues"]:
        print("\nHUMAN ACTION REQUIRED:")
        for action in pf["human_actions"]:
            print(f"  - {action}")
        return 2
    return 0


def _cli_build_manifest(args: argparse.Namespace) -> int:
    pf = _preflight_from_args(args)
    # build-manifest fails closed when preflight is incomplete; a blocked
    # preflight must not yield a manifest.
    if pf["issues"]:
        print(json.dumps({"blocked": True, "issues": pf["issues"], "human_actions": pf["human_actions"]},
                         indent=2, sort_keys=True))
        print("HUMAN ACTION REQUIRED: resolve the preflight blockers before building a manifest.")
        return 2
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
    nested = validate_manifest(manifest)
    if nested:
        print(json.dumps({"blocked": True, "validation_errors": nested}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def _cli_ingest_authorization(args: argparse.Namespace) -> int:
    # All authorized values are parsed from the fetched comment body; the CLI
    # only names the repository/issue/comment to fetch.
    envelope = ingest_authorization(
        repository=args.repository,
        issue=args.issue,
        comment_id=str(args.comment_id),
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
        refetch=not args.cached,
        expected_comment_id=args.expected_comment_id,
        expected_target=args.expected_target,
        expected_allowed_input_sequence=args.expected_allowed_input_sequence,
        expected_issued_utc=args.expected_issued_utc,
        expected_expires_utc=args.expected_expires_utc,
        expected_issue_url=args.expected_issue_url,
    )
    print(json.dumps({"ok": ok, "reason": reason, "cached": args.cached}, indent=2, sort_keys=True))
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

    for subparser in (sub.add_parser("preflight", help="no-live preflight; emits HUMAN ACTION REQUIRED"),
                      sub.add_parser("build-manifest", help="emit the experiment manifest")):
        subparser.add_argument("--repo-root")
        subparser.add_argument("--output-root", default=".work/evidence")
        subparser.add_argument("--host-interface")
        subparser.add_argument("--target-beagle-port", type=int, default=0)
        subparser.add_argument("--target-state-confirmed", action="store_true")
        subparser.add_argument("--cable-path")
        subparser.add_argument("--beagle-position")
        subparser.add_argument("--target-identity")
        subparser.add_argument("--official-app-driver")
        subparser.add_argument("--beagle-driver")
        subparser.add_argument("--offline-only", action="store_true",
                               help="select offline-only preflight: current KVM2USB device presence is not required")
        subparser.add_argument("--interface-mapping", help='JSON mapping, e.g. \'{"\\\\\\\\\\\\.\\\\USBPcap1":{"device_instance":"USB\\\\VID_2B77&PID_3661\\\\..."}}\'')
    p_pre = list(sub.choices.values())[0] if False else sub.choices.get("preflight")
    p_build = sub.choices.get("build-manifest")
    p_pre.set_defaults(func=_cli_preflight)
    p_build.add_argument("--correlation")
    p_build.add_argument("--operator")
    p_build.add_argument("--recovery-base-head")
    p_build.add_argument("--target-state-note")
    p_build.set_defaults(func=_cli_build_manifest)

    p_ing = sub.add_parser("ingest-authorization", help="fetch the issue comment via gh api and write a hash-pinned envelope")
    p_ing.add_argument("--repository", required=True)
    p_ing.add_argument("--issue", type=int, required=True)
    p_ing.add_argument("--comment-id", required=True)
    p_ing.add_argument("--output")
    p_ing.set_defaults(func=_cli_ingest_authorization)

    p_ver = sub.add_parser("verify-authorization", help="verify a cached evidence envelope against the current GitHub comment (or cached evidence)")
    p_ver.add_argument("--envelope", required=True)
    p_ver.add_argument("--experiment-id", required=True)
    p_ver.add_argument("--repository", required=True)
    p_ver.add_argument("--issue", type=int, required=True)
    p_ver.add_argument("--human-authority", required=True,
                       help="approved human authority (GitHub login) that must have posted the authorizing comment; required, never optional")
    p_ver.add_argument("--expected-comment-id",
                       help="expected comment id; compared against the envelope (never creates authorization)")
    p_ver.add_argument("--expected-target",
                       help="expected target identity; compared against the comment-derived target (never creates authorization)")
    p_ver.add_argument("--expected-allowed-input-sequence", action="append",
                       help="expected allowed input sequence item; repeatable (compared, never creates authorization)")
    p_ver.add_argument("--expected-issued-utc",
                       help="expected issued UTC; compared against the comment-derived value (never creates authorization)")
    p_ver.add_argument("--expected-expires-utc",
                       help="expected expiry UTC; compared against the comment-derived value (never creates authorization)")
    p_ver.add_argument("--expected-issue-url",
                       help="expected issue URL; compared against the envelope (never creates authorization)")
    p_ver.add_argument("--cached", action="store_true",
                       help="verify cached evidence only (no GitHub re-fetch); explicitly identified as cached evidence")
    p_ver.set_defaults(func=_cli_verify_authorization)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
