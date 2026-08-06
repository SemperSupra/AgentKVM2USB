from pathlib import Path


ROOT = Path(__file__).resolve().parent
KICKOFF = ROOT / "prompts" / "ISSUE22_KICKOFF.md"
PROMPT = ROOT / "prompts" / "ISSUE22_WORKSTATION_CAPTURE_DEPS.md"
RUNBOOK = ROOT / "docs" / "ISSUE22_OPERATOR_RUNBOOK.md"
COLLECTOR = ROOT / "scripts" / "collect_issue22_readiness.ps1"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing work-package file: {path}"
    return path.read_text(encoding="utf-8")


def test_issue22_work_package_files_exist() -> None:
    for path in (KICKOFF, PROMPT, RUNBOOK, COLLECTOR):
        assert path.is_file()


def test_minimal_kickoff_tracks_remote_branch_safely() -> None:
    text = _read(KICKOFF)
    for required in (
        "origin/issue-22-workstation-capture-deps",
        "git branch --track issue-22-workstation-capture-deps",
        "git worktree add",
        "Run claim preflight",
        "Do not install, elevate, capture, send input, recable",
        "PR #26",
    ):
        assert required in text


def test_prompt_preserves_claim_and_safety_boundaries() -> None:
    text = _read(PROMPT)
    for required in (
        "issue-22-workstation-capture-deps",
        "recovery/agentkvm2usb-app-capabilities",
        "START",
        "CHECKPOINT",
        "HANDOFF",
        "release the claim",
        "Do not install",
        "Do not start",
        "PR #13",
        "PR #7",
        "live operation remained disabled",
    ):
        assert required in text


def test_runbook_separates_operator_actions_from_agent_actions() -> None:
    text = _read(RUNBOOK)
    for required in (
        "The operator performs every elevated or physical action explicitly.",
        "winget show --id WiresharkFoundation.USBPcap",
        "winget install --id WiresharkFoundation.USBPcap",
        "winget uninstall --id WiresharkFoundation.USBPcap",
        "USBPcapCMD.exe -d",
        "Do not start the experiment.",
        "expiring authorization",
    ):
        assert required in text


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

    forbidden_executable_actions = (
        "winget install",
        "winget uninstall",
        "Start-Process -Verb RunAs",
        "runas.exe",
        "--execute-live",
        "--allow-live",
        "--force-live",
    )
    lowered = text.lower()
    for forbidden in forbidden_executable_actions:
        assert forbidden.lower() not in lowered


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
