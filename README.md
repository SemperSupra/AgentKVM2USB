# AgentKVM2USB

**AgentKVM2USB** is a universal, cross-platform, and agent-ready SDK for the **Epiphan KVM2USB 3.0**. 

It provides a high-performance, unified interface for video capture (up to 1080p @ 60fps) and programmatic KVM control (keyboard, mouse, and touch injection) without requiring the original, discontinued Epiphan vendor drivers or SDK.

## Key Features
- **Unified SDK**: Control video and HID inputs through a single Python class.
- **Cross-Platform**: Natively supports Windows (DirectShow), Linux (V4L2), and macOS (AVFoundation).
- **Agent-Ready**: High-level semantic API (e.g., `sdk.type()`, `sdk.click_percent()`) optimized for AI agents like Gemini, Codex, and Claude.
- **Reverse-Engineered**: Bypasses legacy proprietary protocols using standard HID and UVC interfaces.
- **Self-Healing**: Automated target re-enumeration and status monitoring (Resolution, Signal Active, Keyboard LEDs).

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
- `epiphan_sdk.py`: Core universal SDK library.
- `test_sdk.py`: Comprehensive test suite (supports hardware & mock testing).
- `HARDWARE_REPORT.md`: Detailed reverse-engineering documentation and component analysis.
- `BACKLOG.md`: Future roadmap and low-level protocol research notes.

## Testing
Run the comprehensive test suite to verify your setup:
```bash
pytest -v test_sdk.py
```

## Contributing
Please see `BACKLOG.md` for current development priorities. High-risk features such as firmware flashing are currently deferred to protect hardware safety.

---
*Disclaimer: This project is not affiliated with Epiphan Video. It is a reverse-engineered community effort to provide modern automation support for legacy hardware.*
