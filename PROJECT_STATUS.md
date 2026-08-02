# AgentKVM2USB Project Status

Last reviewed: 2026-08-02

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
- UVC camera list included `[KVM2USB 3.0] KVM2USB 3.0` at camera index 3.
- OpenCV captured a `1080x1920` BGR frame from the device.
- Captured frame was black.
- `get_status()` reported `resolution: 0x0` and `is_signal_active: false`.

Two KVM2USB 3.0 units showed the same result. Interpretation: USB/HID/UVC enumeration works on the host. The blue LED supports that the host USB 3.0 link is healthy. The target video signal path still needs follow-up because the camera stream is available but no active signal is reported by the system endpoint and the captured frame is black.

Current Wyse video path:

```text
Wyse DisplayPort
-> DP to HDMI adapter
-> HDMI cable
-> HDMI to DVI adapter
-> Epiphan KVM cable
-> KVM2USB
```

Leading diagnosis: the target video signal is not negotiating through this multi-adapter chain. Prefer a single active DisplayPort-to-DVI-D conversion.

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
- `python -m json.tool .package-foundry\package.json`
- `python scripts\build_portable.py`
- `python hardware_probe.py --capture`
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
