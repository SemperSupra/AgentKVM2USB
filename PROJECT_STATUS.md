# AgentKVM2USB Project Status

Last reviewed: 2026-08-02

Program strategy update reviewed: 2026-08-03. Long-term open-stack work is now
tracked in `OPENKVM2USB_STRATEGY.md`; public metadata schemas for artifacts,
experiments, environments, and vendor-document acquisition are under
`manifests/`.

## Repository Triage

- Active branch: `package-foundry/public-deployment-readiness`.
- Base branch: `main`.
- Open issue: `#5`, Windows Package Foundry public deployment readiness.
- Open pull request: `#6`, draft, targeting `main` from `package-foundry/public-deployment-readiness`.
- Stale remote branches observed after merged work: `origin/refactor/spartan-6-fx3-assumptions-8828302436159790485` and `origin/update-hardware-report-16011522587312263998`.
- No GitHub Actions workflow exists in this repository.

## Current Artifact Model

The public release artifact is a portable Windows ZIP, not a frozen executable. This keeps Python, PySide6, OpenCV, `hidapi`, `pygrabber`, DirectShow, UVC, and HID behavior visible and debuggable for humans and automation.

Release `v0.2.0` has these install assets:

- `AgentKVM2USB-v0.2.0-windows-portable.zip`
- `AgentKVM2USB-v0.2.0-windows-portable.zip.sha256`

Current SHA256:

```text
360ff91a7c4b76d90b5d115ceea379b4f8c8568e67c54c36f7c37a8ff413a3c1  AgentKVM2USB-v0.2.0-windows-portable.zip
```

## Hardware Validation

Hardware validation was run on 2026-08-02 with the Epiphan KVM2USB connected to a powered-on Wyse 5070.

Observed:

- Device LED: blue, which is expected for the KVM2USB 3.0 USB 3.0 host link. Epiphan documents solid blue as USB 3.0 connection active and blinking blue as KVM App connected.
- HID keyboard endpoint: connected.
- HID mouse endpoint: connected.
- HID touch endpoint: connected.
- HID system endpoint: connected.
- UVC camera list included `[KVM2USB 3.0] KVM2USB 3.0`.
- OpenCV captured a `1080x1920` BGR frame from the device.
- With the revised adapter chain, captured frame showed the Wyse firmware screen: `No bootable devices found`.
- HID usage `0x103`, feature report `3`, returned bytes `80 07 38 04 01`, decoded as `1920x1080 active`.
- `get_status()` now reports `resolution: 1920x1080`, `is_signal_active: true`, and `signal_source: touch_feature_3`.
- `hardware_probe.py` now emits HID collection metadata, camera open state, frame statistics when available, and an `effectiveSignal` block that combines HID signal and visible frame evidence.
- When the GUI owns the DirectShow capture device, a separate probe may report `cameraState.opened: false`, `frameStats: null`, and `effectiveSignal.reason: hid_report`; this is expected camera ownership behavior rather than a signal failure.
- DirectShow advertises YUY2-only capture modes from `640x360` through `1920x1200`, with each mode allowing approximately `15` to `60.0002` fps. OpenCV currently opens the KVM2USB through `DSHOW` at `1920x1080`, FOURCC `YUY2`.
- The enhanced probe observed `180` unique captured frames over `3` seconds, measured `60.0 fps`, while the Wyse firmware screen was static.
- A Wyse reboot monitor captured Dell logo, PXE/media check, and `No bootable devices found` states with no HID live-mode resolution change or signal drop; all reported `1920x1080 active`.
- No current read-only SDK path exposes the Wyse-facing EDID. Host WMI EDID queries only show the host displays, UVC exposes capture modes, HID usage `0x103` exposes live mode, and USB MI_00 `KVM2USB 3.0 Config` is present but has Windows problem code `28` without a vendor driver.
- Detailed current pipeline notes are tracked in `VIDEO_PIPELINE.md`.
- Recovered official app, driver, firmware, HID, and config-interface capability
  inventory is tracked in `RECOVERED_CAPABILITIES.md`.
