import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "scripts" / "prepare_issue22_dependencies.ps1"
PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(PWSH is None, reason="PowerShell 7 is required")


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    assert PWSH is not None
    return subprocess.run(
        [PWSH, "-NoProfile", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_dependency_script_parses_in_powershell() -> None:
    escaped = str(SCRIPT).replace("'", "''")
    command = (
        "$tokens = $null; $errors = $null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{escaped}', "
        "[ref]$tokens, [ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { "
        "$errors | ForEach-Object { Write-Error $_.Message }; exit 1 }"
    )
    result = _run("-Command", command)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("dependency", ["USBPcap", "Wireshark"])
def test_install_whatif_is_a_clean_noop(dependency: str) -> None:
    result = _run(
        "-File",
        str(SCRIPT),
        "-Install",
        dependency,
        "-WhatIf",
        "-RepoRoot",
        str(ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["what_if"] is True
    assert payload["installation_started"] is False
    assert payload["elevated_child_started"] is False
    assert payload["vendor_installer_started"] is False
    assert payload["reboot_initiated"] is False


def test_plan_is_no_live_and_writes_ignored_evidence() -> None:
    output = ROOT / ".work" / "evidence" / "issue-27-ci" / "plan.json"
    result = _run(
        "-File",
        str(SCRIPT),
        "-Plan",
        "-RepoRoot",
        str(ROOT),
        "-OutputPath",
        str(output),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["live_disabled"] is True
    assert payload["safety"]["plan_elevates"] is False
    assert payload["safety"]["plan_installs"] is False
    assert payload["safety"]["starts_capture"] is False
    assert payload["safety"]["sends_target_input"] is False
    assert payload["safety"]["initiates_reboot"] is False
    assert output.is_file()

    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", str(output.relative_to(ROOT))],
        cwd=ROOT,
        check=False,
    )
    assert ignored.returncode == 0
