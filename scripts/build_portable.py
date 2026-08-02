#!/usr/bin/env python3
"""Build a reproducible Windows-consumable portable ZIP for AgentKVM2USB."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

PROJECT_NAME = "AgentKVM2USB"
VERSION_FILE = "epiphan_sdk.py"
REQUIRED_RUNTIME_FILES = (
    "epiphan_sdk.py",
    "frame_processor.py",
    "kvmapp_gui.py",
    "requirements.txt",
)
ROOT_DATA_FILES = ("requirements.txt", "config.json")
RUNTIME_PYTHON_FILES = (
    "analyze_firmware.py",
    "dump_hid.py",
    "dump_usb.py",
    "dump_usb2.py",
    "epiphan_sdk.py",
    "fpga_automation.py",
    "frame_processor.py",
    "kvmapp_gui.py",
    "probe_hid.py",
    "settings_dialog.py",
)
ROOT_DOCUMENTS = (
    "README.md",
    "AGENTS.md",
    "MACROS.md",
    "PACKAGING.md",
    "HARDWARE_REPORT.md",
    "BACKLOG.md",
)
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        help="Artifact version. Defaults to VERSION in epiphan_sdk.py.",
    )
    parser.add_argument(
        "--dist-dir",
        type=Path,
        help="Output directory. Defaults to <repository>/dist.",
    )
    parser.add_argument(
        "--keep-stage",
        action="store_true",
        help="Keep the temporary staging directory for inspection.",
    )
    return parser.parse_args()


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_project_version(root: Path) -> str:
    version_path = root / VERSION_FILE
    text = version_path.read_text(encoding="utf-8")
    match = re.search(r'^\s*VERSION\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Could not find VERSION in {version_path}")
    return match.group(1)


def normalize_version(value: str) -> str:
    version = value.strip()
    if version.lower().startswith("v"):
        version = version[1:]
    if not version or not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._+-]*", version):
        raise ValueError(f"Invalid version: {value!r}")
    return version


def ensure_runtime_files(root: Path) -> None:
    missing = [name for name in REQUIRED_RUNTIME_FILES + RUNTIME_PYTHON_FILES if not (root / name).is_file()]
    if missing:
        raise FileNotFoundError("Required runtime files are missing: " + ", ".join(missing))


def write_windows_text(path: Path, content: str) -> None:
    normalized = content.strip() + "\n"
    with path.open("w", encoding="utf-8", newline="\r\n") as handle:
        handle.write(normalized)


def install_dependencies_ps1() -> str:
    return r'''
[CmdletBinding()]
param(
    [string]$VirtualEnvironment = ".venv"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPath = Join-Path $Root $VirtualEnvironment
$Requirements = Join-Path $Root "requirements.txt"

function Invoke-SystemPython {
    param([Parameter(Mandatory = $true)][string[]]$PythonArgs)

    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 @PythonArgs
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python @PythonArgs
    }
    else {
        throw "Python 3 was not found. Install a 64-bit Python 3 distribution and try again."
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Python exited with code $LASTEXITCODE."
    }
}

if (-not (Test-Path $Requirements)) {
    throw "requirements.txt was not found in $Root"
}

if (-not (Test-Path $VenvPath)) {
    Write-Host "Creating virtual environment at $VenvPath"
    Invoke-SystemPython -PythonArgs @("-m", "venv", $VenvPath)
}

$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment Python was not created at $VenvPython"
}

& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed with code $LASTEXITCODE." }

& $VenvPython -m pip install -r $Requirements
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed with code $LASTEXITCODE." }

Write-Host "Dependencies installed. Start the GUI with Run-AgentKVM2USB.cmd."
'''


def run_gui_ps1() -> str:
    return r'''
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$EntryPoint = Join-Path $Root "kvmapp_gui.py"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $EntryPoint)) {
    throw "kvmapp_gui.py was not found in $Root"
}

Push-Location $Root
try {
    if (Test-Path $VenvPython) {
        & $VenvPython $EntryPoint @args
    }
    elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 $EntryPoint @args
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python $EntryPoint @args
    }
    else {
        throw "Python 3 was not found. Run Install-Dependencies.cmd after installing Python."
    }

    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
'''


def install_dependencies_cmd() -> str:
    return r'''
@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Dependencies.ps1" %*
exit /b %ERRORLEVEL%
'''


def run_gui_cmd() -> str:
    return r'''
@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-AgentKVM2USB.ps1" %*
exit /b %ERRORLEVEL%
'''


def portable_readme(version: str) -> str:
    return f"""# AgentKVM2USB v{version} — Windows Portable