- Official Epiphan firmware, KVM App/config tool, Linux AppImage, and legacy Windows driver packages were downloaded into `.work/epiphan-downloads/` with SHA256 provenance recorded in `.work/epiphan-downloads/manifest.json`.
- Static vendor artifact findings are tracked in `VENDOR_ARTIFACTS.md`. The KVM App WinUSB INF binds `VID_2B77&PID_3661&MI_00` as `KVM2USB 3.0 Configuration` and registers interface GUID `{9f543223-cede-4fa3-b376-a25ce9a30e74}`.
- The firmware `.fw` package contains a validated KVM2USB 3.0 EDID hex dump with manufacturer `EPH`, two valid EDID blocks, and base detailed timings for `1920x1080`, `1280x720`, and `1920x1200` near 60 Hz.
- `epiphan_firmware.py` now parses Cypress FX3 `.img` firmware containers offline, validates the 32-bit data-word checksum, and produces the same `0x1000`-bounded address chunks used by the vendor updater's request `0xA0` write/read-verify path.
- `scripts/inspect_epiphan_firmware.py` now emits offline JSON summaries for Epiphan `.fw` packages, including FX3 records/checksums, FPGA sync offset, package metadata, and firmware-packaged EDID summary/checksum state.
- The official `kvm2usb3.img` has 6 valid FX3 records, 61 transfer chunks, entry `0x4002a114`, checksum `0x19fc6591`, and SHA256 `97c1e45f1af12ff7187275547e690b3105abe21c0f6187b9e99e5cd674fb3f3a`.
- The official `kvm2usb3-sandbox.img` has 5 valid FX3 records, 51 transfer chunks, entry `0x400207a4`, checksum `0x2f1dea7f`, and SHA256 `f744a812c62208812392d9f085bbfe6f3184a3871c339e21487d6ab2e246e07d`.
- The official FPGA payload `kvm2usb3.bin` has SHA256 `0b917e5ba03ff745c5bb7d09aceec29d255bb72e7027a0fd65c49334e5533d8b` and a Xilinx-style sync word `55 99 aa 66` at offset `0x10`. Packet-level FPGA bitstream decoding remains open.
- Detailed firmware/update recovery notes are tracked in `FIRMWARE_UPDATE_RECOVERY.md`.
- Long-term clean-room recovery and recreation strategy is tracked in `OPENKVM2USB_STRATEGY.md`.
- Linux AppImage disassembly confirms HID reports for keyboard (`1`, 9 bytes), mouse (`2`, 5 bytes), touch (`5`, 7 bytes), input size/status feature read (`3`, 6 bytes), touch type feature write (`6`, 2 bytes), and slave re-enumeration feature write (`7`, 2 bytes).
- Linux KVM app disassembly confirms firmware/version display is read with `hid_get_indexed_string()` at USB string index `3`, not through a custom HID report.
- Live SDK verification read USB string index `3` as firmware version `4.0.0.39896`.
- Linux `EpiphanCaptureConfig` disassembly confirms vendor config control transfers through libusb: vendor IN `0xC0`, vendor OUT `0x40`, request `0xB2` for input status, `0xB3` for user modes, `0xE2`/`0xE3` for byte-sized flags, `0xA0` for chunked update/EDID transfer, `0xC4` for one-byte flash-status polling, and `0xC5`/`0xD4` in update/repair flows.
- Static recovery now maps `InputStatusInfo` fields for config request `0xB2`, three 5-byte `UserMode` records for request `0xB3`, and device flag bits `0x02` preserve aspect ratio, `0x04` performance mode, and `0x10` multichannel audio selector for requests `0xE2`/`0xE3`. The SDK includes offline parsers/builders for recovered input-status, flag, and user-mode payloads.
- The `0xA0` path writes chunks capped at `0x1000` bytes, verifies them with read-back, splits the 32-bit address across `wValue`/`wIndex`, and sends a final zero-length transfer after checksum validation. Treat this as update/write machinery until a separate read-only EDID path is confirmed.
- SDK HID output framing now follows the vendor app report IDs for keyboard (`1`), relative mouse (`2`), and touch (`5`), with legacy fallback writes retained. Touch-type (`6`) and re-enumerate (`7`) feature reports are exposed but not live-validated because they are write paths.

Two KVM2USB 3.0 units previously showed USB/HID/UVC enumeration with black captured frames when the target signal path was not negotiating. Interpretation after the latest cable change: the host USB 3.0 link is healthy, the Wyse video is visible through UVC, and the earlier `0x0` status was caused by reading the wrong HID feature report rather than by lack of signal.

Current Wyse video path:

```text
Wyse DisplayPort
-> DP to HDMI adapter
-> HDMI to DVI adapter
-> Epiphan KVM cable
-> KVM2USB
```

Current diagnosis: the DP-to-HDMI plus HDMI-to-DVI chain is producing visible capture. A single active DisplayPort-to-DVI-D conversion is still preferred for long-term reliability and fewer EDID/timing negotiation variables.

Likely adapter/cable choices:

- StarTech `DP2DVIMM6BS`: active DP male to DVI-D male cable. Best physical fit for the Epiphan KVM cable's female DVI end.
- StarTech `DP2DVIS`: active DP male to DVI-D female adapter. Requires a short DVI-D male-to-male cable.
- Cable Matters `102022`: active DP male to DVI-D female adapter. Requires a short DVI-D male-to-male cable.
- Accell UltraAV `B087B-005B-2`: active DP to DVI-D single-link adapter. Confirm connector gender.
- Club 3D `CAC-1010`: active DP to dual-link DVI-D. Confirm connector gender.

Avoid passive DP-to-DVI unless the Wyse port is known to support DP++, and avoid DP-to-HDMI plus HDMI-to-DVI chains.

## UI/UX Review

The GUI now uses the native Qt/platform style instead of forcing Fusion. Toolbar actions use standard platform icons and plain labels instead of emoji-heavy labels. The central no-signal/no-hardware view uses the platform palette and default font.

