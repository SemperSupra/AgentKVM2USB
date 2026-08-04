# AgentKVM2USB Project Status

Last reviewed: 2026-08-04T02:00:00Z

> This is a concise snapshot. The current state of issues, pull requests, branches,
> and their head SHAs on GitHub supersedes this document whenever they differ.
> Agents and humans must read the canonical issues and linked PRs for authoritative
> scope, decisions, blockers, and validation.

## Repository State

- Integration branch: `main` @ `15223d035d0dfc4e0aa97e1c396103c160a928c2`.
- Remote GitHub repository is the authoritative coordination surface; see
  `docs/REMOTE_AGENT_COORDINATION.md` and `AGENTS.md`.
- No GitHub Actions workflow exists in this repository (a path-filtered
  governance CI workflow is a recommended follow-up).

## Active Canonical Workstreams

| Issue | Title | Branch | PR | Head SHA | State | Dependencies | Next bounded action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| #8 | Make the input path profile-driven across keyboard, relative mouse, pen, and touch | `issue-8-phase-b-keyboard` | #13 (draft) | `4cce290188705413d3e88686f4443cdda53db16c` | Phase B keyboard correctness implemented; awaiting integration review | Hardware HID/USB validation, #16 coordination protocol | Continue target-side HID forwarding/activation investigation; keep PR #13 isolated |
| #14 | Recover the downstream HID forwarding and activation path | `issue-14-container-re-toolchain` | #15 (ready for review) | `6837a7a48fe20a9a154c320f70a44ff037a83632` | Container-first RE toolchain implemented and ready for integration review; **target-side HID forwarding remains unresolved** | #16 coordination protocol; Total Phase Linux Beagle API (operational follow-up) | Maintain PR #15 ready; unresolved target-side DATA/forwarding requires further hardware investigation |
| #16 | Establish repository-native agent coordination and project metadata governance | `issue-16-agent-coordination-governance` | #17 (draft, ready for review) | `35efdff9d013ab84280bb020fa0d65b5fcbf15b` (validated implementation head; see PR #17 for the authoritative current head) | Governance corrections complete; **PR #17 is in final documentation validation/review** (claim/lease protocol, status correction, capability metadata correction all implemented) | None | Await remote integration review of PR #17 |

Issue #5 / PR #6 (Windows Package Foundry public deployment readiness) are
**not** active work; the active repository work is tracked by issues #8, #14,
and #16 and their PRs #13, #15, and #17 above.

## Current Artifact Model

The public release artifact is a portable Windows ZIP, not a frozen executable.
This keeps Python, PySide6, OpenCV, `hidapi`, `pygrabber`, DirectShow, UVC, and
HID behavior visible and debuggable for humans and automation.

Release `v0.2.0` has these install assets:

- `AgentKVM2USB-v0.2.0-windows-portable.zip`
- `AgentKVM2USB-v0.2.0-windows-portable.zip.sha256`

Current SHA256:

```text
360ff91a7c4b76d90b5d115ceea379b4f8c8568e67c54c36f7c37a8ff413a3c1  AgentKVM2USB-v0.2.0-windows-portable.zip
```

## Hardware Validation

Hardware validation was run on 2026-08-02 with the Epiphan KVM2USB connected to
a powered-on Wyse 5070.

Observed:

- Device LED: blue, which is expected for the KVM2USB 3.0 USB 3.0 host link.
- HID keyboard, mouse, touch, and system endpoints: connected.
- UVC camera list included `[KVM2USB 3.0] KVM2USB 3.0`.
- OpenCV captured a `1080x1920` BGR frame from the device.
- Later captures with a revised adapter chain showed the Wyse firmware screen
  and `get_status()` reporting `1920x1080` active; HID usage `0x103` feature
  report `3` returned bytes decoded as `1920x1080 active`.
- **Target-side HID forwarding is unresolved**: an inline Beagle-12 capture
  recorded `IN` polls and `NAK` handshakes on the target-facing interrupt
  endpoint with `0` HID `DATA` packets. This is the core blocker tracked by
  issue #14 and is not yet resolved.

Current Wyse video path:

```text
Wyse DisplayPort
-> DP to HDMI adapter
-> HDMI to DVI adapter
-> Epiphan KVM cable
-> KVM2USB
```

Leading diagnosis: the target video signal is not negotiating through this
multi-adapter chain. Prefer a single active DisplayPort-to-DVI-D conversion.

Likely adapter/cable choices:

- StarTech `DP2DVIMM6BS`: active DP male to DVI-D male cable.
- StarTech `DP2DVIS`: active DP male to DVI-D female adapter.
- Cable Matters `102022`: active DP male to DVI-D female adapter.
- Accell UltraAV `B087B-005B-2`: active DP to DVI-D single-link adapter.
- Club 3D `CAC-1010`: active DP to dual-link DVI-D.

Avoid passive DP-to-DVI unless the Wyse port is known to support DP++, and avoid
DP-to-HDMI plus HDMI-to-DVI chains.

## Safety, Security, And Performance Notes

- Firmware flashing, EDID writing, and raw USB control writes remain deferred
  high-risk work requiring explicit human approval and a hardware-safe plan.
- Macro coordinates are clamped to normalized `0.0` to `1.0` before HID touch
  reports are emitted.
- Generated media, SRT files, and session JSON logs are ignored by Git.
- Runtime outputs and per-run mutable state are grouped under
  `runtime_sessions/<YYYYMMDDTHHMMSSZ>-<correlation-id>/`.
- The repository root `config.json` is a packaged default seed; per-run
  `config.json`, `user_presets.json`, logs, captures, recordings, and SRT files
  are written under the correlated runtime session directory.
- Public repositories contain sanitized facts, independently written code,
  manifests, hashes, references, and conclusions; restricted evidence belongs in
  an approved private evidence repository.

## Test Status

Validated locally:

- `python -m compileall -q .`
- `.venv\Scripts\python.exe -m pytest -q`
- `python -m json.tool .package-foundry\package.json`
- `python scripts\build_portable.py`
- `python hardware_probe.py --capture`
- release script dry-run and release upload path
- portable dependency installer in an extracted path containing spaces
- hardware HID/UVC enumeration and frame capture

Current automated test coverage is useful for SDK processing, macro parsing,
packaging scripts, and GUI structure. It does not fully cover live UVC signal
quality, HID injection against a target OS, DirectShow camera permission
failures, long-running recording behavior, or packaging on a clean Windows
machine.
