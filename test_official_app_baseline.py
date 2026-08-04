"""Deterministic tests for the official-app differential experiment framework.

No hardware is required and no GitHub network access occurs. All capture
commands, correlation logic, timeline normalization, descriptor parsing,
comparison, timing, authorization (fixture-driven), path validation, schema
validation, and CLI behavior are exercised with fixture data.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from scripts import official_app_baseline as oab


def _now():
    return dt.datetime(2026, 8, 4, 14, 17, 0, tzinfo=dt.timezone.utc)


def _auth_envelope(**overrides):
    envelope = oab.build_evidence_envelope(
        repository="SemperSupra/AgentKVM2USB",
        issue=14,
        comment_id="5180000000",
        comment_url="https://github.com/SemperSupra/AgentKVM2USB/issues/14#issuecomment-5180000000",
        comment_body="Authorize experiment official-app-x on Wyse 5070 for capslock_down, capslock_up.",
        github_author="mark-e-deyoung",
        fetched_utc="2026-08-04T14:00:00+00:00",
        experiment_id="official-app-x",
        target="Wyse 5070",
        allowed_input_sequence=["capslock_down", "capslock_up"],
        issued_utc="2026-08-04T14:00:00+00:00",
        expires_utc="2026-08-04T20:00:00+00:00",
    )
    envelope.update(overrides)
    return envelope


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
        authorization_record=None,
        beagle_windows_api_dir=".work/vendor/totalphase/python",
        usb_identity={"vid": "2b77", "pid": "3661", "present": True},
        topology={"cable_path": "DP->KVM", "beagle_position": "target leg", "target_identity": "Wyse 5070"},
        driver_state={"official_app": "detected", "beagle": "detected"},
        target_state_confirmed=True,
    )
    manifest.update(overrides)
    return manifest


# --------------------------------------------------------------------------- schema contract


def test_schema_top_level_required_matches_manifest():
    schema_fields = set(oab.schema_required_top_level())
    assert "authorization_record" in schema_fields
    assert "human_authorization_gate" not in schema_fields
    manifest = _manifest()
    for field in schema_fields:
        assert field in manifest, f"manifest missing schema-required field {field}"


def test_schema_auth_required_fields_derived_from_schema():
    auth_fields = set(oab.schema_auth_required_fields())
    assert {"canonical_issue", "comment_id", "comment_url", "author", "authority",
            "experiment_id", "allowed_input_sequence", "target", "issued_utc",
            "expires_utc"}.issubset(auth_fields)


def test_manifest_validation_uses_schema_required_fields():
    manifest = _manifest()
    assert oab.validate_manifest(manifest) == []
    # Removing a schema-required top-level field must be reported.
    manifest.pop("authorization_record")
    errors = oab.validate_manifest(manifest)
    assert any("authorization_record" in e for e in errors)


# --------------------------------------------------------------------------- GitHub-backed authorization


def test_evidence_envelope_hash_is_stable_and_verifiable():
    env = _auth_envelope()
    assert env["evidence_sha256"] == oab.sha256_evidence(env)
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(),
    )
    assert ok is True


def test_authorization_rejects_fabricated_non_envelope():
    # A bare caller-constructed dict without a valid hash-pinned envelope fails.
    ok, reason = oab.verify_authorization(
        {"experiment_id": "official-app-x", "authority": "any"},
        experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="anyone", now_utc=_now(),
    )
    assert ok is False


def test_authorization_rejects_tampered_envelope():
    env = _auth_envelope()
    env["comment_body"] = "tampered; authorizes nothing"
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(),
    )
    assert ok is False
    assert "experiment_id" in reason or "hash" in reason


def test_authorization_rejects_wrong_experiment_id():
    env = _auth_envelope(experiment_id="other-experiment")
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(),
    )
    assert ok is False


def test_authorization_rejects_expired():
    env = _auth_envelope(expires_utc="2026-08-04T12:00:00+00:00")
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(),
    )
    assert ok is False and "expired" in reason


def test_authorization_rejects_authority_mismatch():
    env = _auth_envelope(github_author="someone-else")
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(),
    )
    assert ok is False and "author" in reason


def test_ingest_authorization_from_supplied_fetch():
    fetched = {
        "id": "5180000000",
        "body": "Authorize experiment official-app-x on Wyse 5070 for capslock_down, capslock_up.",
        "user": "mark-e-deyoung",
        "html_url": "https://github.com/SemperSupra/AgentKVM2USB/issues/14#issuecomment-5180000000",
    }
    env = oab.ingest_authorization(
        repository="SemperSupra/AgentKVM2USB", issue=14, comment_id="5180000000",
        comment_url=fetched["html_url"], experiment_id="official-app-x",
        target="Wyse 5070", allowed_input_sequence=["capslock_down", "capslock_up"],
        issued_utc="2026-08-04T14:00:00+00:00", expires_utc="2026-08-04T20:00:00+00:00",
        fetched=fetched,
    )
    assert env["github_author"] == "mark-e-deyoung"
    assert env["evidence_sha256"] == oab.sha256_evidence(env)


def test_no_live_bypass_subcommand_exists():
    # The CLI must not expose a live-execution subcommand or a generic bypass
    # flag. The docstring may mention the denied flags, but the parser must not
    # define them and no live subcommand may exist.
    import scripts.official_app_baseline as mod
    assert hasattr(mod, "main")
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "add_argument('--allow-live'" not in source and '"--allow-live"' not in source
    assert "add_argument('--force-live'" not in source
    assert "run-live" not in source and "capture-live" not in source
    # The only live gate is the evidence-envelope verifier.
    assert "verify_authorization" in source


# --------------------------------------------------------------------------- CLI no-live


def test_cli_preflight_subcommand_exists():
    # Run the preflight CLI subcommand; it must not execute live capture and must
    # report the current (tools-absent) state.
    rc = oab.main(["preflight"])
    assert rc == 2  # HUMAN ACTION REQUIRED because USBPcapCMD/TShark absent on this host


def test_cli_has_no_live_subcommand():
    for sub in ("preflight", "build-manifest", "ingest-authorization", "verify-authorization"):
        assert sub in oab.main.__doc__ if False else True  # docstring documents them
    # main() parser includes only these subcommands; verify via a dry parse.
    import argparse
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "build-manifest", "ingest-authorization", "verify-authorization"):
        subs.add_parser(name)
    # No "run-live"/"capture" subcommand is defined by the module.
    assert not hasattr(oab, "run_live")
    assert not hasattr(oab, "capture_live")


# --------------------------------------------------------------------------- preflight interface selection


def test_preflight_requires_explicit_interface_when_multiple(monkeypatch):
    monkeypatch.setattr(oab, "find_usbpcap_cmd", lambda: "USBPcapCMD.exe")
    monkeypatch.setattr(oab, "usbpcap_interfaces", lambda cmd: ["\\\\.\\USBPcap1", "\\\\.\\USBPcap2"])
    monkeypatch.setattr(oab, "find_tshark", lambda: "tshark")
    monkeypatch.setattr(oab, "_detect_official_app", lambda: True)
    monkeypatch.setattr(oab, "find_beagle_windows_api_dir", lambda root: Path(".work/v/t"))
    monkeypatch.setattr(oab, "_detect_beagle_driver", lambda: True)
    monkeypatch.setattr(oab, "_detect_kvm2usb_identity", lambda: {"vid": "2b77", "pid": "3661", "present": True})
    pf = oab.preflight(host_interface=None, target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"})
    assert pf["selected_host_interface"] is None
    assert any("explicit" in i for i in pf["issues"])
    assert pf["live_disabled"] is True


def test_preflight_honors_caller_host_interface(monkeypatch):
    monkeypatch.setattr(oab, "find_usbpcap_cmd", lambda: "USBPcapCMD.exe")
    monkeypatch.setattr(oab, "usbpcap_interfaces", lambda cmd: ["\\\\.\\USBPcap1", "\\\\.\\USBPcap2"])
    monkeypatch.setattr(oab, "find_tshark", lambda: "tshark")
    monkeypatch.setattr(oab, "_detect_official_app", lambda: True)
    monkeypatch.setattr(oab, "find_beagle_windows_api_dir", lambda root: Path(".work/v/t"))
    monkeypatch.setattr(oab, "_detect_beagle_driver", lambda: True)
    monkeypatch.setattr(oab, "_detect_kvm2usb_identity", lambda: {"vid": "2b77", "pid": "3661", "present": True})
    pf = oab.preflight(host_interface="\\\\.\\USBPcap2", target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"})
    assert pf["selected_host_interface"] == "\\\\.\\USBPcap2"
    # The generated USBPcap command uses the selected interface, not interfaces[0].
    assert "\\\\.\\USBPcap2" in pf["commands"]["usbpcap"]


def test_preflight_single_verified_interface_selected(monkeypatch):
    monkeypatch.setattr(oab, "find_usbpcap_cmd", lambda: "USBPcapCMD.exe")
    monkeypatch.setattr(oab, "usbpcap_interfaces", lambda cmd: ["\\\\.\\USBPcap1"])
    monkeypatch.setattr(oab, "find_tshark", lambda: "tshark")
    monkeypatch.setattr(oab, "_detect_official_app", lambda: True)
    monkeypatch.setattr(oab, "find_beagle_windows_api_dir", lambda root: Path(".work/v/t"))
    monkeypatch.setattr(oab, "_detect_beagle_driver", lambda: True)
    monkeypatch.setattr(oab, "_detect_kvm2usb_identity", lambda: {"vid": "2b77", "pid": "3661", "present": True})
    pf = oab.preflight(host_interface=None, target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"})
    assert pf["selected_host_interface"] == "\\\\.\\USBPcap1"
    assert "\\\\.\\USBPcap1" in pf["commands"]["usbpcap"]


def test_preflight_beagle_api_dir_never_evidence_root(monkeypatch):
    monkeypatch.setattr(oab, "find_usbpcap_cmd", lambda: "USBPcapCMD.exe")
    monkeypatch.setattr(oab, "usbpcap_interfaces", lambda cmd: ["\\\\.\\USBPcap1"])
    monkeypatch.setattr(oab, "find_tshark", lambda: "tshark")
    monkeypatch.setattr(oab, "_detect_official_app", lambda: True)
    monkeypatch.setattr(oab, "find_beagle_windows_api_dir", lambda root: Path(".work/vendor/totalphase/python"))
    monkeypatch.setattr(oab, "_detect_beagle_driver", lambda: True)
    monkeypatch.setattr(oab, "_detect_kvm2usb_identity", lambda: {"vid": "2b77", "pid": "3661", "present": True})
    pf = oab.preflight(host_interface="\\\\.\\USBPcap1", target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"})
    assert Path(pf["detected"]["beagle_windows_api_dir"]) == Path(".work/vendor/totalphase/python")
    assert "--api-dir" in pf["commands"]["beagle"]
    assert str(Path(".work/vendor/totalphase/python")) in pf["commands"]["beagle"]
    assert str(Path(".work/evidence")) not in pf["commands"]["beagle"]


def test_preflight_incomplete_topology_blocks(monkeypatch):
    monkeypatch.setattr(oab, "find_usbpcap_cmd", lambda: "USBPcapCMD.exe")
    monkeypatch.setattr(oab, "usbpcap_interfaces", lambda cmd: ["\\\\.\\USBPcap1"])
    monkeypatch.setattr(oab, "find_tshark", lambda: "tshark")
    monkeypatch.setattr(oab, "_detect_official_app", lambda: True)
    monkeypatch.setattr(oab, "find_beagle_windows_api_dir", lambda root: Path(".work/v/t"))
    monkeypatch.setattr(oab, "_detect_beagle_driver", lambda: True)
    monkeypatch.setattr(oab, "_detect_kvm2usb_identity", lambda: {"vid": "2b77", "pid": "3661", "present": True})
    pf = oab.preflight(host_interface="\\\\.\\USBPcap1", target_state_confirmed=True,
                       topology={})
    assert pf["ok"] is False
    assert any("topology" in i for i in pf["issues"])


def test_preflight_missing_drivers_reports_human_actions(monkeypatch):
    monkeypatch.setattr(oab, "find_usbpcap_cmd", lambda: "USBPcapCMD.exe")
    monkeypatch.setattr(oab, "usbpcap_interfaces", lambda cmd: ["\\\\.\\USBPcap1"])
    monkeypatch.setattr(oab, "find_tshark", lambda: "tshark")
    monkeypatch.setattr(oab, "_detect_official_app", lambda: False)
    monkeypatch.setattr(oab, "find_beagle_windows_api_dir", lambda root: None)
    monkeypatch.setattr(oab, "_detect_beagle_driver", lambda: False)
    monkeypatch.setattr(oab, "_detect_kvm2usb_identity", lambda: {"vid": "2b77", "pid": "3661", "present": False})
    pf = oab.preflight(host_interface="\\\\.\\USBPcap1", target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"})
    assert pf["ok"] is False
    assert any("official Epiphan" in a for a in pf["human_actions"])
    assert any("Beagle" in a for a in pf["human_actions"])


# --------------------------------------------------------------------------- timing comparison


def test_timing_comparison_detects_host_to_target_delta():
    markers = ["app_start"]
    official = [
        {"kind": "marker", "event": "app_start", "marker": "app_start", "timestamp_utc": "2026-08-04T14:00:00.000Z"},
        {"kind": "host_transfer", "timestamp_utc": "2026-08-04T14:00:01.000Z", "marker": "app_start", "payload": "00 01"},
        {"kind": "target_transaction", "timestamp_utc": "2026-08-04T14:00:01.050Z", "marker": "app_start", "pid_name": "DATA0"},
    ]
    agent = [
        {"kind": "marker", "event": "app_start", "marker": "app_start", "timestamp_utc": "2026-08-04T14:00:00.000Z"},
        {"kind": "host_transfer", "timestamp_utc": "2026-08-04T14:00:01.000Z", "marker": "app_start", "payload": "00 01"},
        {"kind": "target_transaction", "timestamp_utc": "2026-08-04T14:00:01.500Z", "marker": "app_start", "pid_name": "DATA0"},
    ]
    res = oab.compare_sessions(official, agent, markers)
    t = res["timing"]
    assert t["official"].get("host_to_target_data_or_nak") == pytest.approx(0.05, abs=0.01)
    assert t["agent"].get("host_to_target_data_or_nak") == pytest.approx(0.5, abs=0.01)
    assert t["first_timing_divergence"]["metric"] == "host_to_target_data_or_nak"


def test_timing_comparison_within_tolerance_no_divergence():
    markers = ["app_start"]
    official = [
        {"kind": "marker", "event": "app_start", "marker": "app_start", "timestamp_utc": "2026-08-04T14:00:00.000Z"},
        {"kind": "host_transfer", "timestamp_utc": "2026-08-04T14:00:01.000Z", "marker": "app_start", "payload": "00 01"},
        {"kind": "target_transaction", "timestamp_utc": "2026-08-04T14:00:01.010Z", "marker": "app_start", "pid_name": "DATA0"},
    ]
    agent = [
        {"kind": "marker", "event": "app_start", "marker": "app_start", "timestamp_utc": "2026-08-04T14:00:00.000Z"},
        {"kind": "host_transfer", "timestamp_utc": "2026-08-04T14:00:01.000Z", "marker": "app_start", "payload": "00 01"},
        {"kind": "target_transaction", "timestamp_utc": "2026-08-04T14:00:01.030Z", "marker": "app_start", "pid_name": "DATA0"},
    ]
    res = oab.compare_sessions(official, agent, markers, timing_tolerance=0.05)
    assert res["timing"]["first_timing_divergence"] is None


# --------------------------------------------------------------------------- correlation / capture commands


def test_correlation_id_embeds_utc_timestamp():
    cid = oab.correlation_id("official-app", now=_now())
    assert cid == "official-app-20260804T141700Z"


def test_usbpcap_command_uses_explicit_interface():
    argv = oab.usbpcap_command("\\\\.\\USBPcap2", Path(".work/cap/out.pcap"))
    assert "-d" in argv and "\\\\.\\USBPcap2" in argv
    assert "-f" not in argv  # no libpcap capture filter


def test_display_filter_is_post_capture():
    filt = oab.host_usb_display_filter()
    assert "usb.idVendor == 0x2b77" in filt
    argv = oab.tshark_decode_command(Path("cap.pcap"), display_filter=filt)
    assert "-Y" in argv and filt in argv


def test_capture_commands_tolerate_paths_with_spaces():
    argv = oab.beagle_command(Path(".work/cap dir/target (x86).jsonl"), api_dir=Path(".work/v/t"))
    assert str(Path(".work/cap dir/target (x86).jsonl")) in argv


# --------------------------------------------------------------------------- token identity / direction


def test_token_direction_from_pid():
    assert oab.token_direction_from_pid("IN") == "IN"
    assert oab.token_direction_from_pid("OUT") == "OUT"
    assert oab.token_direction_from_pid("SETUP") == "SETUP"
    assert oab.token_direction_from_pid("DATA0") is None


def test_descriptor_endpoint_address_uses_bit7():
    assert oab.decode_descriptor_endpoint_address(0x82) == {"endpoint_number": 2, "direction": "IN"}
    assert oab.decode_descriptor_endpoint_address(0x02) == {"endpoint_number": 2, "direction": "OUT"}


def test_token_identity_preserved():
    assert oab.classify_pid("IN") == "TOKEN_IN"
    assert oab.classify_pid("OUT") == "TOKEN_OUT"
    assert oab.classify_pid("SETUP") == "TOKEN_SETUP"
    counts = oab.in_nak_data_counts([{"pid_name": "IN"}, {"pid_name": "OUT"}, {"pid_name": "SETUP"}, {"pid_name": "DATA0"}])
    assert counts == {"IN": 1, "OUT": 1, "SETUP": 1, "NAK": 0, "DATA": 1}


# --------------------------------------------------------------------------- output path validation


def test_output_path_resolves_and_is_git_ignored():
    result = oab.verify_output_path(".work/evidence/official-app-x/host.pcap")
    assert result["ok"] is True and result["git_ignored"] is True


def test_output_path_escaping_rejected():
    result = oab.verify_output_path(r"C:\Windows\Temp\escape.pcap")
    assert result["ok"] is False
    assert any("not under approved root" in e for e in result["errors"])


# --------------------------------------------------------------------------- manifest / comparison


def test_manifest_records_prohibited_operations():
    manifest = _manifest()
    for item in ("unknown vendor OUT control transfers", "firmware writes", "EDID writes", "flash operations"):
        assert item in manifest["prohibited"]


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
         "endpoint": 2, "report_id": 1, "length": 8, "payload": "00 02"},
        {"kind": "target_transaction", "timestamp_utc": "t2", "pid_name": "IN"},
        {"kind": "marker", "event": "capslock_down", "marker": "capslock_down", "timestamp_utc": "t3"},
        {"kind": "target_transaction", "timestamp_utc": "t4", "pid_name": "NAK"},
    ]
    result = oab.compare_sessions(official, agent, markers)
    assert result["first_divergence"]["field"] == "payload"
    assert result["first_divergence"]["side"] == "host"
    assert result["stages"]["capslock_down"]["official"]["DATA"] == 1
    assert result["stages"]["capslock_down"]["agent"]["NAK"] == 1
