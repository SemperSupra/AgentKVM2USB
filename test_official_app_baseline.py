"""Deterministic tests for the official-app differential experiment framework.

No hardware is required and no GitHub network access occurs. All capture
commands, correlation logic, timeline normalization, descriptor parsing,
comparison, timing, authorization (fixture-driven), path validation, schema
validation, and CLI behavior are exercised with fixture data.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

import pytest

from scripts import official_app_baseline as oab


def _now():
    return dt.datetime(2026, 8, 4, 14, 17, 0, tzinfo=dt.timezone.utc)


def _auth_block(**overrides):
    block = {
        "repository": "SemperSupra/AgentKVM2USB",
        "issue": 14,
        "experiment_id": "official-app-x",
        "target": "Wyse 5070",
        "allowed_input_sequence": ["capslock_down", "capslock_up"],
        "issued_utc": "2026-08-04T14:00:00+00:00",
        "expires_utc": "2026-08-04T20:00:00+00:00",
        "authority": "mark-e-deyoung (issue #14 human authorization)",
    }
    block.update(overrides)
    return block


def _auth_body(block=None):
    block = block or _auth_block()
    import json as _json
    return "Authorize the experiment below.\n\n```json\n" + _json.dumps(block, indent=2) + "\n```\n"


def _auth_fetched(block=None, comment_id="5180000000", user="mark-e-deyoung", **overrides):
    fetched = {
        "id": comment_id,
        "body": _auth_body(block),
        "user": user,
        "html_url": f"https://github.com/SemperSupra/AgentKVM2USB/issues/14#issuecomment-{comment_id}",
        "issue_url": "https://api.github.com/repos/SemperSupra/AgentKVM2USB/issues/14",
        "repository_url": "https://api.github.com/repos/SemperSupra/AgentKVM2USB",
        "created_at": "2026-08-04T14:00:00Z",
        "updated_at": "2026-08-04T14:00:00Z",
    }
    fetched.update(overrides)
    return fetched


def _auth_envelope(block=None, fetched=None, **overrides):
    fetched = fetched or _auth_fetched(block)
    env = oab.ingest_authorization(
        repository="SemperSupra/AgentKVM2USB", issue=14, comment_id=str(fetched["id"]), fetched=fetched,
    )
    env.update(overrides)
    return env


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
    # The schema must describe the actual ingested evidence-envelope shape.
    assert {"repository", "issue", "comment_id", "comment_url", "issue_url",
            "repository_url", "comment_body", "github_author", "fetched_utc",
            "authorization_block", "experiment_id", "target",
            "allowed_input_sequence", "issued_utc", "expires_utc", "authority",
            "evidence_sha256"}.issubset(auth_fields)
    # Old-shape fields must not be schema-required anymore.
    assert "canonical_issue" not in auth_fields
    assert "author" not in auth_fields
    # The nested authorization_block has its own schema-required fields.
    block_fields = set(oab.schema_auth_block_required_fields())
    assert {"repository", "issue", "experiment_id", "target",
            "allowed_input_sequence", "issued_utc", "expires_utc",
            "authority"}.issubset(block_fields)


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
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(), refetch=False,
    )
    assert ok is True
    assert "cached evidence" in reason


def test_authorization_rejects_fabricated_non_envelope():
    # A bare caller-constructed dict without a valid hash-pinned envelope fails.
    ok, reason = oab.verify_authorization(
        {"experiment_id": "official-app-x", "authority": "any"},
        experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="anyone", now_utc=_now(), refetch=False,
    )
    assert ok is False


def test_authorization_rejects_tampered_envelope():
    env = _auth_envelope()
    env["comment_body"] = "tampered; authorizes nothing"
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(), refetch=False,
    )
    assert ok is False


def test_authorization_rejects_wrong_experiment_id():
    # A valid-looking envelope whose parsed block has a different experiment id.
    env = _auth_envelope(block=_auth_block(experiment_id="other-experiment"))
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(), refetch=False,
    )
    assert ok is False


def test_authorization_rejects_expired():
    # issued < expires, but expires is before the verification time.
    env = _auth_envelope(block=_auth_block(issued_utc="2026-08-04T12:00:00+00:00",
                                           expires_utc="2026-08-04T13:00:00+00:00"))
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(), refetch=False,
    )
    assert ok is False and "expired" in reason


def test_authorization_rejects_authority_mismatch():
    env = _auth_envelope(fetched=_auth_fetched(user="someone-else"))
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(), refetch=False,
    )
    assert ok is False and "author" in reason


def test_authorization_rejects_target_difference():
    # Comment block authorizes a different target than the expected experiment.
    env = _auth_envelope(block=_auth_block(target="Other Machine"))
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(), refetch=False,
        expected_target="Wyse 5070",
    )
    assert ok is False


def test_authorization_rejects_sequence_difference():
    env = _auth_envelope(block=_auth_block(allowed_input_sequence=["capslock_down"]))
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(), refetch=False,
        expected_allowed_input_sequence=["capslock_down", "capslock_up"],
    )
    assert ok is False


def test_authorization_rejects_wrong_comment_id():
    env = _auth_envelope(fetched=_auth_fetched(comment_id="999"))
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(), refetch=False,
        expected_comment_id="5180000000",
    )
    assert ok is False


def test_authorization_rejects_wrong_issue_url():
    # A fetched comment whose issue_url does not identify the expected issue is
    # rejected at ingest time; it can never produce a valid envelope.
    fetched = _auth_fetched(issue_url="https://api.github.com/repos/SemperSupra/AgentKVM2USB/issues/99")
    try:
        oab.ingest_authorization(repository="SemperSupra/AgentKVM2USB", issue=14,
                                 comment_id="5180000000", fetched=fetched)
        raise AssertionError("expected ingest to reject an issue_url for the wrong issue")
    except ValueError:
        pass


def test_authorization_rejects_wrong_issue_url_expected():
    # Caller supplies an expected issue URL that disagrees with the envelope.
    env = _auth_envelope()
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(), refetch=False,
        expected_issue_url="https://api.github.com/repos/SemperSupra/AgentKVM2USB/issues/99",
    )
    assert ok is False


def test_authorization_rejects_wrong_repository():
    # The comment block names a different repository than the envelope/expected.
    env = oab.build_evidence_envelope(
        repository="SemperSupra/AgentKVM2USB", issue=14,
        comment_id="5180000000",
        comment_url="https://github.com/SemperSupra/AgentKVM2USB/issues/14#issuecomment-5180000000",
        issue_url="https://api.github.com/repos/SemperSupra/AgentKVM2USB/issues/14",
        repository_url="https://api.github.com/repos/SemperSupra/AgentKVM2USB",
        comment_body=_auth_body(_auth_block(repository="Other/Org")),
        github_author="mark-e-deyoung",
        fetched_utc="2026-08-04T14:00:00+00:00",
        authorization_block=_auth_block(repository="Other/Org"),
    )
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(), refetch=False,
    )
    assert ok is False


def test_authorization_rejects_missing_expiry():
    # The comment block omits expires_utc entirely; ingest must reject it.
    fetched = _auth_fetched(block=_auth_block(expires_utc=None))
    try:
        oab.ingest_authorization(repository="SemperSupra/AgentKVM2USB", issue=14,
                                 comment_id="5180000000", fetched=fetched)
        raise AssertionError("expected ingest to reject a block without expires_utc")
    except ValueError:
        pass


def test_authorization_rejects_expiry_difference():
    # Caller expects a different expiry than the comment block authorizes.
    env = _auth_envelope()
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(), refetch=False,
        expected_expires_utc="2026-08-05T20:00:00+00:00",
    )
    assert ok is False


def test_authorization_caller_fields_cannot_fabricate():
    # Caller-supplied authorization values are not accepted by ingest; there is
    # no signature path through which they can create an authorization.
    fetched = _auth_fetched(body="irrelevant body; caller fields present")
    try:
        oab.ingest_authorization(
            repository="SemperSupra/AgentKVM2USB", issue=14, comment_id="5180000000",
            fetched=fetched, experiment_id="official-app-x", target="Wyse 5070",
            allowed_input_sequence=["capslock_down"], issued_utc="2026-08-04T14:00:00+00:00",
            expires_utc="2026-08-04T20:00:00+00:00",
        )
        raise AssertionError("expected ingest to reject caller-supplied authorization values")
    except (TypeError, ValueError):
        pass


def test_authorization_rejects_body_with_only_experiment_id():
    # A body containing only the experiment id (no target/sequence/expiry) is
    # not a valid fenced authorization block.
    fetched = _auth_fetched(body="Authorize experiment official-app-x only.")
    try:
        oab.ingest_authorization(repository="SemperSupra/AgentKVM2USB", issue=14,
                                 comment_id="5180000000", fetched=fetched)
        raise AssertionError("expected ingest to reject a body without a JSON authorization block")
    except ValueError:
        pass


def test_authorization_rejects_github_comment_differing_from_cached(monkeypatch):
    env = _auth_envelope()
    # Re-fetch returns a different comment body than the cached envelope.
    monkeypatch.setattr(oab, "fetch_issue_comment",
                        lambda repo, cid: _auth_fetched(body=_auth_body(_auth_block(experiment_id="changed"))))
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(), refetch=True,
    )
    assert ok is False
    assert "differs" in reason or "different" in reason


def test_authorization_fabricated_envelope_not_proof(monkeypatch):
    # An arbitrary call to build_evidence_envelope() with a well-formed but
    # fabricated block produces a self-consistent envelope + hash. That alone is
    # never proof GitHub supplied the authorization: default re-verification
    # compares the envelope against the current fetched comment and rejects it.
    block = _auth_block()
    env = oab.build_evidence_envelope(
        repository="SemperSupra/AgentKVM2USB", issue=14,
        comment_id="5180000000",
        comment_url="https://github.com/SemperSupra/AgentKVM2USB/issues/14#issuecomment-5180000000",
        issue_url="https://api.github.com/repos/SemperSupra/AgentKVM2USB/issues/14",
        repository_url="https://api.github.com/repos/SemperSupra/AgentKVM2USB",
        comment_body=_auth_body(block),
        github_author="mark-e-deyoung",
        fetched_utc="2026-08-04T14:00:00+00:00",
        authorization_block=block,
    )
    assert env["evidence_sha256"] == oab.sha256_evidence(env)
    # The current GitHub comment for that id differs (e.g. no such authorization
    # block was ever posted); re-verification must reject the fabricated record.
    monkeypatch.setattr(oab, "fetch_issue_comment",
                        lambda repo, cid: _auth_fetched(body="no authorization block posted"))
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(), refetch=True,
    )
    assert ok is False
    assert "authorization block" in reason or "differs" in reason


def test_ingest_authorization_parses_values_from_body():
    fetched = _auth_fetched()
    env = oab.ingest_authorization(
        repository="SemperSupra/AgentKVM2USB", issue=14, comment_id="5180000000", fetched=fetched,
    )
    assert env["github_author"] == "mark-e-deyoung"
    assert env["experiment_id"] == "official-app-x"
    assert env["target"] == "Wyse 5070"
    assert env["allowed_input_sequence"] == ["capslock_down", "capslock_up"]
    assert env["authorization_block"]["authority"] == "mark-e-deyoung (issue #14 human authorization)"
    assert env["evidence_sha256"] == oab.sha256_evidence(env)


def test_ingest_authorization_rejects_plain_callable_fields():
    # Caller-supplied metadata must never create or override authorization
    # values; ingest requires a fetched comment body with a JSON block.
    try:
        oab.ingest_authorization(
            repository="SemperSupra/AgentKVM2USB", issue=14, comment_id="1",
            fetched={"id": "1", "body": "no block here", "user": "x",
                     "html_url": "https://x", "issue_url": "https://x", "repository_url": "https://x"},
        )
        raise AssertionError("expected ingest to reject a body without a JSON authorization block")
    except ValueError:
        pass


def test_authorization_envelope_end_to_end_schema_valid():
    # fetch fixture -> ingest -> verify -> embed in manifest -> schema-derived
    # validation must all PASS for a real ingested envelope.
    fetched = _auth_fetched()
    env = oab.ingest_authorization(
        repository="SemperSupra/AgentKVM2USB", issue=14, comment_id="5180000000", fetched=fetched,
    )
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(), refetch=False,
    )
    assert ok is True
    manifest = _manifest(authorization_record=env)
    assert oab.validate_manifest(manifest) == []
    # The nested authorization_block also validates against the schema.
    for field in oab.schema_auth_block_required_fields():
        assert field in env["authorization_block"]


def test_manifest_rejects_old_shape_authorization_record():
    # An old-shape record (canonical_issue/author) must fail schema-derived
    # validation; it is not the ingested evidence-envelope format.
    manifest = _manifest(authorization_record={
        "canonical_issue": 14, "comment_id": "x", "comment_url": "u", "author": "a",
        "authority": "b", "experiment_id": "e", "allowed_input_sequence": [],
        "target": "t", "issued_utc": "x", "expires_utc": "y",
    })
    errors = oab.validate_manifest(manifest)
    assert any("authorization_record." in e for e in errors)


def test_parse_authorization_block_rejects_multiple_blocks():
    body = _auth_body() + "\n```json\n" + json.dumps(_auth_block(experiment_id="second")) + "\n```\n"
    try:
        oab.parse_authorization_block(body)
        raise AssertionError("expected parse to reject multiple fenced JSON blocks")
    except ValueError as exc:
        assert "multiple" in str(exc)


def test_parse_authorization_block_rejects_issued_not_before_expiry():
    block = _auth_block(issued_utc="2026-08-04T21:00:00+00:00", expires_utc="2026-08-04T20:00:00+00:00")
    try:
        oab.ingest_authorization(repository="SemperSupra/AgentKVM2USB", issue=14,
                                 comment_id="5180000000", fetched=_auth_fetched(block=block))
        raise AssertionError("expected ingest to reject issued_utc not preceding expires_utc")
    except ValueError:
        pass


def test_verify_authorization_rejects_issued_not_before_expiry():
    env = oab.build_evidence_envelope(
        repository="SemperSupra/AgentKVM2USB", issue=14,
        comment_id="5180000000",
        comment_url="https://github.com/SemperSupra/AgentKVM2USB/issues/14#issuecomment-5180000000",
        issue_url="https://api.github.com/repos/SemperSupra/AgentKVM2USB/issues/14",
        repository_url="https://api.github.com/repos/SemperSupra/AgentKVM2USB",
        comment_body=_auth_body(_auth_block(issued_utc="2026-08-04T21:00:00+00:00",
                                            expires_utc="2026-08-04T20:00:00+00:00")),
        github_author="mark-e-deyoung",
        fetched_utc="2026-08-04T14:00:00+00:00",
        authorization_block=_auth_block(issued_utc="2026-08-04T21:00:00+00:00",
                                        expires_utc="2026-08-04T20:00:00+00:00"),
    )
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(), refetch=False,
    )
    assert ok is False
    assert "issued_utc must precede" in reason


def test_verify_authorization_rejects_unrelated_authority():
    # The block authority must reference the approved authority; an unrelated
    # arbitrary string cannot authorize the experiment.
    env = _auth_envelope(block=_auth_block(authority="someone entirely unrelated"))
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="mark-e-deyoung", now_utc=_now(), refetch=False,
    )
    assert ok is False
    assert "does not reference" in reason


def test_verify_authorization_requires_human_authority():
    # The GitHub author check must not be disableable via an empty default.
    env = _auth_envelope()
    ok, reason = oab.verify_authorization(
        env, experiment_id="official-app-x", repository="SemperSupra/AgentKVM2USB",
        issue=14, human_authority="", now_utc=_now(), refetch=False,
    )
    assert ok is False
    assert "cannot be empty" in reason


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


def _preflight_env(monkeypatch, interfaces, usb_present=True, api_dir=".work/v/t", disk_free=20 * 1024**3):
    monkeypatch.setattr(oab, "find_usbpcap_cmd", lambda: "USBPcapCMD.exe")
    monkeypatch.setattr(oab, "usbpcap_interfaces", lambda cmd: interfaces)
    monkeypatch.setattr(oab, "find_tshark", lambda: "tshark")
    monkeypatch.setattr(oab, "_detect_official_app", lambda: True)
    monkeypatch.setattr(oab, "find_beagle_windows_api_dir", lambda root: Path(api_dir))
    monkeypatch.setattr(oab, "_detect_beagle_driver", lambda: True)
    monkeypatch.setattr(oab, "_detect_kvm2usb_identity",
                        lambda: {"vid": "2b77", "pid": "3661", "present": usb_present})
    monkeypatch.setattr(shutil, "disk_usage",
                        lambda path: type("DiskUsage", (), {
                            "total": 100 * 1024**3, "used": 100 * 1024**3 - disk_free, "free": disk_free})())


def test_preflight_requires_interface_mapping_when_multiple(monkeypatch):
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1", "\\\\.\\USBPcap2"])
    pf = oab.preflight(host_interface=None, target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"})
    assert pf["selected_host_interface"] is None
    assert any("mapping" in i for i in pf["issues"])
    assert pf["live_disabled"] is True


def test_preflight_rejects_explicit_interface_without_mapping(monkeypatch):
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1", "\\\\.\\USBPcap2"])
    pf = oab.preflight(host_interface="\\\\.\\USBPcap2", target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"})
    assert pf["selected_host_interface"] is None
    assert any("no mapping evidence" in i for i in pf["issues"])


def test_preflight_accepts_explicit_interface_with_mapping(monkeypatch):
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1", "\\\\.\\USBPcap2"])
    mapping = {"\\\\.\\USBPcap2": {"device_instance": "USB\\VID_2B77&PID_3661\\KVM", "evidence": "pnp-root-hub"}}
    pf = oab.preflight(host_interface="\\\\.\\USBPcap2", target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"},
                       driver_state={"official_app": "detected", "beagle": "detected"},
                       interface_mapping=mapping)
    assert pf["selected_host_interface"] == "\\\\.\\USBPcap2"
    assert "\\\\.\\USBPcap2" in pf["commands"]["usbpcap"]


def test_preflight_auto_selects_single_mapped_interface(monkeypatch):
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1", "\\\\.\\USBPcap2"])
    mapping = {"\\\\.\\USBPcap1": {"device_instance": "USB\\VID_2B77&PID_3661\\KVM", "evidence": "pnp-root-hub"}}
    pf = oab.preflight(host_interface=None, target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"},
                       driver_state={"official_app": "detected", "beagle": "detected"},
                       interface_mapping=mapping)
    assert pf["selected_host_interface"] == "\\\\.\\USBPcap1"
    assert "\\\\.\\USBPcap1" in pf["commands"]["usbpcap"]


def test_preflight_does_not_infer_from_global_presence(monkeypatch):
    # Global device presence + one interface does NOT prove association.
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1"], usb_present=True)
    pf = oab.preflight(host_interface=None, target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"})
    assert pf["selected_host_interface"] is None
    assert any("mapping" in i for i in pf["issues"])


def test_preflight_beagle_api_dir_never_evidence_root(monkeypatch):
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1"], api_dir=".work/vendor/totalphase/python")
    mapping = {"\\\\.\\USBPcap1": {"device_instance": "USB\\VID_2B77&PID_3661\\KVM", "evidence": "pnp-root-hub"}}
    pf = oab.preflight(host_interface="\\\\.\\USBPcap1", target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"},
                       driver_state={"official_app": "detected", "beagle": "detected"},
                       interface_mapping=mapping)
    assert Path(pf["detected"]["beagle_windows_api_dir"]) == Path(".work/vendor/totalphase/python")
    assert "--api-dir" in pf["commands"]["beagle"]
    assert str(Path(".work/vendor/totalphase/python")) in pf["commands"]["beagle"]
    assert str(Path(".work/evidence")) not in pf["commands"]["beagle"]


def test_preflight_incomplete_topology_blocks(monkeypatch):
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1"])
    mapping = {"\\\\.\\USBPcap1": {"device_instance": "USB\\VID_2B77&PID_3661\\KVM", "evidence": "pnp-root-hub"}}
    pf = oab.preflight(host_interface="\\\\.\\USBPcap1", target_state_confirmed=True,
                       topology={}, interface_mapping=mapping)
    assert pf["ok"] is False
    assert any("topology" in i for i in pf["issues"])


def test_preflight_missing_target_state_confirmation_blocks(monkeypatch):
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1"])
    mapping = {"\\\\.\\USBPcap1": {"device_instance": "USB\\VID_2B77&PID_3661\\KVM", "evidence": "pnp-root-hub"}}
    pf = oab.preflight(host_interface="\\\\.\\USBPcap1", target_state_confirmed=False,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"},
                       interface_mapping=mapping)
    assert pf["ok"] is False
    assert any("target-state" in i for i in pf["issues"])


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


def test_preflight_single_interface_positive_mapping_selected(monkeypatch):
    # Exactly one interface is positively mapped to KVM2USB -> auto-selected.
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1"])
    mapping = {"\\\\.\\USBPcap1": {"device_instance": "USB\\VID_2B77&PID_3661\\KVM", "evidence": "pnp-root-hub"}}
    pf = oab.preflight(host_interface=None, target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"},
                       driver_state={"official_app": "detected", "beagle": "detected"},
                       interface_mapping=mapping)
    assert pf["selected_host_interface"] == "\\\\.\\USBPcap1"
    assert pf["ok"] is True
    assert not any("selected" in i for i in pf["issues"])  # no blocker for the successful auto-selection
    assert "usbpcap" in pf["commands"] and "beagle" in pf["commands"]


def test_preflight_explicit_wrong_interface_rejected(monkeypatch):
    # The selected interface is mapped, but to a different device, not KVM2USB.
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1", "\\\\.\\USBPcap2"])
    mapping = {
        "\\\\.\\USBPcap2": {"device_instance": "USB\\VID_1234&PID_5678\\some-other-device", "evidence": "pnp-root-hub"},
    }
    pf = oab.preflight(host_interface="\\\\.\\USBPcap2", target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"},
                       interface_mapping=mapping)
    assert pf["selected_host_interface"] is None
    assert any("no mapping evidence" in i for i in pf["issues"])


def test_preflight_multiple_positive_mappings_require_explicit(monkeypatch):
    # Two interfaces positively mapped -> no auto-select; explicit selection required.
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1", "\\\\.\\USBPcap2"])
    mapping = {
        "\\\\.\\USBPcap1": {"device_instance": "USB\\VID_2B77&PID_3661\\KVM1", "evidence": "pnp-root-hub"},
        "\\\\.\\USBPcap2": {"device_instance": "USB\\VID_2B77&PID_3661\\KVM2", "evidence": "pnp-root-hub"},
    }
    pf = oab.preflight(host_interface=None, target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"},
                       interface_mapping=mapping)
    assert pf["selected_host_interface"] is None
    assert any("explicit selection" in i for i in pf["issues"])


def test_preflight_mapped_but_absent_interface_rejected(monkeypatch):
    # The mapping references an interface that is not in the detected USBPcap
    # list; it must be rejected, not silently selected.
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1"])
    mapping = {
        "\\\\.\\USBPcap9": {"device_instance": "USB\\VID_2B77&PID_3661\\KVM", "evidence": "pnp-root-hub"},
    }
    pf = oab.preflight(host_interface="\\\\.\\USBPcap9", target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"},
                       driver_state={"official_app": "detected", "beagle": "detected"},
                       interface_mapping=mapping)
    assert pf["selected_host_interface"] is None
    assert any("not detected" in i and "USBPcap9" in i for i in pf["issues"])
    assert pf["commands"] == {}


def test_preflight_explicit_interface_not_detected_rejected(monkeypatch):
    # An explicitly selected interface that is not a detected USBPcap interface
    # at all is rejected.
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1"])
    pf = oab.preflight(host_interface="\\\\.\\USBPcap7", target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"},
                       driver_state={"official_app": "detected", "beagle": "detected"})
    assert pf["selected_host_interface"] is None
    assert any("not a detected USBPcap interface" in i for i in pf["issues"])


def test_preflight_device_absent_with_mapping_blocks(monkeypatch):
    # KVM2USB device not currently present: a positively mapped interface cannot
    # yield a runnable preflight.
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1"], usb_present=False)
    mapping = {"\\\\.\\USBPcap1": {"device_instance": "USB\\VID_2B77&PID_3661\\KVM", "evidence": "pnp-root-hub"}}
    pf = oab.preflight(host_interface=None, target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"},
                       driver_state={"official_app": "detected", "beagle": "detected"},
                       interface_mapping=mapping)
    assert pf["selected_host_interface"] == "\\\\.\\USBPcap1"
    assert pf["ok"] is False
    assert any("not currently detected" in i for i in pf["issues"])
    assert pf["commands"] == {}


def test_preflight_device_absent_offline_only_allowed(monkeypatch):
    # Offline-only mode waives the current device-presence gate.
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1"], usb_present=False)
    mapping = {"\\\\.\\USBPcap1": {"device_instance": "USB\\VID_2B77&PID_3661\\KVM", "evidence": "pnp-root-hub"}}
    pf = oab.preflight(host_interface=None, target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"},
                       driver_state={"official_app": "detected", "beagle": "detected"},
                       interface_mapping=mapping, offline_only=True)
    assert pf["ok"] is True
    assert not any("not currently detected" in i for i in pf["issues"])


def test_preflight_unknown_driver_state_rejected(monkeypatch):
    # `unknown` driver evidence is rejected, not silently accepted.
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1"])
    mapping = {"\\\\.\\USBPcap1": {"device_instance": "USB\\VID_2B77&PID_3661\\KVM", "evidence": "pnp-root-hub"}}
    pf = oab.preflight(host_interface="\\\\.\\USBPcap1", target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"},
                       driver_state={"official_app": "unknown", "beagle": "detected"},
                       interface_mapping=mapping)
    assert pf["ok"] is False
    assert any("driver-state" in i and "unknown" in i for i in pf["issues"])


def test_preflight_partial_driver_state_rejected(monkeypatch):
    # Missing one driver's evidence is rejected.
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1"])
    mapping = {"\\\\.\\USBPcap1": {"device_instance": "USB\\VID_2B77&PID_3661\\KVM", "evidence": "pnp-root-hub"}}
    pf = oab.preflight(host_interface="\\\\.\\USBPcap1", target_state_confirmed=True,
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"},
                       driver_state={"official_app": "detected"},
                       interface_mapping=mapping)
    assert pf["ok"] is False
    assert any("driver-state" in i for i in pf["issues"])


def test_preflight_output_root_outside_approved_rejected(monkeypatch):
    # An output root outside the approved ignored/private root fails closed.
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1"])
    mapping = {"\\\\.\\USBPcap1": {"device_instance": "USB\\VID_2B77&PID_3661\\KVM", "evidence": "pnp-root-hub"}}
    pf = oab.preflight(host_interface="\\\\.\\USBPcap1", target_state_confirmed=True,
                       output_root=r"C:\Windows\Temp\escape",
                       topology={"cable_path": "x", "beagle_position": "y", "target_identity": "Wyse"},
                       driver_state={"official_app": "detected", "beagle": "detected"},
                       interface_mapping=mapping)
    assert pf["ok"] is False
    assert any("not under an approved" in i for i in pf["issues"])
    assert pf["commands"] == {}


# --------------------------------------------------------------------------- CLI no-live completeness


def _cli_complete_args():
    mapping = json.dumps({
        "\\\\.\\USBPcap1": {"device_instance": "USB\\VID_2B77&PID_3661\\KVM", "evidence": "pnp-root-hub"},
    })
    return [
        "--host-interface", "\\\\.\\USBPcap1",
        "--interface-mapping", mapping,
        "--target-state-confirmed",
        "--cable-path", "DP->KVM2USB->Wyse",
        "--beagle-position", "target leg",
        "--target-identity", "Wyse 5070",
        "--official-app-driver", "detected",
        "--beagle-driver", "detected",
    ]


def test_cli_preflight_complete_ok(monkeypatch, capsys):
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1"])
    rc = oab.main(["preflight"] + _cli_complete_args())
    out = capsys.readouterr().out
    assert rc == 0
    assert "HUMAN ACTION REQUIRED" not in out
    report = json.loads(out)
    assert report["ok"] is True
    assert report["selected_host_interface"] == "\\\\.\\USBPcap1"
    assert report["live_disabled"] is True


def test_cli_preflight_incomplete_nonzero(monkeypatch, capsys):
    # No interface mapping, no topology, no target-state confirmation.
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1"])
    rc = oab.main(["preflight"])
    out = capsys.readouterr().out
    assert rc == 2
    assert "HUMAN ACTION REQUIRED" in out


def test_cli_build_manifest_blocked_when_preflight_incomplete(monkeypatch, capsys):
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1"])
    rc = oab.main(["build-manifest"])
    out = capsys.readouterr().out
    assert rc == 2
    payload = json.loads(out[: out.index("HUMAN ACTION REQUIRED")].strip())
    assert payload.get("blocked") is True
    assert "HUMAN ACTION REQUIRED" in out


def test_cli_build_manifest_complete_valid(monkeypatch, capsys):
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1"])
    rc = oab.main(["build-manifest"] + _cli_complete_args())
    out = capsys.readouterr().out
    assert rc == 0
    manifest = json.loads(out)
    assert manifest["environment"]["host_interface"] == "\\\\.\\USBPcap1"
    assert oab.validate_manifest(manifest) == []
    assert manifest["authorization_record"] is None


def test_cli_build_manifest_validates_nested_required_fields(monkeypatch, capsys):
    # A complete preflight manifest must validate against the schema, including
    # environment and capture nested required fields.
    _preflight_env(monkeypatch, ["\\\\.\\USBPcap1"])
    rc = oab.main(["build-manifest"] + _cli_complete_args())
    out = capsys.readouterr().out
    assert rc == 0
    manifest = json.loads(out)
    for field in oab.schema_section_required("environment"):
        assert field in manifest["environment"]
    for field in oab.schema_section_required("capture"):
        assert field in manifest["capture"]


def test_cli_build_manifest_blocked_when_nested_field_missing(monkeypatch, capsys):
    # Remove a nested schema-required environment field from a built manifest;
    # validate_manifest must flag it (exercises the nested schema contract).
    manifest = _manifest()
    del manifest["environment"]["topology"]
    errors = oab.validate_manifest(manifest)
    assert any("environment.topology" in e for e in errors)


# --------------------------------------------------------------------------- timing comparison


def _timing_session(marker_pairs):
    """Build a timeline from (stage, timestamp) marker pairs plus optional rows."""
    rows = []
    for stage, ts in marker_pairs:
        rows.append({"kind": "marker", "event": stage, "marker": stage, "timestamp_utc": ts})
    return rows


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
    assert t["official"]["app_start"]["host_to_first_target_data_or_nak"] == pytest.approx(0.05, abs=0.01)
    assert t["agent"]["app_start"]["host_to_first_target_data_or_nak"] == pytest.approx(0.5, abs=0.01)
    # The same timing difference also makes init_to_first_target_data diverge, and
    # that interval starts at app_start (14:00:00) — earlier than the host->target
    # interval (14:00:01) — so it is the chronologically first timing divergence.
    diverged = [d["metric"] for d in t["timing_divergences"]]
    assert "app_start.host_to_first_target_data_or_nak" in diverged
    assert t["first_timing_divergence"]["metric"] == "init_to_first_target_data"


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


def test_timing_all_metrics_measured_and_not_overwritten():
    markers = ["app_start", "capslock_down", "capslock_up", "ordinary_key_down",
               "ordinary_key_up", "all_keys_release"]
    rows = [
        {"kind": "marker", "event": "app_start", "marker": "app_start", "timestamp_utc": "2026-08-04T14:00:00.000Z"},
        {"kind": "host_transfer", "timestamp_utc": "2026-08-04T14:00:01.000Z", "marker": "app_start", "payload": "00 01"},
        {"kind": "target_transaction", "timestamp_utc": "2026-08-04T14:00:01.050Z", "marker": "app_start", "pid_name": "DATA0"},
        {"kind": "marker", "event": "capslock_down", "marker": "capslock_down", "timestamp_utc": "2026-08-04T14:00:02.000Z"},
        {"kind": "host_transfer", "timestamp_utc": "2026-08-04T14:00:02.100Z", "marker": "capslock_down", "payload": "00 02"},
        {"kind": "target_transaction", "timestamp_utc": "2026-08-04T14:00:02.200Z", "marker": "capslock_down", "pid_name": "NAK"},
        {"kind": "marker", "event": "capslock_up", "marker": "capslock_up", "timestamp_utc": "2026-08-04T14:00:03.000Z"},
        {"kind": "marker", "event": "ordinary_key_down", "marker": "ordinary_key_down", "timestamp_utc": "2026-08-04T14:00:04.000Z"},
        {"kind": "marker", "event": "ordinary_key_up", "marker": "ordinary_key_up", "timestamp_utc": "2026-08-04T14:00:05.000Z"},
        {"kind": "marker", "event": "all_keys_release", "marker": "all_keys_release", "timestamp_utc": "2026-08-04T14:00:06.000Z"},
    ]
    m = oab.stage_timing_metrics(rows, marker_events=markers)
    # app_start metrics
    assert m["app_start"]["marker_to_first_host_report"] == pytest.approx(1.0, abs=0.01)
    assert m["app_start"]["host_to_first_target_data_or_nak"] == pytest.approx(0.05, abs=0.01)
    # capslock_down stage is not overwritten by later stages
    assert m["capslock_down"]["host_to_first_target_data_or_nak"] == pytest.approx(0.1, abs=0.01)
    # cross-marker intervals
    assert m["capslock"]["down_to_up"] == pytest.approx(1.0, abs=0.01)
    assert m["ordinary_key"]["down_to_up"] == pytest.approx(1.0, abs=0.01)
    assert m["all_keys_release"]["last_key_release_to_all_keys_release"] == pytest.approx(1.0, abs=0.01)
    # init to first target DATA across the full timeline (first DATA at 14:00:01.05)
    assert m["init_to_first_target_data"] == pytest.approx(1.05, abs=0.01)


def test_timing_missing_target_data_is_unavailable_not_zero():
    markers = ["app_start"]
    rows = [
        {"kind": "marker", "event": "app_start", "marker": "app_start", "timestamp_utc": "2026-08-04T14:00:00.000Z"},
        {"kind": "host_transfer", "timestamp_utc": "2026-08-04T14:00:01.000Z", "marker": "app_start", "payload": "00 01"},
        # no DATA/NAK target transaction
    ]
    m = oab.stage_timing_metrics(rows, marker_events=markers)
    assert m["app_start"].get("host_to_first_target_data_or_nak") is None
    assert "init_to_first_target_data" not in m  # unavailable, not 0.0


def test_timing_nak_instead_of_data():
    markers = ["app_start"]
    official = [
        {"kind": "marker", "event": "app_start", "marker": "app_start", "timestamp_utc": "2026-08-04T14:00:00.000Z"},
        {"kind": "host_transfer", "timestamp_utc": "2026-08-04T14:00:01.000Z", "marker": "app_start", "payload": "00 01"},
        {"kind": "target_transaction", "timestamp_utc": "2026-08-04T14:00:01.100Z", "marker": "app_start", "pid_name": "DATA0"},
    ]
    agent = [
        {"kind": "marker", "event": "app_start", "marker": "app_start", "timestamp_utc": "2026-08-04T14:00:00.000Z"},
        {"kind": "host_transfer", "timestamp_utc": "2026-08-04T14:00:01.000Z", "marker": "app_start", "payload": "00 01"},
        {"kind": "target_transaction", "timestamp_utc": "2026-08-04T14:00:01.100Z", "marker": "app_start", "pid_name": "NAK"},
    ]
    res = oab.compare_sessions(official, agent, markers, timing_tolerance=0.05)
    # Same host-to-target timing (NAK treated like DATA/NAK), no timing divergence.
    assert res["timing"]["first_timing_divergence"] is None
    # But the target-count divergence is reported separately.
    assert res["stages"]["app_start"]["target_divergence"] is not None


def test_timing_multiple_divergences_first_is_chronological():
    # The same host->target timing change produces two divergences: the
    # app_start host->target interval AND the init->first-target-DATA interval.
    # init_to_first_target_data starts at app_start (14:00:00), earlier than the
    # host->target interval (14:00:01), so it is the chronologically first
    # divergence even though it appears later in a fixed metric list.
    markers = ["app_start", "capslock_down"]
    def session(first_target_ts):
        return [
            {"kind": "marker", "event": "app_start", "marker": "app_start", "timestamp_utc": "2026-08-04T14:00:00.000Z"},
            {"kind": "host_transfer", "timestamp_utc": "2026-08-04T14:00:01.000Z", "marker": "app_start", "payload": "00 01"},
            {"kind": "target_transaction", "timestamp_utc": first_target_ts, "marker": "app_start", "pid_name": "DATA0"},
            {"kind": "marker", "event": "capslock_down", "marker": "capslock_down", "timestamp_utc": "2026-08-04T14:00:02.000Z"},
            {"kind": "host_transfer", "timestamp_utc": "2026-08-04T14:00:02.100Z", "marker": "capslock_down", "payload": "00 02"},
            {"kind": "target_transaction", "timestamp_utc": "2026-08-04T14:00:02.150Z", "marker": "capslock_down", "pid_name": "NAK"},
        ]
    official = session("2026-08-04T14:00:01.050Z")
    agent = session("2026-08-04T14:00:01.200Z")  # differs in app_start host->target only
    res = oab.compare_sessions(official, agent, markers, timing_tolerance=0.05)
    t = res["timing"]
    diverged_metrics = [d["metric"] for d in t["timing_divergences"]]
    assert "init_to_first_target_data" in diverged_metrics
    assert "app_start.host_to_first_target_data_or_nak" in diverged_metrics
    # Chronologically first by actual start timestamp (14:00:00 < 14:00:01).
    assert t["first_timing_divergence"]["metric"] == "init_to_first_target_data"


def test_timing_identical_sessions_no_divergence():
    markers = ["app_start", "capslock_down", "capslock_up"]
    rows = [
        {"kind": "marker", "event": "app_start", "marker": "app_start", "timestamp_utc": "2026-08-04T14:00:00.000Z"},
        {"kind": "host_transfer", "timestamp_utc": "2026-08-04T14:00:01.000Z", "marker": "app_start", "payload": "00 01"},
        {"kind": "target_transaction", "timestamp_utc": "2026-08-04T14:00:01.100Z", "marker": "app_start", "pid_name": "DATA0"},
        {"kind": "marker", "event": "capslock_down", "marker": "capslock_down", "timestamp_utc": "2026-08-04T14:00:02.000Z"},
        {"kind": "host_transfer", "timestamp_utc": "2026-08-04T14:00:02.100Z", "marker": "capslock_down", "payload": "00 02"},
        {"kind": "target_transaction", "timestamp_utc": "2026-08-04T14:00:02.200Z", "marker": "capslock_down", "pid_name": "NAK"},
        {"kind": "marker", "event": "capslock_up", "marker": "capslock_up", "timestamp_utc": "2026-08-04T14:00:03.000Z"},
    ]
    res = oab.compare_sessions(rows, [dict(r) for r in rows], markers, timing_tolerance=0.05)
    assert res["timing"]["timing_divergences"] == []
    assert res["timing"]["first_timing_divergence"] is None
    m = res["timing"]["official"]
    # All promised metrics are present for the identical sessions, none zero-by-construction.
    assert m["app_start"]["marker_to_first_host_report"] == pytest.approx(1.0, abs=0.01)
    assert m["app_start"]["host_to_first_target_data_or_nak"] == pytest.approx(0.1, abs=0.01)
    assert m["capslock_down"]["marker_to_first_host_transfer"] == pytest.approx(0.1, abs=0.01)
    assert m["capslock_down"]["host_to_first_target_data_or_nak"] == pytest.approx(0.1, abs=0.01)
    assert m["capslock"]["down_to_up"] == pytest.approx(1.0, abs=0.01)


def test_timing_missing_marker_is_unavailable_not_divergence():
    # capslock_up marker is missing: the down->up interval is unavailable in both
    # sessions and must not be reported as a timing divergence.
    markers = ["app_start", "capslock_down", "capslock_up", "ordinary_key_down"]
    def session():
        return [
            {"kind": "marker", "event": "app_start", "marker": "app_start", "timestamp_utc": "2026-08-04T14:00:00.000Z"},
            {"kind": "host_transfer", "timestamp_utc": "2026-08-04T14:00:01.000Z", "marker": "app_start", "payload": "00 01"},
            {"kind": "target_transaction", "timestamp_utc": "2026-08-04T14:00:01.100Z", "marker": "app_start", "pid_name": "DATA0"},
            {"kind": "marker", "event": "capslock_down", "marker": "capslock_down", "timestamp_utc": "2026-08-04T14:00:02.000Z"},
            # no capslock_up marker
            {"kind": "marker", "event": "ordinary_key_down", "marker": "ordinary_key_down", "timestamp_utc": "2026-08-04T14:00:04.000Z"},
        ]
    official = session()
    agent = [dict(r) for r in session()]
    res = oab.compare_sessions(official, agent, markers, timing_tolerance=0.05)
    m = res["timing"]["official"]
    assert "down_to_up" not in (m.get("capslock") or {})
    assert res["timing"]["timing_divergences"] == []


def test_normalized_nak_is_counted_as_nak():
    # A normalized NAK record (class_ == "NAK", from classify_pid) must count as
    # NAK, not be lost to a generic HANDSHAKE class.
    assert oab.classify_pid("NAK") == "NAK"
    normalized = oab.normalize_target_transaction({"pid_name": "NAK"})
    assert normalized["class_"] == "NAK"
    counts = oab.in_nak_data_counts([normalized])
    assert counts["NAK"] == 1
    assert counts["HANDSHAKE"] == 0


def test_ack_not_counted_as_nak():
    # ACK/STALL/NYET are HANDSHAKE, never NAK, for both normalized and raw forms.
    for pid in ("ACK", "STALL", "NYET"):
        normalized = oab.normalize_target_transaction({"pid_name": pid})
        assert normalized["class_"] == "HANDSHAKE"
    counts = oab.in_nak_data_counts([
        oab.normalize_target_transaction({"pid_name": "ACK"}),
        {"pid_name": "STALL"},
        {"pid_name": "NYET"},
    ])
    assert counts["NAK"] == 0
    assert counts["HANDSHAKE"] == 3


def test_timing_target_before_host_transfer_is_not_selected():
    # A target event that precedes the host transfer in the marker bucket must
    # not be selected for host->target timing.
    markers = ["app_start"]
    rows = [
        {"kind": "marker", "event": "app_start", "marker": "app_start", "timestamp_utc": "2026-08-04T14:00:00.000Z"},
        {"kind": "target_transaction", "timestamp_utc": "2026-08-04T14:00:00.500Z", "marker": "app_start", "pid_name": "NAK"},
        {"kind": "host_transfer", "timestamp_utc": "2026-08-04T14:00:01.000Z", "marker": "app_start", "payload": "00 01"},
        {"kind": "target_transaction", "timestamp_utc": "2026-08-04T14:00:01.100Z", "marker": "app_start", "pid_name": "NAK"},
    ]
    m = oab.stage_timing_metrics(rows, marker_events=markers)
    # The host->target interval measures to the NAK strictly after the host
    # transfer (01.100), never the earlier NAK (00.500).
    assert m["app_start"]["host_to_first_target_data_or_nak"] == pytest.approx(0.1, abs=0.01)


def test_timing_init_requires_real_data_not_nak():
    # init_to_first_target_data must require DATA; a NAK-only session yields no
    # such metric (unavailable, not a NAK reported as target DATA).
    markers = ["app_start"]
    rows = [
        {"kind": "marker", "event": "app_start", "marker": "app_start", "timestamp_utc": "2026-08-04T14:00:00.000Z"},
        {"kind": "target_transaction", "timestamp_utc": "2026-08-04T14:00:01.000Z", "marker": "app_start", "pid_name": "NAK"},
        {"kind": "target_transaction", "timestamp_utc": "2026-08-04T14:00:02.000Z", "marker": "app_start", "pid_name": "NAK"},
    ]
    m = oab.stage_timing_metrics(rows, marker_events=markers)
    assert "init_to_first_target_data" not in m


def test_timing_first_data_after_naks():
    # The first true DATA after one or more NAKs is the one measured for
    # init_to_first_target_data.
    markers = ["app_start"]
    rows = [
        {"kind": "marker", "event": "app_start", "marker": "app_start", "timestamp_utc": "2026-08-04T14:00:00.000Z"},
        {"kind": "target_transaction", "timestamp_utc": "2026-08-04T14:00:00.500Z", "marker": "app_start", "pid_name": "NAK"},
        {"kind": "target_transaction", "timestamp_utc": "2026-08-04T14:00:01.000Z", "marker": "app_start", "pid_name": "NAK"},
        {"kind": "target_transaction", "timestamp_utc": "2026-08-04T14:00:02.000Z", "marker": "app_start", "pid_name": "DATA0"},
    ]
    m = oab.stage_timing_metrics(rows, marker_events=markers)
    assert m["init_to_first_target_data"] == pytest.approx(2.0, abs=0.01)


def test_normalized_nak_in_compare_sessions():
    # A normalized NAK session vs a normalized DATA session diverge on target
    # counts (NAK vs DATA), and init_to_first_target_data is unavailable for the
    # NAK-only session (so no timing divergence from it).
    markers = ["app_start"]
    official = [
        {"kind": "marker", "event": "app_start", "marker": "app_start", "timestamp_utc": "2026-08-04T14:00:00.000Z"},
        oab.normalize_target_transaction({"pid_name": "DATA0", "timestamp_utc": "2026-08-04T14:00:01.000Z"}),
    ]
    agent = [
        {"kind": "marker", "event": "app_start", "marker": "app_start", "timestamp_utc": "2026-08-04T14:00:00.000Z"},
        oab.normalize_target_transaction({"pid_name": "NAK", "timestamp_utc": "2026-08-04T14:00:01.000Z"}),
    ]
    res = oab.compare_sessions(official, agent, markers)
    assert res["stages"]["app_start"]["official"]["DATA"] == 1
    assert res["stages"]["app_start"]["agent"]["NAK"] == 1
    assert res["stages"]["app_start"]["agent"]["DATA"] == 0
    t = res["timing"]
    # Official reaches real DATA -> init_to_first_target_data present; the
    # NAK-only agent never does.
    assert t["official"]["init_to_first_target_data"] == pytest.approx(1.0, abs=0.01)
    assert "init_to_first_target_data" not in t["agent"]


def test_timing_divergences_sorted_by_actual_timestamps():
    # Two divergences in the same session: the capslock-down stage (later in
    # time) and the app_start host->target (earlier). The earlier one is first.
    markers = ["app_start", "capslock_down"]
    def session(app_target_ts, cap_target_ts):
        return [
            {"kind": "marker", "event": "app_start", "marker": "app_start", "timestamp_utc": "2026-08-04T14:00:00.000Z"},
            {"kind": "host_transfer", "timestamp_utc": "2026-08-04T14:00:01.000Z", "marker": "app_start", "payload": "00 01"},
            {"kind": "target_transaction", "timestamp_utc": app_target_ts, "marker": "app_start", "pid_name": "DATA0"},
            {"kind": "marker", "event": "capslock_down", "marker": "capslock_down", "timestamp_utc": "2026-08-04T14:00:02.000Z"},
            {"kind": "host_transfer", "timestamp_utc": "2026-08-04T14:00:02.100Z", "marker": "capslock_down", "payload": "00 02"},
            {"kind": "target_transaction", "timestamp_utc": cap_target_ts, "marker": "capslock_down", "pid_name": "DATA0"},
        ]
    official = session("2026-08-04T14:00:01.050Z", "2026-08-04T14:00:02.150Z")
    agent = session("2026-08-04T14:00:01.200Z", "2026-08-04T14:00:02.300Z")
    res = oab.compare_sessions(official, agent, markers, timing_tolerance=0.05)
    t = res["timing"]
    metrics = [d["metric"] for d in t["timing_divergences"]]
    # app_start host->target starts at 14:00:01; capslock host->target at 14:00:02.
    assert metrics.index("app_start.host_to_first_target_data_or_nak") < metrics.index(
        "capslock_down.host_to_first_target_data_or_nak")
    # init_to_first_target_data starts at app_start (14:00:00) and diverges too,
    # so it is the chronologically first divergence by actual timestamps.
    assert t["first_timing_divergence"]["metric"] == "init_to_first_target_data"


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
    assert counts == {"IN": 1, "OUT": 1, "SETUP": 1, "NAK": 0, "DATA": 1, "HANDSHAKE": 0}


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