Offscreen snapshot limitation: PySide6 in the local virtual environment reported a missing Qt font directory during offscreen screenshots, and text rendered as boxes in the offscreen snapshot. This appears to be an offscreen Qt/PySide packaging limitation, not an application stylesheet regression. Do not bundle fonts for this project unless a real packaged GUI environment demonstrates the same problem.

## Safety, Security, And Performance Notes

- Firmware flashing, EDID writing, and raw USB control writes remain deferred high-risk work.
- Installing the official WinUSB config driver for MI_00 is a host-state change and should be explicit. Static analysis indicates it is likely required before read-only config-interface probing can be done through WinUSB/libusb.
- KVM2USB live mode status is currently read from HID usage `0x103`, feature report `3`. The previous usage `0x104`, feature report `0`, path remains a fallback only.
- Feature writes for touch type and slave re-enumeration are recovered and unit-tested offline, but still require a safe target session before live validation.
- Relative mouse movement, button, and wheel reports are recovered and unit-tested offline; live validation should happen only on a sacrificial target or safe firmware screen.
- SDK configuration helpers are offline-only. They parse/build recovered MI_00 payloads but do not bind WinUSB or send raw USB control requests.
- Firmware parser helpers are offline-only. They validate and plan image transfers but do not send update, repair, EDID, or flash commands.
- Linux reverse engineering is valuable and has already recovered more functionality than the stripped Windows binaries. Mac software remains a secondary cross-check unless Linux and Windows disagree.
- Macro coordinates are clamped to normalized `0.0` to `1.0` before HID touch reports are emitted.
- The SDK key map now matches the documented macro key set.
- GUI recording stop controls now signal the SDK recording loop.
- Generated media, SRT files, and session JSON logs are ignored by Git.
- Runtime outputs and per-run mutable state are grouped under `runtime_sessions/<YYYYMMDDTHHMMSSZ>-<correlation-id>/`.
- Broad exception handling still exists in hardware-probing paths. Replace it gradually with narrow exceptions and structured diagnostics as hardware behavior is characterized.
- The repository root `config.json` is treated as a packaged default seed. Per-run `config.json`, `user_presets.json`, logs, captures, recordings, and SRT files are written under the correlated runtime session directory.

## Test Status

Validated locally:

- `python -m compileall -q .`
- `.venv\Scripts\python.exe -m pytest -v`
- `.venv\Scripts\python.exe -m pytest -q` (`34 passed`)
- `python -m json.tool .package-foundry\package.json`
- `python scripts\build_portable.py`
- `python hardware_probe.py --capture`
- `.venv\Scripts\python.exe hardware_probe.py`
- `.venv\Scripts\python.exe hardware_probe.py --include-dshow-options --measure-sec 3`
- `.venv\Scripts\python.exe -c "from epiphan_sdk import EpiphanKVM_SDK; ..."` read-only live status check, including firmware version `4.0.0.39896`
- release script dry-run and release upload path
- portable dependency installer in an extracted path containing spaces
- hardware HID/UVC enumeration and frame capture

Current automated test coverage is useful for SDK processing, macro parsing, packaging scripts, and GUI structure. It does not fully cover live UVC signal quality, HID injection against a target OS, DirectShow camera permission failures, long-running recording behavior, or packaging on a clean Windows machine.

## Phased Strategy

Phase 1: Stabilize source and automation.

- Keep PR `#6` focused on packaging readiness, testability, generated artifact hygiene, and docs.
- Keep `hardware_probe.py` current as the machine-consumable hardware validation entry point.
- Replace print-only macro errors with structured results so agents can consume failures.
- Add a no-hardware CI-safe test mode for GUI and SDK startup.

Phase 2: Validate hardware behavior.

- Capture screenshots from the Wyse 5070 at BIOS, bootloader, Windows lock screen, and desktop states.
- Compare UVC frames to `get_status()` resolution/signal reports.
- Continue refining `hardware_probe.py` as the machine-consumable pipeline baseline.
- Confirm whether UVC/DirectShow formats, frame rates, and FOURCC values change across target resolutions, adapter chains, or USB host ports.
- Validate recovered HID write reports on a safe target session; prefer `sdk.run_macro()` for action sequences.
- After explicit driver approval, build a read-only MI_00 WinUSB/libusb probe for static-confirmed config requests.
- Exercise keyboard, mouse, touch, and hotkey HID paths on a sacrificial target session.
- Measure frame latency, frame rate, and recording stability over 10-minute and 60-minute runs.

Phase 3: Improve operator and agent UX.

- Make the runtime session root configurable for lab automation and packaged installs.
- Add a visible device health panel with UVC, HID, signal, resolution, and recording states.
- Add named macro storage with explicit dry-run/validate support.
- Add structured JSON status and action output for automation.

Phase 4: Package and deployment hardening.

- Test the portable ZIP on a clean Windows 11 system.
- Generate organization-controlled Scoop, Chocolatey, and local Winget metadata from Package Foundry.
- Keep official Winget, Chocolatey Community, Scoop main/extras, and PortableApps publication disabled until explicitly approved.
