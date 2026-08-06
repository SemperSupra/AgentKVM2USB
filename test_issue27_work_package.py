from pathlib import Path


ROOT = Path(__file__).resolve().parent
ACTIVE = ROOT / "docs" / "ACTIVE_WORKSTREAMS.md"
RUNBOOK = ROOT / "docs" / "ISSUE27_OPERATOR_DEPENDENCY_RUNBOOK.md"
KICKOFF = ROOT / "prompts" / "ISSUE27_KICKOFF.md"
PROMPT = ROOT / "prompts" / "ISSUE27_OPERATOR_DEPENDENCIES.md"
SCRIPT = ROOT / "scripts" / "prepare_issue22_dependencies.ps1"
ISSUE22_RUNBOOK = ROOT / "docs" / "ISSUE22_OPERATOR_RUNBOOK.md"
ISSUE22_PROMPT = ROOT / "prompts" / "ISSUE22_WORKSTATION_CAPTURE_DEPS.md"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing work-package file: {path}"
    return path.read_text(encoding="utf-8")


def test_issue27_work_package_files_exist() -> None:
    for path in (ACTIVE, RUNBOOK, KICKOFF, PROMPT, SCRIPT):
        assert path.is_file()


def test_active_workstreams_define_nonoverlapping_lanes() -> None:
    text = _read(ACTIVE)
    for required in (
        "Lane A — AgentKVM2USB issue #27",
        "Lane B — Windows Package Foundry issues #1 and #2",
        "Lane C — AgentKVM2USB issue #22",
        "Lane D — AgentKVM2USB issue #14",
        "Lane E — PR #13 / issue #8 Phase B",
        "START",
        "CHECKPOINT",
        "HANDOFF",
        "issue-27-operator-dependencies",
    ):
        assert required in text


def test_prompt_preserves_claim_and_safety_boundaries() -> None:
    text = _read(PROMPT)
    for required in (
        "issue-27-operator-dependencies",
        "recovery/agentkvm2usb-app-capabilities",
        "START",
        "CHECKPOINT",
        "HANDOFF",
        "release the claim",
        "WiresharkFoundation.Wireshark",
        "SemperSupra/windows-package-foundry#1",
        "SemperSupra/windows-package-foundry#2",
        "SupraCraft/minecraft-infra/scripts/local/Invoke-Elevated.ps1",
        "PR #13",
        "no capture",
        "automatic reboot",
    ):
        assert required in text


def test_minimal_kickoff_tracks_remote_branch_safely() -> None:
    text = _read(KICKOFF)
    for required in (
        "issue #27 and draft PR #28",
        "origin/issue-27-operator-dependencies",
        "git branch --track issue-27-operator-dependencies",
        "git worktree add",
        "Run claim preflight",
        "Do not directly install USBPcap",
        "Do not modify PR #13",
    ):
        assert required in text


def test_script_uses_exact_winget_package_and_shared_helper() -> None:
    text = _read(SCRIPT)
    for required in (
        '$WiresharkPackageId = "WiresharkFoundation.Wireshark"',
        '$WiresharkPackageSource = "winget"',
        '$ExpectedHelperRepository = "SupraCraft/minecraft-infra"',
        '$HelperRelativePath = "scripts\\local\\Invoke-Elevated.ps1"',
        'New-Module -Name "AgentKvmMinecraftInfraUac"',
        ". $PathToHelper",
        "Import-Module $module",
        "Invoke-Elevated",
        '"--id", $WiresharkPackageId',
        '"--source", $WiresharkPackageSource',
        '"--accept-package-agreements"',
        '"--accept-source-agreements"',
    ):
        assert required in text


def test_usbpcap_is_fail_closed_without_fallback() -> None:
    text = _read(SCRIPT)
    assert "Stop-UsbPcapInstall" in text
    assert "windows-package-foundry#1" in text
    assert "windows-package-foundry#2" in text
    assert "No direct installer or alternate package-manager fallback is permitted" in text

    lowered = text.lower()
    for forbidden in (
        "wiresharkfoundation.usbpcap",
        "usbpcapsetup-",
        "invoke-webrequest",
        "start-bitstransfer",
        "choco install",
        "scoop install",
    ):
        assert forbidden not in lowered


def test_vendor_staging_is_local_ignored_and_provenance_bound() -> None:
    text = _read(SCRIPT)
    for required in (
        ".work\\vendor\\totalphase",
        ".work\\vendor\\epiphan",
        "Assert-GitIgnoredPath",
        "Get-FileHash -Algorithm SHA256",
        ".provenance.json",
        "credentials_recorded = $false",
        "cookies_recorded = $false",
        "tokens_recorded = $false",
        "committed_to_git = $false",
        "same staged filename",
    ):
        assert required in text


def test_portable_staging_does_not_request_uac() -> None:
    text = _read(SCRIPT)
    stage_start = text.index("function Stage-VendorArtifact")
    stage_end = text.index("function Get-VerifiedStagedEpiphanInstaller")
    stage_body = text[stage_start:stage_end]
    assert "Invoke-Elevated" not in stage_body
    assert "Start-Process" not in stage_body


def test_staged_epiphan_install_is_human_gated_and_hash_checked() -> None:
    text = _read(SCRIPT)
    for required in (
        "Get-VerifiedStagedEpiphanInstaller",
        "hash no longer matches its provenance record",
        "Install-StagedEpiphanArtifact",
        "Import-TrustedUacHelper",
        "Invoke-Elevated",
        "review and accept every interactive installer decision",
        "Get-InstalledApplicationRecords -Pattern \"Epiphan|KVM2USB\"",
    ):
        assert required in text


def test_plan_and_whatif_are_fail_closed() -> None:
    text = _read(SCRIPT)
    for required in (
        "SupportsShouldProcess = $true",
        "live_disabled = $true",
        "plan_elevates = $false",
        "plan_installs = $false",
        "starts_capture = $false",
        "sends_target_input = $false",
        "initiates_reboot = $false",
        "reboot_initiated_by_script = $false",
        "if ($WhatIfPreference",
        "elevated_child_started = $false",
        "installation_started = $false",
        "vendor_installer_started = $false",
    ):
        assert required in text

    lowered = text.lower()
    for forbidden in (
        "restart-computer",
        "shutdown.exe",
        "--execute-live",
        "--allow-live",
        "capture_beagle_usb12.py",
        "capture_mi00_experiment.py",
        "run_macro(",
    ):
        assert forbidden not in lowered


def test_issue22_documents_delegate_acquisition_to_issue27() -> None:
    runbook = _read(ISSUE22_RUNBOOK)
    prompt = _read(ISSUE22_PROMPT)
    combined = runbook + "\n" + prompt
    assert "issue #27" in combined.lower()
    assert "WiresharkFoundation.USBPcap" not in combined
    assert "dependency acquisition" in combined.lower()
    assert "USBPcap interface-to-KVM2USB" in combined
