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
- `HARDWARE_REPORT.md`: Reverse-engineering documentation and component analysis.
- `BACKLOG.md`: Development roadmap and protocol research notes.
- `AGENTS.md`: Dedicated instructions for AI agents operating the SDK.
- `MACROS.md`: Documentation for the Macro Engine DSL.

## Testing
Run the comprehensive test suite to verify your setup:
```bash
pytest -v test_sdk.py
```

## Contributing
Please see `BACKLOG.md` for current development priorities. High-risk features such as firmware flashing are currently deferred to protect hardware safety.

---
*Disclaimer: This project is not affiliated with Epiphan Video. It is a reverse-engineered community effort to provide modern automation support for legacy hardware.*
