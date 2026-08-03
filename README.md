# AgentKVM2USB

AgentKVM2USB is a Python SDK for the Epiphan KVM2USB 3.0.

It provides an interface for video capture (up to 1080p @ 60fps) and programmatic KVM control (keyboard, mouse, and touch injection), utilizing standard HID and UVC interfaces. It does not require the original Epiphan vendor drivers or SDK.

## Key Features
- **Unified SDK**: Control video and HID inputs via a single Python class.
- **Cross-Platform**: Natively supports Windows (DirectShow), Linux (V4L2), and macOS (AVFoundation).
- **Agent-Ready API**: Provides a high-level API (e.g., `sdk.type()`, `sdk.click()`) structured for AI agent integration. See [AGENTS.md](AGENTS.md) for agent instructions.
- **Macro Engine**: Includes a Domain Specific Language (DSL) for executing multi-step KVM routines. See [MACROS.md](MACROS.md).
- **Standard Protocol Implementation**: Bypasses legacy proprietary protocols by utilizing standard HID and UVC interfaces.
- **Automated Monitoring**: Implements automated target re-enumeration and status monitoring (Resolution, Signal Active, Keyboard LEDs).

## Windows Portable Release

GitHub Releases can provide a Windows-consumable portable ZIP containing the SDK,
GUI, utilities, requirements, documentation, and local dependency/launch helpers.
The archive intentionally uses the host Python installation rather than bundling an
untested hardware-access executable.

After extracting a release asset:

1. Run `Install-Dependencies.cmd` to create a local `.venv` and install dependencies.
2. Run `Run-AgentKVM2USB.cmd` to start the GUI.
3. Verify the ZIP against its sibling `.sha256` release asset before extraction.

Maintainers can build and publish the assets locally without GitHub Actions:

```powershell
py -3 scripts\build_portable.py
py -3 scripts\release.py --tag v0.2.0
```

See [PACKAGING.md](PACKAGING.md) for the complete build, release, checksum, hardware,
and Windows Package Foundry integration guidance.

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Linux Permissions (One-time)
```bash
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="2b77", ATTR{idProduct}=="3661", MODE="0666"' | sudo tee /etc/udev/rules.d/99-epiphan.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### 3. Usage Example
```python
from epiphan_sdk import EpiphanKVM_SDK

# Initialize SDK
sdk = EpiphanKVM_SDK()

# Check target status
print(f"Target Resolution: {sdk.get_status()['resolution']}")

# Perform actions
sdk.type("sudo reboot")
sdk.press("enter")

# Capture screen for processing
sdk.get_screen("observation.jpg")

sdk.close()
```

## Project Structure
- `epiphan_sdk.py`: Core SDK library.
- `test_sdk.py`: Test suite (supports hardware & mock testing).
- `PROJECT_STATUS.md`: Current triage, validation results, known gaps, and phased remediation strategy.
- `HARDWARE_REPORT.md`: Reverse-engineering documentation and component analysis.
- `VIDEO_PIPELINE.md`: Current physical, HID, UVC, DirectShow, and OpenCV video pipeline findings.
- `VENDOR_ARTIFACTS.md`: Official Epiphan download inventory, hashes, extracted package notes, and reverse-engineering leads.
- `RECOVERED_CAPABILITIES.md`: App, driver, firmware, HID, and config-interface capability matrix recovered from official artifacts.
- `FIRMWARE_UPDATE_RECOVERY.md`: Offline firmware, FPGA, update-container, checksum, and transfer-plan recovery notes.
- `OPENKVM2USB_STRATEGY.md`: Long-term clean-room strategy for an open host, protocol, FX3 firmware, and Spartan-6 FPGA stack.
- `manifests/`: Public metadata schemas and document acquisition checklists for private evidence and reproducibility records.
- `BACKLOG.md`: Development roadmap and protocol research notes.
- `AGENTS.md`: Dedicated instructions for AI agents operating the SDK.
- `MACROS.md`: Documentation for the Macro Engine DSL.
- `PACKAGING.md`: Local Windows artifact, release, and Package Foundry guidance.
- `scripts/`: Local portable-build and GitHub Release scripts.
- `scripts/inspect_epiphan_firmware.py`: Offline parser for Epiphan `.fw`,
  FX3 `.img`, FPGA `.bin`, EDID text dumps, and package metadata.
- `scripts/inspect_epiphan_config.py`: Offline recovered MI_00 request map and
  config-payload parser.
- `scripts/probe_mi00_config.py`: Guarded live read-only MI_00 WinUSB/libusb
  probe for input status, user modes, and device flags.
- `scripts/capture_mi00_experiment.py`: Captures a deterministic read-only
  MI_00 experiment directory for replay and USBPcap correlation.
- `scripts/summarize_trace.py`: Summarizes deterministic experiment trace
  directories for no-hardware replay.

## Testing
Run the comprehensive test suite to verify your setup:
```bash
pytest -v test_sdk.py
```

For repository-wide syntax validation:

```bash
python -m compileall -q .
```

Hardware validation requires the physical Epiphan KVM2USB and a powered target. See
`PROJECT_STATUS.md` for the latest observed HID/UVC status and current signal-path
limitations.

Per-run config, user presets, screenshots, recordings, SRT files, and session logs
are written under:

```text
runtime_sessions/<YYYYMMDDTHHMMSSZ>-<correlation-id>/
```

To emit machine-consumable hardware diagnostics:

```bash
python hardware_probe.py --capture
```

To include guarded read-only MI_00 config-interface diagnostics after the
official WinUSB INF is bound:

```bash
python hardware_probe.py --include-mi00 --libusb-dll path\to\libusb-1.0.dll
```

To capture a replayable read-only MI_00 experiment under `.work/experiments/`:

```bash
python scripts/capture_mi00_experiment.py --libusb-dll path\to\libusb-1.0.dll
```

Runtime captures, logs, and per-run config can be redirected with either:

```bash
set AGENTKVM2USB_SESSION_ROOT=C:\KVM-Lab\Sessions
python hardware_probe.py --runtime-root C:\KVM-Lab\Sessions
```

## Contributing
Please see `BACKLOG.md` for current development priorities. High-risk features such as firmware flashing are currently deferred to protect hardware safety.

---
*Disclaimer: This project is not affiliated with Epiphan Video. It is a reverse-engineered community effort to provide modern automation support for legacy hardware.*
