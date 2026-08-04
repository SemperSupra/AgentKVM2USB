"""Deterministic tests for the official-app differential experiment framework.

No hardware is required. All capture commands, correlation logic, timeline
normalization, descriptor parsing, comparison, authorization, and path
validation are exercised with fixture data. End-to-end self-consistency tests
use the real generator, normalizer, counter, comparison, path validator, and
authorization validator together.
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


def _auth_record(**overrides):
    record = oab.build_authorization_record(
        canonical_issue=14,
        comment_id="5180000000",
        comment_url="https://github.com/SemperSupra/AgentKVM2USB/issues/14#issuecomment-5180000000",
        author="human",
        authority="issue #14 explicit authorization",
        experiment_id="official-app-x",
        allowed_input_sequence=["capslock_down", "capslock_up", "ordinary_key_down", "ordinary_key_up", "all_keys_release"],
        target="Wyse 5070",
        issued_utc="2026-08-04T14:00:00+00:00",
        expires_utc="2026-08-04T18:00:00+00:00",
    )
    record.update(overrides)
    return record


def _manifest(**overrides):
    manifest = oab.build_manifest(
        correlation=oab.correlation_id(now=_now()),
        operator="test-operator",
        git_commit="deadbeef",
        recovery_base_head="28b41c41223877bf2e5e3648fecc32353172a38c",
        output_root=".work/evidence/official-app-x",
        host_interface="\\\\.\\USBPcap1",
        target_beagle_port=0,
        usbpcap_present=True,
        tshark_present=True,
        beagle_windows_api_present=True,
        official_app_present=True,
        target_state_note="harmless BIOS screen, no sensitive data",
        authorization_record=_auth_record(),
    )
    manifest.update(overrides)
    return manifest


# --------------------------------------------------------------------------- correlation / timestamps


def test_correlation_id_embeds_utc_timestamp():
    cid = oab.correlation_id("official-app", now=_now())
    assert cid == "official-app-20260804T141700Z"
    assert __import__("re").match(r"official-app-\d{8}T\d{6}Z", cid) is not None


# --------------------------------------------------------------------------- capture commands


def test_usbpcap_command_uses_interface_selection_not_capture_filter():
    argv = oab.usbpcap_command("\\\\.\\USBPcap1", Path(".work/cap/out.pcap"))
    assert argv[0] == "USBPcapCMD.exe"
    assert "-d" in argv and "\\\\.\\USBPcap1" in argv
    assert "-o" in argv and str(Path(".work/cap/out.pcap")) in argv
    # No libpcap capture filter expression is passed.
    assert "-f" not in argv


def test_usbpcap_display_filter_is_post_capture():
    filt = oab.host_usb_display_filter()
    assert filt == "usb.idVendor == 0x2b77 && usb.idProduct == 0x3661"
    # It is used as a display filter (-Y), not a capture filter (-f).
    argv = oab.tshark_decode_command(Path("cap.pcap"), display_filter=filt)
    assert "-Y" in argv and filt in argv
    assert "-f" not in argv


def test_tshark_capture_command_avoids_capture_filter():
    argv = oab.wireshark_tshark_command("eth0", Path("cap/out.pcap"))
    assert argv[0] == "tshark"
    assert "-i" in argv and "eth0" in argv
    assert "-f" not in argv


def test_beagle_command_construction():
    argv = oab.beagle_command(
        Path(".work/cap/target.jsonl"),
        api_dir=Path(".work/vendor/totalphase/python"),
        max_events=5000,
    )
    assert "scripts/capture_beagle_usb12.py" in argv
    assert "--output" in argv and str(Path(".work/cap/target.jsonl")) in argv


def test_capture_commands_tolerate_paths_with_spaces():
    argv = oab.usbpcap_command("\\\\.\\USBPcap1", Path(".work/cap dir/out.pcap"))
    assert str(Path(".work/cap dir/out.pcap")) in argv
    argv2 = oab.beagle_command(Path(".work/cap dir/target (x86).jsonl"), api_dir=Path(".work/v/t"))
    assert str(Path(".work/cap dir/target (x86).jsonl")) in argv2


# --------------------------------------------------------------------------- token identity / direction


def test_token_direction_derived_from_pid_not_endpoint_bit():
    # Token direction comes from the PID, never from endpoint bit 7.
    assert oab.token_direction_from_pid("IN") == "IN"
    assert oab.token_direction_from_pid("OUT") == "OUT"
    assert oab.token_direction_from_pid("SETUP") == "SETUP"
    assert oab.token_direction_from_pid("DATA0") is None


def test_descriptor_endpoint_address_uses_bit7():
    # Descriptor endpoint-address decoding is separate and uses bit 7.
    assert oab.decode_descriptor_endpoint_address(0x02) == {"endpoint_number": 2, "direction": "OUT"}
    assert oab.decode_descriptor_endpoint_address(0x82) == {"endpoint_number": 2, "direction": "IN"}


def test_token_pid_preserved_through_classification():
    assert oab.classify_pid("IN") == "TOKEN_IN"
    assert oab.classify_pid("OUT") == "TOKEN_OUT"
    assert oab.classify_pid("SETUP") == "TOKEN_SETUP"
    assert oab.classify_pid("NAK") == "HANDSHAKE"
    assert oab.classify_pid("DATA0") == "DATA"


def test_in_nak_data_counts_preserve_token_identity():
    records = [
        {"pid_name": "IN"},
        {"pid_name": "IN"},
        {"pid_name": "OUT"},
        {"pid_name": "SETUP"},
        {"pid_name": "NAK"},
        {"pid_name": "DATA0"},
        {"pid_name": "DATA1"},
    ]
    counts = oab.in_nak_data_counts(records)
    assert counts == {"IN": 2, "OUT": 1, "SETUP": 1, "NAK": 1, "DATA": 2}


def test_normalized_class_counts_token_identity():
    records = [
        {"class_": "TOKEN_IN"},
        {"class_": "TOKEN_OUT"},
        {"class_": "TOKEN_SETUP"},
        {"class_": "NAK"},
        {"class_": "DATA"},
    ]
    counts = oab.in_nak_data_counts(records)
    assert counts == {"IN": 1, "OUT": 1, "SETUP": 1, "NAK": 1, "DATA": 1}


# --------------------------------------------------------------------------- output path validation


def test_output_path_resolves_and_is_git_ignored():
    result = oab.verify_output_path(".work/evidence/official-app-x/host.pcap")
    assert result["ok"] is True
    assert result["git_ignored"] is True
    assert ".work" in result["resolved"]


def test_output_path_escaping_approved_root_rejected():
    with pytest.raises(ValueError):
        oab.resolve_output_path(r"C:\Windows\Temp\escape.pcap")
    result = oab.verify_output_path(r"C:\Windows\Temp\escape.pcap")
    assert result["ok"] is False
    assert any("not under approved root" in e for e in result["errors"])


# --------------------------------------------------------------------------- structured authorization


def test_authorization_requires_structured_record():
    ok, reason = oab.live_capture_authorized(None, experiment_id="official-app-x", now_utc=_now())
    assert ok is False and "no structured authorization record" in reason


def test_authorization_requires_experiment_specific():
    rec = _auth_record(experiment_id="other-experiment")
    ok, reason = oab.live_capture_authorized(rec, experiment_id="official-app-x", now_utc=_now())
    assert ok is False and "experiment_id" in reason


def test_authorization_rejects_generic_authority():
    rec = _auth_record(authority="generated default authorization")
    ok, _ = oab.live_capture_authorized(rec, experiment_id="official-app-x", now_utc=_now())
    assert ok is False


def test_authorization_rejects_expired():
    rec = _auth_record(expires_utc="2026-08-04T12:00:00+00:00")  # before now
    ok, reason = oab.live_capture_authorized(rec, experiment_id="official-app-x", now_utc=_now())
    assert ok is False and "expired" in reason


def test_authorization_valid_structured_record():
    ok, reason = oab.live_capture_authorized(_auth_record(), experiment_id="official-app-x", now_utc=_now())
    assert ok is True


def test_no_generic_live_bypass_exists():
    # The module must not implement a generic --allow-live flag. It has no
    # argparse CLI entry point; the only live gate is the structured record.
    source = Path(oab.__file__).read_text(encoding="utf-8")
    assert "argparse" not in source
    assert "add_argument" not in source
    assert "live_capture_authorized" in source  # the only live gate is the structured record


# --------------------------------------------------------------------------- marker / timeline alignment


def test_marker_contract_is_unified():
    # marker_event() sets both event and marker so align_by_marker works on the
    # real generated records, not fabricated marker fields.
    record = oab.marker_event("capslock_down", "cid", now=_now())
    assert record["kind"] == "marker"
    assert record["marker"] == record["event"] == "capslock_down"
    aligned = oab.align_by_marker([record, {"kind": "host_transfer", "marker": "capslock_down"}],
                                  ["capslock_down"])
    assert len(aligned["capslock_down"]) == 2


def test_timeline_normalization_mixes_sources_and_sorts():
    records = [
        {"kind": "host_transfer", "time": "2026-08-04T14:17:02Z", "endpoint": 2, "length": 8},
        {"kind": "target_transaction", "host_timestamp": "2026-08-04T14:16:59Z", "pid_name": "IN"},
        {"kind": "app_event", "timestamp_utc": "2026-08-04T14:17:03Z", "event": "app_start"},
        {"kind": "video_event", "timestamp_utc": "2026-08-04T14:17:00Z", "event": "frame", "resolution": "1920x1080"},
    ]
    rows = oab.normalize_timeline(records)
    assert rows[0]["kind"] == "target_transaction"
    assert rows[-1]["kind"] == "app_event"
    kinds = {r["kind"] for r in rows}
    assert {"host_transfer", "target_transaction", "app_event", "video_event"}.issubset(kinds)


def test_normalize_target_transaction_uses_pid_direction():
    row = oab.normalize_target_transaction({
        "host_timestamp": "2026-08-04T14:17:00Z",
        "pid_name": "IN",
        "token_address": 0x17,
        "token_endpoint": 0x82,
    })
    assert row["class_"] == "TOKEN_IN"
    assert row["token_direction"] == "IN"
    # Token endpoint is a number (2), not a direction-bearing address.
    assert row["token"]["endpoint_number"] == 2
    assert row["token"]["direction"] == "IN"


# --------------------------------------------------------------------------- comparison


def test_compare_sessions_detects_host_and_target_divergence():
    markers = ["app_start", "capslock_down"]
    official = [
        {"kind": "marker", "event": "app_start", "marker": "app_start", "timestamp_utc": "t0"},
        {"kind": "host_transfer", "timestamp_utc": "t1", "transfer_type": "interrupt", "collection": "keyboard",
         "endpoint": 2, "report_id": 1, "length": 8, "payload": "00 01"},
        {"kind": "target_transaction", "timestamp_utc": "t2", "pid_name": "IN"},
        {"kind": "marker", "event": "capslock_down", "marker": "capslock_down", "timestamp_utc": "t3"},
        {"kind": "target_transaction", "timestamp_utc": "t4", "pid_name": "DATA0"},
    ]
    agent = [
        {"kind": "marker", "event": "app_start", "marker": "app_start", "timestamp_utc": "t0"},
        {"kind": "host_transfer", "timestamp_utc": "t1", "transfer_type": "interrupt", "collection": "keyboard",
         "endpoint": 2, "report_id": 1, "length": 8, "payload": "00 02"},  # payload differs
        {"kind": "target_transaction", "timestamp_utc": "t2", "pid_name": "IN"},
        {"kind": "marker", "event": "capslock_down", "marker": "capslock_down", "timestamp_utc": "t3"},
        {"kind": "target_transaction", "timestamp_utc": "t4", "pid_name": "NAK"},
    ]
    result = oab.compare_sessions(official, agent, markers)
    # Host-side divergence on payload.
    assert result["first_divergence"]["field"] == "payload"
    assert result["first_divergence"]["side"] == "host"
    # Target-side divergence in the capslock stage: agent NAK vs official DATA.
    assert result["stages"]["capslock_down"]["official"]["DATA"] == 1
    assert result["stages"]["capslock_down"]["agent"]["DATA"] == 0
    assert result["stages"]["capslock_down"]["agent"]["NAK"] == 1
    assert result["stages"]["capslock_down"]["target_divergence"]["side"] == "target"


# --------------------------------------------------------------------------- manifest validation


def test_manifest_validation_requires_fields():
    manifest = _manifest()
    assert oab.validate_manifest(manifest) == []
    manifest["experiment"]["id"] = ""
    errors = oab.validate_manifest(manifest)
    assert any("experiment.id is required" in e for e in errors)


def test_manifest_requires_all_event_markers():
    manifest = _manifest()
    manifest["capture"]["event_markers"] = [{"event": "app_start", "description": "x"}]
    errors = oab.validate_manifest(manifest)
    assert any("missing required markers" in e for e in errors)


def test_manifest_records_prohibited_operations():
    manifest = _manifest()
    for item in ("unknown vendor OUT control transfers", "firmware writes",
                 "FPGA writes", "EDID writes", "flash operations"):
        assert item in manifest["prohibited"]


def test_prohibited_operations_refused():
    manifest = _manifest()
    assert oab.refuse_prohibited(manifest, "EDID write") is True
    assert oab.refuse_prohibited(manifest, "firmware writes") is True
    assert oab.refuse_prohibited(manifest, "unknown vendor OUT control transfers") is True
    assert oab.refuse_prohibited(manifest, "Caps Lock key") is False
    assert oab.refuse_prohibited(manifest, "host USB capture") is False


# --------------------------------------------------------------------------- no-live preflight


def test_preflight_disables_live_and_reports_missing_tools():
    pf = oab.preflight()
    assert pf["live_disabled"] is True
    assert pf["authorization_required"]
    # On this host USBPcap/TShark are not installed; preflight must report it.
    assert pf["detected"]["usbpcap_cmd"] is None or pf["detected"]["tshark"] is None


def test_preflight_returns_human_actions_for_missing_tools():
    pf = oab.preflight()
    actions = " ".join(pf["human_actions"]).lower()
    assert "install" in actions


# --------------------------------------------------------------------------- end-to-end self-consistency


def test_end_to_end_marker_normalize_count_compare_path_authorization():
    """Exercise the real generator, normalizer, counter, comparison, path
    validator, and authorization validator together for one session."""
    markers = [m["event"] for m in oab.DEFAULT_MARKERS]
    correlation = oab.correlation_id(now=_now())

    def ts(i, j):
        base = dt.datetime(2026, 8, 4, 14, 17, 0, tzinfo=dt.timezone.utc)
        return (base + dt.timedelta(seconds=i * 2 + j)).isoformat()

    official_rows = []
    agent_rows = []
    for i, marker in enumerate(markers):
        official_rows.append(oab.marker_event(marker, correlation))
        agent_rows.append(oab.marker_event(marker, correlation))
        # Host transfer + target transaction per stage.
        official_rows.append({"kind": "host_transfer", "timestamp_utc": ts(i, 0),
                              "transfer_type": "interrupt", "collection": "keyboard",
                              "endpoint": 2, "report_id": 1, "length": 8, "payload": "00 01",
                              "marker": marker})
        official_rows.append({"kind": "target_transaction", "host_timestamp": ts(i, 1),
                              "pid_name": "IN", "marker": marker})
        agent_rows.append({"kind": "host_transfer", "timestamp_utc": ts(i, 0),
                           "transfer_type": "interrupt", "collection": "keyboard",
                           "endpoint": 2, "report_id": 1, "length": 8, "payload": "00 01",
                           "marker": marker})
        agent_rows.append({"kind": "target_transaction", "host_timestamp": ts(i, 1),
                           "pid_name": "IN", "marker": marker})

    # Real normalizer.
    official_norm = oab.normalize_timeline(official_rows)
    agent_norm = oab.normalize_timeline(agent_rows)
    # Real counter + comparison.
    result = oab.compare_sessions(official_norm, agent_norm, markers)
    assert result["first_divergence"] is None  # identical sessions
    assert result["summary"]["official_IN"] == result["summary"]["agent_IN"] > 0
    assert result["summary"]["official_DATA"] == 0

    # Real path validator.
    path_result = oab.verify_output_path(".work/evidence/official-app-x/host.pcap")
    assert path_result["ok"] is True

    # Real authorization validator (aligned to the session experiment id).
    auth_ok, reason = oab.live_capture_authorized(
        _auth_record(experiment_id=correlation), experiment_id=correlation, now_utc=_now()
    )
    assert auth_ok is True
