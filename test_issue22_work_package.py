from pathlib import Path


ROOT = Path(__file__).resolve().parent
KICKOFF = ROOT / "prompts" / "ISSUE22_KICKOFF.md"
PROMPT = ROOT / "prompts" / "ISSUE22_WORKSTATION_CAPTURE_DEPS.md"
RUNBOOK = ROOT / "docs" / "ISSUE22_OPERATOR_RUNBOOK.md"
COLLECTOR = ROOT / "scripts" / "collect_issue22_readiness.ps1"
DEPENDENCY_SCRIPT = ROOT / "scripts" / "prepare_issue22_dependencies.ps1"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing work-package file: {path}"
    return path.read_text(encoding="utf-8")


def test_issue22_work_package_files_exist() -> None:
    for path in (KICKOFF, PROMPT, RUNBOOK, COLLECTOR, DEPENDENCY_SCRIPT):
        assert path.is_file()


def test_issue22_kickoff_uses_fresh_completion_branch() -> None:
    text = _read(KICKOFF)
    for required in (
        "issue #27",
        "Windows Package Foundry #1/#2",
        "issue-22-readiness-completion",
        "claim preflight",
        "START",
        "CHECKPOINT",
        "HANDOFF",
        "PR #13",
    ):
        assert required in text
    assert "origin/issue-22-workstation-capture-deps" not in text


def test_prompt_preserves_claim_and_no_live_boundaries() -> None:
    text = _read(PROMPT)
    for required in (
        "Issue #27 owns dependency planning",
        "issue-22-readiness-completion",
        "START",
        "CHECKPOINT",
        "HANDOFF",
        "release the claim",
        "USBPcap interface-to-KVM2USB",
        "live_disabled: true",
        "no capture or target input",
        "PR #13",
    ):
        assert required in text


def test_runbook_delegates_dependency_acquisition() -> None:
    text = _read(RUNBOOK)
    for required in (
        "Issue #22 begins after issue #27",
        "does not acquire software",
        "docs/ISSUE27_OPERATOR_DEPENDENCY_RUNBOOK.md",
        "issue-22-readiness-completion",
        "USBPcapCMD.exe -d",
        "Do not start the experiment.",
        "PR #13 remains untouched",
    ):
        assert required in text

    assert "WiresharkFoundation.USBPcap" not in text
    # The runbook delegates acquisition to issue #27 and must not contain a direct
    # winget install command (e.g. the stale USBPcap package-ID invocation). Match
    # the command signature, not prose such as "exact WinGet installation of ...".
    assert "winget install --id" not in text.lower()
    assert "winget.exe install" not in text.lower()


def test_collector_is_fail_closed_and_no_live() -> None:
    text = _read(COLLECTOR)

    for required in (
        "live_disabled = $true",
        'status = "unproven"',
        "git -C $repoFull check-ignore --quiet",
        "OutputPath must remain inside the repository",
        "OutputPath is not Git-ignored",
        'ArgumentList @("-d")',
        "starts_capture = $false",
        "sends_target_input = $false",
        "installs_software = $false",
        "elevates_privileges = $false",
    ):
        assert required in text

    lowered = text.lower()
    for forbidden in (
        "winget install",
        "winget uninstall",
        "start-process -verb runas",
        "runas.exe",
        "--execute-live",
        "--allow-live",
        "--force-live",
    ):
        assert forbidden not in lowered


def test_collector_records_stable_device_identity_fields() -> None:
    text = _read(COLLECTOR)
    for required in (
        "DEVPKEY_Device_Parent",
        "DEVPKEY_Device_ContainerId",
        "DEVPKEY_Device_LocationPaths",
        "DEVPKEY_Device_DriverProvider",
        "DEVPKEY_Device_DriverVersion",
        "VID_2B77&PID_3661",
        "VID_1679&PID_2001",
        "VID_2109&PID_0817",
    ):
        assert required in text


def test_readiness_output_is_private_by_default() -> None:
    text = _read(COLLECTOR)
    assert ".work\\evidence\\issue-22-workstation-capture-deps\\readiness.json" in text
    assert "writes_only_ignored_readiness_json = $true" in text


def test_dependency_script_owns_install_and_vendor_staging_paths() -> None:
    text = _read(DEPENDENCY_SCRIPT)
    for required in (
        "WiresharkFoundation.Wireshark",
        "windows-package-foundry#1",
        "windows-package-foundry#2",
        ".work\\vendor\\totalphase",
        ".work\\vendor\\epiphan",
        "Invoke-Elevated",
    ):
        assert required in text
