# AgentKVM2USB Backlog

This file tracks advanced features that require USB protocol sniffing (Wireshark/USBPcap) to implement safely without risk of bricking the KVM2USB 3.0 hardware.

## High-Risk / Low-Priority
- [ ] **Custom Firmware Flasher:** Reverse engineer `bRequest` vendor codes for writing to FX3/FPGA flash.
- [ ] **Custom EDID Injector:** Implement raw I2C/EEPROM writes via USB Control Endpoint 0 to set custom monitor profiles.
- [ ] **Advanced Signal Diagnostics:** Extract raw VGA/DVI sync timing parameters (H-Sync, V-Sync, Phase) programmatically.

## Optimization
- [ ] **HID Macro Engine:** Build a high-level DSL for complex key combinations (e.g., `ctrl+alt+t`).
- [ ] **OpenCV Template Library:** Pre-captured images of the Terasic DE2-115 boot screens for automated state detection.
