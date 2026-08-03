# AgentKVM2USB Handoff

Session date: 2026-08-02

## Current Repository State

- Repository: `SemperSupra/AgentKVM2USB`
- Active branch: `package-foundry/public-deployment-readiness`
- Base branch: `main`
- Open issue: `#5`
- Open draft PR: `#6`
- Latest pushed commits:
  - `5a42e86ebd41253f8b848dec2e0b0dece649ebe9` - `Harden portable release packaging`
  - `042a591a4fb7041d3cb62ee0746193b8d8274bf1` - `Improve hardware validation and UI testability`

## Release State

Release `v0.2.0` has a Windows portable ZIP and matching SHA256 checksum attached.

Current release asset checksum:

```text
360ff91a7c4b76d90b5d115ceea379b4f8c8568e67c54c36f7c37a8ff413a3c1  AgentKVM2USB-v0.2.0-windows-portable.zip
```

Release URL: https://github.com/SemperSupra/AgentKVM2USB/releases/tag/v0.2.0

## Completed This Session

- Added local portable ZIP build and release scripts.
- Added `.package-foundry/package.json`.
- Uploaded release assets to `v0.2.0`.
- Added `PROJECT_STATUS.md`.
- Added `hardware_probe.py` for machine-consumable hardware diagnostics.
- Moved mutable runtime outputs into `runtime_sessions/<YYYYMMDDTHHMMSSZ>-<correlation-id>/`.
- Treat root `config.json` as a default seed only.
- Updated `.gitignore` so runtime sessions, generated captures, recordings, SRTs, and session logs do not show up in Git.
- Fixed GUI menu construction.
- Removed forced Fusion styling and emoji-heavy toolbar labels.
- Added SDK and GUI regression tests.

## Current Validation

Validated:

- `python -m compileall -q .`
- `.venv\Scripts\python.exe -m pytest -v`: 16 passed
- `.venv\Scripts\python.exe -m pip check`: no broken requirements
- `python -m json.tool .package-foundry\package.json`
- `python scripts\build_portable.py`
- `python scripts\release.py --tag v0.2.0`
- Published release assets downloaded and checksum-verified.

## Hardware Findings

Two KVM2USB 3.0 units were tested against a powered-on Wyse 5070.

Observed on both units:

- USB/HID/UVC host link is good.
- LED is blue, which Epiphan documents as normal for an active USB 3.0 host link.
- HID keyboard, mouse, touch, and system endpoints open.
- DirectShow sees `KVM2USB 3.0`.
- OpenCV reads 1920x1080 YUY2 frames.
- Captured frames are black.
- `get_status()` reports `resolution: 0x0` and `is_signal_active: false`.

Current connection path:

```text
Wyse DisplayPort
-> DP to HDMI adapter
-> HDMI cable
-> HDMI to DVI adapter
-> Epiphan KVM cable
-> KVM2USB
```

Leading diagnosis: target video negotiation is failing through the adapter chain. The KVM2USB units themselves appear healthy.

## Adapter Recommendation

Avoid the DP-to-HDMI plus HDMI-to-DVI chain. Use one active DisplayPort-to-DVI conversion.

Best physical fit:

- StarTech `DP2DVIMM6BS`: active DP male to DVI-D male cable, 1080p/1920x1200 at 60 Hz. This should plug directly into the Epiphan KVM cable's female DVI end.

Likely alternatives:

- StarTech `DP2DVIS`: active DP male to DVI-D female adapter. Requires a short DVI-D male-to-male cable.
- Cable Matters `102022`: active DP male to DVI-D female adapter. Requires a short DVI-D male-to-male cable.
- Accell UltraAV `B087B-005B-2`: active DP to DVI-D single-link adapter. Confirm connector gender before buying.
- Club 3D `CAC-1010`: active DP to dual-link DVI-D. More than needed for 1080p; confirm connector gender.

Avoid:

- StarTech `DP2DVI`, because it is passive.
- Passive DP-to-DVI unless the Wyse DP port is known to support DP++.
- DP-to-HDMI plus HDMI-to-DVI adapter chains.
- USB display adapters.

## Next Steps

1. Reboot the host/working machine as needed.
2. Acquire or locate an active DisplayPort-to-DVI-D adapter/cable.
3. Connect the Wyse to the Epiphan KVM cable through a single active DP-to-DVI conversion.
4. Boot the Wyse with video and target USB connected from power-on.
5. Run:

```powershell
python hardware_probe.py --capture
```

6. If still black, try the other Wyse DisplayPort output and reboot again.
7. If still black, use the official Epiphan Capture Config tool to inspect/set user modes/EDID.

## Important Caveats

- Do not commit files under `runtime_sessions/`.
- Do not commit machine-specific runtime `config.json` files.
- Firmware flashing, EDID writing, and raw USB control writes remain high-risk deferred work.
