# AgentKVM2USB Backlog

This document tracks features requiring USB protocol sniffing (Wireshark/USBPcap) for implementation.

## Device Investigation Priorities
- [x] **Program Separation:** PR `#6` was restored to packaging baseline scope and merged. The private evidence vault and private-first clean `OpenKVM2USB` repository were created and seeded.
- [ ] **Provenance Manifests:** Use `manifests/artifact.schema.yaml`, `manifests/experiment.schema.yaml`, and `manifests/environment.schema.yaml` for evidence-vault and reproducible-build records.
- [x] **Live Mode HID Report:** Map the observed KVM2USB 3.0 live mode report. Usage `0x103`, feature report `3`, returns `width_le16`, `height_le16`, and an active flag. Verified with `1920x1080 active`.
- [x] **Structured Hardware Probe v2:** Extend `hardware_probe.py` to emit HID collection metadata, status source, UVC ownership/open state, frame statistics, and effective signal inference in one JSON document.
- [x] **Initial UVC / DirectShow Capability Map:** Enumerate supported formats, resolutions, frame rates, actual backend, FOURCC, and camera-open failure cases. Prefer stable camera selection by device name over index. See `VIDEO_PIPELINE.md`.
- [ ] **UVC / DirectShow Follow-Up:** Confirm whether the advertised mode list changes with different target resolutions, adapter chains, or USB host ports.
- [x] **Trace Replay Foundation:** Add deterministic experiment-directory replay helpers for descriptors, device status, and host JSONL logs.
- [x] **HID Report Map:** Recover KVM2USB 3.0 keyboard, mouse, touch, live-size, touch-type, and re-enumerate report IDs/lengths from Linux vendor-app disassembly. SDK keyboard, relative mouse, and touch framing now follows the vendor report IDs with legacy fallbacks. Keep live write-path validation deferred until a human approves a hardware-safe target session.
- [x] **Recovered Capability Matrix:** Document recovered app, driver, firmware, HID, and config-interface features in `RECOVERED_CAPABILITIES.md`.
- [x] **MI_00 Config Interface Probe:** Built and live-validated after user approval on 2026-08-03. The official Epiphan INF binds `VID_2B77&PID_3661&MI_00` to WinUSB, and `scripts/probe_mi00_config.py` performs guarded read-only PyUSB/libusb requests around interface GUID `{9f543223-cede-4fa3-b376-a25ce9a30e74}`. Live-validated requests: vendor IN `0xB2` input status, `0xB3` user mode, and `0xE2` device flags only. Do not send `0x40` OUT requests, update requests, EDID writes, or flash writes.
- [x] **MI_00 SDK/Probe Integration:** `EpiphanKVM_SDK.get_config_status()`, `get_device_health(include_mi00=True)`, `hardware_probe.py --include-mi00`, and GUI Tools -> Read Config Status now expose the guarded read-only config status path, including all three `0xB3` user-mode slots.
- [x] **MI_00 Experiment Capture:** `scripts/capture_mi00_experiment.py` writes deterministic read-only MI_00 experiment directories with `metadata.yaml`, `descriptors.json`, `device-status.json`, `mi00-status.json`, and `host-log.jsonl`; `scripts/summarize_trace.py` now summarizes MI_00 captures for replay and USBPcap correlation.
- [ ] **MI_00 Protocol Confirmation:** Capture official configuration-tool USBPcap traces for the now-live read paths, then compare request values, indexes, payloads, and parsed values against the clean probe.
- [x] **Vendor Config Request Map:** Static disassembly confirms config requests `0xB2`, `0xB3`, `0xE2`, `0xE3`, and update/EDID requests including `0xA0`, `0xC4`, `0xC5`, and `0xD4`. `InputStatusInfo`, `UserMode`, and device flag payloads are mapped and exposed through offline parser/building helpers plus `scripts/inspect_epiphan_config.py`. Next step is USBPcap confirmation of read-only official-tool actions before implementing a live probe.
- [x] **FX3 Firmware Container Parser:** Add offline Cypress FX3 `.img` parsing, checksum validation, entry address recovery, and request `0xA0` chunk planning. See `FIRMWARE_UPDATE_RECOVERY.md`.
- [ ] **FPGA Bitstream Packet Decoder:** First-pass decoder now normalizes the bit-reversed FPGA payload to canonical Xilinx sync `aa 99 55 66` and emits packet-like records, opcode counts, and truncation flags. Continue with UG380/TORC cross-checking before treating register names, CRC behavior, or frame boundaries as authoritative.
- [x] **Signal Health Model:** Distinguish HID-reported signal, UVC stream-open state, latest-frame presence, blank-frame detection, and stale-frame detection in SDK/GUI status.
- [ ] **Harmless HID Injection Validation:** Validate keyboard, mouse, touch, touch-type, re-enumerate, and macro behavior against safe firmware screens or a sacrificial OS session. Prefer `sdk.run_macro()` for sequences.

## High-Risk / Low-Priority
- [ ] **Custom Firmware Flasher:** Reverse engineer and validate firmware/update flows. Static analysis has identified request IDs, but implementation remains deferred high-risk work.
- [ ] **Custom Firmware Builder:** Define a reproducible offline build/sign/checksum pipeline for custom FX3 images before any live updater exists.
- [ ] **Custom FPGA Builder:** Identify FPGA family/toolchain constraints and bitstream compatibility before any live FPGA update support exists.
- [ ] **Custom EDID Injector:** Implement raw EDID writes only after read-only EDID extraction and a hardware-safe write/rollback plan are approved. Current `0xA0` evidence is chunked write/read-verify update machinery, not a safe live EDID read API.
- [ ] **Signal Diagnostics:** Extract raw VGA/DVI sync timing parameters (H-Sync, V-Sync, Phase) programmatically.

## Automation States
- [ ] **State Detection Templates:** Pre-captured images of the Spartan-6 / FX3 boot screens for automated state detection.

## Agent-Ready Feature Pipeline
- [ ] **Named Macro Library:** Add a persistent gallery for saved DSL scripts (e.g., "Reset to BIOS", "Install Windows Update").
- [ ] **Vision-Conditional Macros:** Extend DSL with `WAIT_FOR_MOTION`, `WAIT_FOR_SIGNAL`, or `IF_MOTION_STOP` for feedback-loop automation.
- [ ] **Remote Control API (Headless Mode):** Implement a FastAPI or WebSocket bridge to allow remote AI agents to call `get_processed_frame` and `run_macro`.
- [ ] **OCR Integration:** Integrate `pytesseract` or `easyocr` to enable `WAIT_FOR_TEXT "Welcome"` and searchable screen content.
- [ ] **Multi-KVM Dashboard:** Support a grid-view mode for users with 2-4 devices connected to a single host.

## Testability and Repository Hygiene
- [ ] **Structured Hardware Probe:** Keep expanding the script that emits JSON for HID endpoint state, camera enumeration, signal state, frame shape, frame statistics, and sample capture path.
- [x] **Structured Macro Results:** Return parse/runtime errors from `run_macro()` instead of only printing them.
- [ ] **Configurable Session Output Root:** Allow lab automation to override the default `runtime_sessions/` root.
- [ ] **Persistent Profile Store:** Decide whether non-secret user presets should remain per-run or be promoted to a user profile directory outside the repository.
- [ ] **Clean Windows Smoke Test:** Validate the portable ZIP on a clean Windows 11 machine with no repository checkout.
