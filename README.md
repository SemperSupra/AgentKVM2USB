# AgentKVM2USB

AgentKVM2USB is a Python SDK for the Epiphan KVM2USB 3.0.

It provides an interface for video capture (up to 1080p @ 60fps) and HID input development (keyboard, mouse, and touch report research), utilizing standard HID and UVC interfaces. Target-side HID forwarding and activation remain under investigation and are not yet demonstrated as end-to-end control. It does not require the original Epiphan vendor drivers or SDK.

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

## Repository Coordination and Metadata

The remote GitHub repository is the authoritative coordination surface for web
agents, local terminal agents, automation, and human reviewers. A workstream must
have a canonical issue, bounded branch, draft pull request, remote validation
record, and `START`/`CHECKPOINT`/`DECISION`/`BLOCKER`/`HANDOFF` comments. Chat and
local-only notes are not sufficient project records.

Read:

- [AGENTS.md](AGENTS.md) for mandatory agent operating rules;
- [Remote Agent Coordination Protocol](docs/REMOTE_AGENT_COORDINATION.md) for branch, PR, ownership, handoff, and evidence discipline;
- [repository-metadata.json](.github/repository-metadata.json) for expected project-specific GitHub and documentation metadata;
- [agent-handoff.schema.json](.github/agent-handoff.schema.json) for machine-readable coordination records.

Validate local and remote metadata drift with:

```bash
python scripts/validate_repository_metadata.py --remote auto
```

The validator reports differences and never silently rewrites repository settings.

## Project Structure
- `epiphan_sdk.py`: Core SDK library.
- `test_sdk.py`: Test suite (supports hardware & mock testing).
- `PROJECT_STATUS.md`: Current triage, validation results, known gaps, and phased remediation strategy.
- `HARDWARE_REPORT.md`: Reverse-engineering documentation and component analysis.
- `BACKLOG.md`: Development roadmap and protocol research notes.
- `AGENTS.md`: Dedicated instructions for AI agents operating the SDK.
- `MACROS.md`: Documentation for the Macro Engine DSL.
- `PACKAGING.md`: Local Windows artifact, release, and Package Foundry guidance.
- `docs/REMOTE_AGENT_COORDINATION.md`: Canonical remote multi-agent coordination protocol.
- `.github/repository-metadata.json`: Expected repository identity and metadata.
- `.github/agent-handoff.schema.json`: Structured agent coordination record schema.
- `scripts/`: Local build, release, validation, and repository-governance scripts.

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

## Contributing

Create or use a canonical GitHub issue before implementation, work on a bounded
issue branch, open a draft PR early, and publish all validation and handoff state
through the remote repository. See `BACKLOG.md` for development priorities.
High-risk features such as firmware flashing remain deferred unless a canonical
issue contains explicit authorization and a hardware-safe recovery plan.

---
*Disclaimer: This project is not affiliated with Epiphan Video. It is a reverse-engineered community effort to provide modern automation support for legacy hardware.*