This archive contains the AgentKVM2USB Python SDK, GUI, diagnostics, documentation,
and Windows launch helpers. It intentionally does not bundle Python or hardware
access libraries into a single executable.

## Install

1. Install a current 64-bit Python 3 distribution.
2. Extract the complete archive to a writable directory.
3. Connect the Epiphan KVM2USB 3.0 device.
4. Run `Install-Dependencies.cmd` while internet access is available.
5. Run `Run-AgentKVM2USB.cmd` to start the GUI.

The dependency installer creates a private `.venv` directory inside the extracted
folder. Delete the extracted folder to uninstall the portable application.

## Hardware notes

Full SDK and GUI functionality requires a physical Epiphan KVM2USB 3.0 device and
working Windows UVC/HID access. Camera enumeration uses DirectShow; HID control uses
`hidapi`; and Windows camera naming uses `pygrabber`. Security software, USB policy,
or another process holding the camera can prevent discovery or control.

Do not use the diagnostic or firmware-analysis utilities to write firmware. The
project's high-risk firmware-writing work remains intentionally deferred.

## Integrity

The release includes a sibling `.sha256` file. Verify it before extracting:

```powershell
$Expected = (Get-Content .\\AgentKVM2USB-v{version}-windows-portable.zip.sha256).Split()[0]
$Actual = (Get-FileHash .\\AgentKVM2USB-v{version}-windows-portable.zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Expected -ne $Actual) {{ throw "Checksum mismatch" }}
```

See `PACKAGING.md` in the source repository for build, release, and Package Foundry
integration details.
"""


def stage_files(root: Path, stage: Path, version: str) -> None:
    ensure_runtime_files(root)
    stage.mkdir(parents=True, exist_ok=True)

    for name in RUNTIME_PYTHON_FILES:
        shutil.copy2(root / name, stage / name)

    for name in ROOT_DATA_FILES + ROOT_DOCUMENTS:
        source = root / name
        if source.is_file():
            shutil.copy2(source, stage / name)

    write_windows_text(stage / "Install-Dependencies.ps1", install_dependencies_ps1())
    write_windows_text(stage / "Install-Dependencies.cmd", install_dependencies_cmd())
    write_windows_text(stage / "Run-AgentKVM2USB.ps1", run_gui_ps1())
    write_windows_text(stage / "Run-AgentKVM2USB.cmd", run_gui_cmd())
    (stage / "PORTABLE-README.md").write_text(portable_readme(version), encoding="utf-8")


def write_reproducible_zip(stage: Path, destination: Path) -> None:
    with ZipFile(destination, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for source in sorted(path for path in stage.rglob("*") if path.is_file()):
            relative = source.relative_to(stage).as_posix()
            info = ZipInfo(relative, date_time=FIXED_ZIP_TIMESTAMP)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    root = repository_root()
    version = normalize_version(args.version or read_project_version(root))
    dist = (args.dist_dir or (root / "dist")).resolve()
    stage = dist / ".stage"

    if dist.exists():
        shutil.rmtree(dist)
    stage.mkdir(parents=True)

    staged_payload = stage / PROJECT_NAME
    stage_files(root, staged_payload, version)

    zip_path = dist / f"{PROJECT_NAME}-v{version}-windows-portable.zip"
    checksum_path = zip_path.with_name(zip_path.name + ".sha256")
    write_reproducible_zip(staged_payload, zip_path)

    checksum = sha256_file(zip_path)
    checksum_path.write_text(f"{checksum}  {zip_path.name}\n", encoding="ascii")

    if not args.keep_stage:
        shutil.rmtree(stage)

    print(f"Built: {zip_path}")
    print(f"SHA256: {checksum_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
