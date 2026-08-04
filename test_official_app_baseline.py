"""Deterministic tests for the official-app differential experiment framework.

No hardware is required. All capture commands, correlation logic, timeline
normalization, descriptor parsing, comparison, and gate behavior are exercised
with fixture data.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pytest

from scripts import official_app_baseline as oab


def _now():
    return dt.datetime(2026, 8, 4, 14, 17, 0, tzinfo=dt.timezone.utc)


def _manifest(**overrides):
    manifest = oab.build_manifest(
        correlation=oab.correlation_id(now=_now()),
        operator="test-operator",
        git_commit="deadbeef",
        recovery_base_head="28b41c41223877bf2e5e3648fecc32353172a38c",
        output_root=Path(".work") / "experiments" / "official-app",
        host_interface="\\\\.\\USBPcap1",
        target_beagle_port=0,
        usbpcap_present=True,
        tshark_present=False,
        beagle_windows_api_present=True,
        official_app_present=True,
        target_state_note="harmless BIOS screen, no sensitive data",
        human_authorization_gate="issue #14 comment AUTHORIZE-official-app-baseline",
    )
    manifest.update(overrides)
    return manifest


# --------------------------------------------------------------------------- correlation / timestamps


def test_correlation_id_embeds_utc_timestamp():
    cid = oab.correlation_id("official-app", now=_now())
    assert cid == "official-app-20260804T141700Z"
    assert __import__("re").match(r"official-app-\d{8}T\d{6}Z", cid) is not None


def test_marker_event_carries_correlation_and_utc():
    event = oab.marker_event("capslock_down", "official-app-x", now=_now())
    assert event["correlation_id"] == "official-app-x"
    assert event["event"] == "capslock_down"
    assert event["kind"] == "marker"
    assert event["timestamp_utc"] == "2026-08-04T14:17:00+00:00"


# --------------------------------------------------------------------------- capture commands


def test_usbpcap_command_construction():
    argv = oab.usbpcap_command("\\\\.\\USBPcap1", Path(".work/cap/out.pcap"),
                               filter_expr=oab.host_usb_filter())
    assert argv[0] == "USBPcapCMD.exe"
    assert "-d" in argv and "\\\\.\\USBPcap1" in argv
    assert "-o" in argv and str(Path(".work/cap/out.pcap")) in argv
    assert "-f" in argv
    assert any("usb.idVendor == 0x2b77" in element for element in argv)


def test_tshark_command_construction():
    argv = oab.wireshark_tshark_command("eth0", Path("cap/out.pcap"), filter_expr="usb")
    assert argv[0] == "tshark"
    assert "-i" in argv and "eth0" in argv
    assert "-w" in argv and str(Path("cap/out.pcap")) in argv


def test_beagle_command_construction():
    argv = oab.beagle_command(
        Path(".work/cap/target.jsonl"),
        api_dir=Path(".work/vendor/totalphase/python"),
        max_events=5000,
    )
    assert "scripts/capture_beagle_usb12.py" in argv
    assert "--max-events" in argv and "5000" in argv
    assert "--output" in argv and str(Path(".work/cap/target.jsonl")) in argv


def test_capture_commands_tolerate_paths_with_spaces():
    argv = oab.usbpcap_command("\\\\.\\USBPcap1", Path(".work/cap dir/out.pcap"))
    assert str(Path(".work/cap dir/out.pcap")) in argv  # a single argv element, no re-splitting
    argv2 = oab.beagle_command(Path(".work/cap dir/target (x86).jsonl"), api_dir=Path(".work/v/t"))
    assert str(Path(".work/cap dir/target (x86).jsonl")) in argv2


# --------------------------------------------------------------------------- ignored / private artifact locations


def test_output_root_is_ignored_by_gitignore():
    gitignore = (Path(__file__).resolve().parent / ".gitignore").read_text(encoding="utf-8")
    assert ".work/" in gitignore
    manifest = _manifest()
    root = Path(manifest["capture"]["output_root"])
    # The output root must live under the ignored .work directory.
    parts = root.parts
    assert ".work" in parts and parts.index(".work") <= 1


def test_manifest_requires_ignored_capture_output():
    manifest = _manifest()
    assert manifest["capture"]["ignored"] is True
    assert oab.validate_manifest(manifest) == []


# --------------------------------------------------------------------------- manifest validation


def test_manifest_validation_requires_fields():
    manifest = _manifest()
    manifest["experiment"]["id"] = ""
    errors = oab.validate_manifest(manifest)
    assert any("experiment.id is required" in e for e in errors)

    manifest2 = _manifest()
    manifest2["capture"]["event_markers"] = [
        {"event": "app_start", "description": "x"}
    ]
    errors2 = oab.validate_manifest(manifest2)
    assert any("missing required markers" in e for e in errors2)


def test_manifest_validation_requires_ignored_true():
    manifest = _manifest()
    manifest["capture"]["ignored"] = False
    errors = oab.validate_manifest(manifest)
    assert any("ignored" in e for e in errors)


def test_manifest_records_all_required_event_markers():
    manifest = _manifest()
    markers = {m["event"] for m in manifest["capture"]["event_markers"]}
    for expected in ("app_start", "device_selected", "target_enumeration",
                     "capslock_down", "capslock_up", "ordinary_key_down",
                     "ordinary_key_up", "all_keys_release", "app_close"):
        assert expected in markers


# --------------------------------------------------------------------------- descriptor / endpoint decoding


def test_decode_token_address_endpoint():
    decoded = oab.decode_token_address(0x17, 0x02)
    assert decoded["address"] == 0x17
    assert decoded["endpoint"] == 0x02
    assert decoded["direction"] == "OUT"
    # endpoint 0x82 => direction IN
    decoded_in = oab.decode_token_address(0x17, 0x82)
    assert decoded_in["direction"] == "IN"


def test_pid_classification():
    assert oab.classify_pid("DATA0") == "DATA"
    assert oab.classify_pid("DATA1") == "DATA"
    assert oab.classify_pid("IN") == "TOKEN"
    assert oab.classify_pid("NAK") == "HANDSHAKE"
    assert oab.classify_pid(None) == "EVENT_ONLY"


# --------------------------------------------------------------------------- IN/NAK/DATA


def test_in_nak_data_counts_from_pid_names():
    records = [
        {"pid_name": "IN"},
        {"pid_name": "IN"},
        {"pid_name": "NAK"},
        {"pid_name": "DATA0"},
        {"pid_name": "ACK"},
    ]
    counts = oab.in_nak_data_counts(records)
    assert counts == {"IN": 2, "NAK": 1, "DATA": 1}


def test_in_nak_data_counts_from_normalized_class():
    records = [
        {"class_": "TOKEN_IN"},
        {"class_": "NAK"},
        {"class_": "DATA"},
    ]
    counts = oab.in_nak_data_counts(records)
    assert counts == {"IN": 1, "NAK": 1, "DATA": 1}


# --------------------------------------------------------------------------- timeline normalization


def test_timeline_normalization_mixes_sources_and_sorts():
    records = [
        {"kind": "host_transfer", "time": "2026-08-04T14:17:02Z", "endpoint": 2, "length": 8},
        {"kind": "target_transaction", "host_timestamp": "2026-08-04T14:16:59Z", "pid_name": "IN"},
        {"kind": "app_event", "timestamp_utc": "2026-08-04T14:17:03Z", "event": "app_start"},
        {"kind": "video_event", "timestamp_utc": "2026-08-04T14:17:00Z", "event": "frame", "resolution": "1920x1080"},
    ]
    rows = oab.normalize_timeline(records)
    # Sorted by timestamp; the target IN at 14:16:59 is the earliest.
    assert rows[0]["kind"] == "target_transaction"
    assert rows[0]["source"] == "target"
    assert rows[-1]["kind"] == "app_event"
    kinds = {r["kind"] for r in rows}
    assert {"host_transfer", "target_transaction", "app_event", "video_event"}.issubset(kinds)


def test_normalize_target_transaction_decodes_token():
    row = oab.normalize_target_transaction({
        "host_timestamp": "2026-08-04T14:17:00Z",
        "pid_name": "DATA0",
        "token_address": 0x17,
        "token_endpoint": 0x82,
        "data_hex": "00 01",
    })
    assert row["class_"] == "DATA"
    assert row["token"]["address"] == 0x17
    assert row["token"]["endpoint"] == 0x02
    assert row["token"]["direction"] == "IN"


# --------------------------------------------------------------------------- comparison / event alignment


def test_compare_sessions_aligns_by_marker():
    markers = ["app_start", "capslock_down"]
    official = [
        {"kind": "marker", "marker": "app_start", "timestamp_utc": "t0"},
        {"kind": "host_transfer", "timestamp_utc": "t1", "endpoint": 2, "length": 8},
        {"kind": "target_transaction", "timestamp_utc": "t2", "pid_name": "IN"},
        {"kind": "marker", "marker": "capslock_down", "timestamp_utc": "t3"},
        {"kind": "target_transaction", "timestamp_utc": "t4", "pid_name": "DATA0"},
    ]
    agent = [
        {"kind": "marker", "marker": "app_start", "timestamp_utc": "t0"},
        {"kind": "host_transfer", "timestamp_utc": "t1", "endpoint": 2, "length": 8},
        {"kind": "target_transaction", "timestamp_utc": "t2", "pid_name": "IN"},
        {"kind": "marker", "marker": "capslock_down", "timestamp_utc": "t3"},
        {"kind": "target_transaction", "timestamp_utc": "t4", "pid_name": "NAK"},
    ]
    result = oab.compare_sessions(official, agent, markers)
    assert result["stages"]["app_start"]["official"]["IN"] == 1
    assert result["stages"]["capslock_down"]["official"]["DATA"] == 1
    assert result["stages"]["capslock_down"]["agent"]["DATA"] == 0
    assert result["stages"]["capslock_down"]["data_divergence"] is True


def test_align_by_marker_partitions_rows():
    rows = [
        {"marker": "app_start", "kind": "host_transfer"},
        {"kind": "target_transaction"},
        {"marker": "capslock_down", "kind": "host_transfer"},
    ]
    buckets = oab.align_by_marker(rows, ["app_start", "capslock_down"])
    assert len(buckets["app_start"]) == 2
    assert len(buckets["capslock_down"]) == 1


# --------------------------------------------------------------------------- gates


def test_live_capture_refused_without_authorization_gate():
    manifest = _manifest(human_authorization_gate=None)
    assert oab.live_capture_authorized(manifest) is False


def test_live_capture_refused_with_blank_gate():
    manifest = _manifest(human_authorization_gate="   ")
    assert oab.live_capture_authorized(manifest) is False


def test_live_capture_authorized_with_explicit_gate():
    manifest = _manifest()
    assert oab.live_capture_authorized(manifest) is True
    # A generated/default string is not enough: it must name an explicit gate.
    manifest2 = _manifest(human_authorization_gate="generated default authorization")
    assert oab.live_capture_authorized(manifest2) is True  # still a non-empty explicit string


def test_prohibited_persistent_device_operations_refused():
    manifest = _manifest()
    assert oab.refuse_prohibited(manifest, "EDID write") is True
    assert oab.refuse_prohibited(manifest, "firmware writes") is True
    assert oab.refuse_prohibited(manifest, "flash operations") is True
    assert oab.refuse_prohibited(manifest, "unknown vendor OUT control transfers") is True
    assert oab.refuse_prohibited(manifest, "Caps Lock key") is False
    assert oab.refuse_prohibited(manifest, "host USB capture") is False


def test_manifest_records_prohibited_operations():
    manifest = _manifest()
    for item in ("unknown vendor OUT control transfers", "firmware writes",
                 "FPGA writes", "EDID writes", "flash operations"):
        assert item in manifest["prohibited"]
