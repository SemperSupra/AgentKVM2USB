# Windows Packaging and Release

AgentKVM2USB is currently a loose Python SDK and GUI with hardware-sensitive UVC,
HID, OpenCV, PySide6, and Windows DirectShow dependencies. The public artifact is
therefore a portable ZIP rather than a frozen executable. This keeps the hardware
access path visible and avoids presenting an untested PyInstaller bundle as a
stable application.

## Artifact contents

The build copies all top-level Python utilities, `requirements.txt`, `config.json`,
and the user-facing Markdown documentation. It also generates:

- `Install-Dependencies.ps1` and `.cmd` to create a local `.venv` and install the
  pinned-by-repository dependency set.
- `Run-AgentKVM2USB.ps1` and `.cmd` to launch `kvmapp_gui.py` from that environment.
- `PORTABLE-README.md` with end-user installation, hardware, integrity, and
  uninstall guidance.

The archive does not install vendor drivers, write firmware, or register a system
service. Removing the extracted directory removes the application and its virtual
environment.

## Local build

Prerequisite: Python 3. The build itself uses only the Python standard library.
From the repository root:

```powershell
py -3 scripts\build_portable.py
```

To override the version embedded in the filename:

```powershell
py -3 scripts\build_portable.py --version 0.2.1
```

The script deletes and recreates `dist/`, stages a clean payload, and produces:

```text
dist/AgentKVM2USB-v<version>-windows-portable.zip
dist/AgentKVM2USB-v<version>-windows-portable.zip.sha256
```

The ZIP is written in sorted order with fixed member timestamps so identical input
files produce identical archive bytes.

## Checksum verification

The `.sha256` file uses the common `<hash>  <filename>` format. Verify a downloaded
artifact before extracting it:

```powershell
$Zip = ".\AgentKVM2USB-v0.2.0-windows-portable.zip"
$Expected = (Get-Content "$Zip.sha256").Split()[0]
$Actual = (Get-FileHash $Zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Expected -ne $Actual) { throw "Checksum mismatch" }
```

## Local release

Prerequisites:

1. Python 3.
2. GitHub CLI (`gh`) authenticated with permission to update releases in
   `SemperSupra/AgentKVM2USB`.
3. A clean, reviewed commit at the intended release target.

Create or update a release and upload both assets:

```powershell
py -3 scripts\release.py --tag v0.2.0
```

The release script:

1. Rebuilds the portable artifact from a clean `dist/` directory.
2. Verifies the generated checksum locally.
3. Runs `gh auth status`.
4. Creates the release if it does not exist, or reuses the existing release.
5. Uploads the ZIP and `.sha256` with `gh release upload --clobber`.

Optional examples:

```powershell
py -3 scripts\release.py --tag v0.2.1 --target main --notes-file RELEASE_NOTES.md
py -3 scripts\release.py --tag v0.2.1 --skip-build
```

No GitHub-hosted runner is used for artifact creation or release publication.

## Windows installation and hardware caveats

1. Install a current 64-bit Python 3 distribution.
2. Extract the ZIP to a user-writable directory.
3. Connect the Epiphan KVM2USB 3.0.
4. Run `Install-Dependencies.cmd` while internet access is available.
5. Run `Run-AgentKVM2USB.cmd`.

Full behavior cannot be validated without the physical device. Windows camera
capture depends on DirectShow/UVC, HID injection depends on `hidapi`, and friendly
camera enumeration depends on `pygrabber`. Endpoint security policy, USB device
control, camera privacy settings, or another process holding the capture device can
prevent discovery. Hardware-writing and firmware-flashing behavior is not added to
the package.

## Package Foundry integration

`.package-foundry/package.json` declares the latest GitHub Release as the source of
truth and matches these assets:

```text
AgentKVM2USB-v*-windows-portable.zip
AgentKVM2USB-v*-windows-portable.zip.sha256
```

The portable ZIP can be wrapped for the private/public deployment points as:

- Scoop portable package with `Run-AgentKVM2USB.cmd` as the command alias.
- Chocolatey portable package with a local dependency-bootstrap step.
- Local Winget ZIP/portable metadata where the deployment point supports the
  generated bootstrap requirement.

The metadata explicitly disables official Winget submission, Chocolatey Community
publication, official Scoop bucket publication, and PortableApps.com publication.
Deployment-point automation should resolve the latest release asset URL, read the
sibling checksum, and generate only organization-controlled metadata.
