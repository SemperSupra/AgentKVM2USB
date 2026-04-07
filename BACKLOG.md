# AgentKVM2USB Backlog

This document tracks features requiring USB protocol sniffing (Wireshark/USBPcap) for implementation.

## High-Risk / Low-Priority
- [ ] **Custom Firmware Flasher:** Reverse engineer `bRequest` vendor codes for writing to FX3/FPGA flash.
- [ ] **Custom EDID Injector:** Implement raw I2C/EEPROM writes via USB Control Endpoint 0 to set custom monitor profiles.
- [ ] **Signal Diagnostics:** Extract raw VGA/DVI sync timing parameters (H-Sync, V-Sync, Phase) programmatically.

## Automation States
- [ ] **State Detection Templates:** Pre-captured images of the Spartan-6 / FX3 boot screens for automated state detection.
