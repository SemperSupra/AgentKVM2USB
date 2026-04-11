# AgentKVM2USB Backlog

This document tracks features requiring USB protocol sniffing (Wireshark/USBPcap) for implementation.

## High-Risk / Low-Priority
- [ ] **Custom Firmware Flasher:** Reverse engineer `bRequest` vendor codes for writing to FX3/FPGA flash.
- [ ] **Custom EDID Injector:** Implement raw I2C/EEPROM writes via USB Control Endpoint 0 to set custom monitor profiles.
- [ ] **Signal Diagnostics:** Extract raw VGA/DVI sync timing parameters (H-Sync, V-Sync, Phase) programmatically.

## Automation States
- [ ] **State Detection Templates:** Pre-captured images of the Spartan-6 / FX3 boot screens for automated state detection.

## Agent-Ready Feature Pipeline
- [ ] **Named Macro Library:** Add a persistent gallery for saved DSL scripts (e.g., "Reset to BIOS", "Install Windows Update").
- [ ] **Vision-Conditional Macros:** Extend DSL with `WAIT_FOR_MOTION`, `WAIT_FOR_SIGNAL`, or `IF_MOTION_STOP` for feedback-loop automation.
- [ ] **Remote Control API (Headless Mode):** Implement a FastAPI or WebSocket bridge to allow remote AI agents to call `get_processed_frame` and `run_macro`.
- [ ] **OCR Integration:** Integrate `pytesseract` or `easyocr` to enable `WAIT_FOR_TEXT "Welcome"` and searchable screen content.
- [ ] **Multi-KVM Dashboard:** Support a grid-view mode for users with 2-4 devices connected to a single host.
