# AgentKVM2USB Backlog

This file tracks actionable work. Completed investigation history and detailed evidence belong in `PROJECT_STATUS.md`, the capability/strategy documents, GitHub issues, and merged pull requests.

Current multi-agent ownership and sequencing are authoritative in `docs/ACTIVE_WORKSTREAMS.md`.

## Active critical path

1. [ ] **Issue #27 / PR #28 — Operator dependency workflow**
   - run full local Windows validation;
   - verify `-Plan` and every `-WhatIf` path are non-privileged and fail closed;
   - verify trusted discovery of `SupraCraft/minecraft-infra/scripts/local/Invoke-Elevated.ps1`;
   - review and merge PR #28 after validation.

2. [ ] **Windows Package Foundry #1 — Eligibility policy**
   - implement `existing_winget`, `foundry_eligible`, `manual_vendor`, and `blocked` dispositions;
   - exclude authenticated, personalized, expiring, and license-incompatible artifacts from deployment exports.

3. [ ] **Windows Package Foundry #2 — USBPcap package assessment**
   - establish Windows 11 support, signing, provenance, unattended behavior, reboot behavior, uninstall, and rollback;
   - publish an approved package only if the eligibility and safety gates pass.

4. [ ] **Issue #27 — Operator dependency actions**
   - install exact public WinGet package `WiresharkFoundation.Wireshark` through the shared human-gated UAC helper;
   - install USBPcap only through the approved Package Foundry path;
   - stage authorized Total Phase files beneath ignored `.work/vendor/totalphase/`;
   - stage and, when explicitly approved, run the exact authorized Epiphan installer beneath ignored `.work/vendor/epiphan/`;
   - verify applications, tools, drivers, hashes, signatures, and any post-reboot state.

5. [ ] **Issue #22 — Readiness completion and USBPcap mapping**
   - start on a fresh `issue-22-readiness-completion` branch after the dependency entry gate passes;
   - enumerate USBPcap interfaces without capture;
   - positively map the exact KVM2USB device and USB topology to the selected USBPcap root hub;
   - record physical topology, Beagle placement, target identity, and harmless target state;
   - obtain no-live `preflight` result `ok: true` with `live_disabled: true`;
   - generate the experiment manifest without capture or target input.

6. [ ] **Issue #14 — Authorized official-app differential experiment**
   - create a fresh experiment-specific authorization with exact target, interfaces, allowed input, output root, issued/expiry UTC, stop conditions, and forbidden actions;
   - perform the bounded synchronized experiment;
   - preserve raw evidence outside Git and publish only sanitized findings.

7. [ ] **PR #13 / issue #8 Phase B — Keyboard target receipt**
   - keep the branch frozen until issue #14 evidence is available;
   - prove representative keyboard receipt at the target;
   - resolve the missing target-side HID forwarding/activation behavior;
   - update and integrate the keyboard work only after the evidence gate passes.

8. [ ] **Issue #8 Phases C–E — One-KVM pointer completion and multi-device identity**
   - relative mouse semantics and target receipt;
   - pen/touch semantics and target receipt;
   - stable physical grouping of HID, UVC, and MI_00;
   - persistent KVM IDs independent of camera indices;
   - no-mixing validation and isolated per-device sessions;
   - two-KVM concurrency and reconnect/soak testing.

9. [ ] **Issue #12 — Multi-target control plane**
   - one supervised worker per physical KVM;
   - `TargetBundle` registry;
   - target-addressed API;
   - per-target lease, emergency stop, and evidence correlation.

10. [ ] **AgentWebCam #3 — General media and controller-side speech**
    - stable camera, microphone, and speaker identities;
    - media workers and local API;
    - target/media association;
    - voice notes and STT;
    - TTS feedback and safe voice-command interpretation.

11. [ ] **Issue #24 — Controlled-target audio**
    - characterize any real KVM2USB audio stream;
    - design external USB audio fallback;
    - implement target-associated capture/playback/injection only after privacy and routing gates are defined.

## Work that may proceed in parallel

- [ ] Local validation and review of PR #28.
- [ ] Windows Package Foundry #1 and #2 in the separate repository.
- [ ] Offline-only parser, replay, schema, and documentation work that does not alter the active device or overlap an issued claim.
- [ ] Static FPGA bitstream analysis using existing non-proprietary tooling and ignored evidence.
- [ ] UVC/DirectShow capability comparison using already recorded sanitized data.

Every parallel slice still requires its own issue, branch, worktree, draft PR, and finite claim.

## Blocked until the critical path advances

- [ ] **MI_00 official-tool protocol confirmation** — requires the approved capture path and issue #14 authorization.
- [ ] **Harmless HID injection validation** — requires target-side forwarding activation and an explicit safe target gate.
- [ ] **Wyse BIOS automation mapping** — requires confirmed HID target receipt.
- [ ] **Multi-KVM dashboard** — requires stable physical grouping and target-addressed routing.
- [ ] **Vision-conditional macros and OCR actions** — require a reliable single-target control loop and authorization model.
- [ ] **Voice commands that can cause HID actions** — require explicit target selection, confidence refusal, confirmation, lease enforcement, and emergency stop.

## Open protocol and diagnostics work

- [ ] Confirm whether UVC/DirectShow advertised modes change across target resolutions, adapter chains, host ports, and multiple KVM2USB units.
- [ ] Complete packet-level FPGA bitstream decoding and validate register/CRC/frame interpretations against authoritative references.
- [ ] Extract raw VGA/DVI timing diagnostics where the hardware exposes them.
- [ ] Continue structured hardware-probe improvements without adding implicit live actions.
- [ ] Define persistent non-secret profile storage outside the repository.
- [ ] Validate the portable Windows ZIP on a clean Windows 11 host.

## Multi-device, media, audio, and speech bring-up

Canonical roadmap: issue #23 and `docs/MULTI_DEVICE_MEDIA_SPEECH_ROADMAP.md`.

### Stable KVM identity — issue #8 Phase E

- [ ] Group MI_00, MI_01/UVC, MI_03/HID collections by serial, PnP ContainerId, parent composite device, location path, controller, hub, and port.
- [ ] Reject ambiguous, partial, duplicate, inaccessible, or cross-device collection sets.
- [ ] Maintain independent handles, locks, release-all behavior, runtime roots, and reconnect state.
- [ ] Record topology evidence for USB bandwidth policy.

### Multi-target orchestration — issue #12

- [ ] Supervise one worker with exclusive UVC/HID ownership per physical KVM.
- [ ] Associate target, KVM, auxiliary cameras, audio devices, evidence roots, lease, and authorization.
- [ ] Replace implicit single-device routes with `/targets/{target_id}/...`.
- [ ] Correlate actions, screenshots/video, auxiliary media, voice notes, and results by UTC and correlation ID.

### Media and speech — AgentWebCam #3

- [ ] Stable media-device IDs rather than transient indices.
- [ ] Concurrent snapshot, video, timelapse, microphone recording, stop, health, and playback operations.
- [ ] Push-to-talk voice notes with transcript, confidence, provider provenance, target, and UTC.
- [ ] Explicit TTS speaker routing and cancellation.
- [ ] Separate note and command modes; prevent TTS-to-STT command feedback.

### Controlled-target audio — issue #24

- [ ] Determine whether KVM2USB exposes a usable audio capture/playback stream; do not infer this from the recovered selector flag.
- [ ] Provide target-associated external USB audio adapters when the native path is absent or unsuitable.
- [ ] Add capability, capture, playback, injection, stop/mute, health, latency, and correlation APIs.
- [ ] Validate synchronization, clipping, feedback, hidden-capture prevention, retention, and operator indicators.

### Scale and reliability

- [ ] Controller-aware full-rate, reduced-rate, and snapshot-only policies.
- [ ] Two-to-four target dashboard after stable IDs and target-addressed routing pass.
- [ ] Long-duration reconnect/soak testing with resource quotas and evidence-retention limits.

## High-risk deferred work

These items remain intentionally blocked behind separate design, authorization, recovery, and rollback gates:

- [ ] Custom firmware flasher.
- [ ] Custom firmware builder/signing/checksum pipeline.
- [ ] Custom FPGA builder and compatibility validation.
- [ ] Raw EDID injector.
- [ ] Unknown vendor OUT transfers or persistent device writes.

No active issue may absorb these tasks implicitly.

## Documentation index

- Current execution and lane ownership: `docs/ACTIVE_WORKSTREAMS.md`
- Current hardware and investigation history: `PROJECT_STATUS.md`
- Multi-device/media/speech roadmap: `docs/MULTI_DEVICE_MEDIA_SPEECH_ROADMAP.md`
- Issue #27 operator workflow: `docs/ISSUE27_OPERATOR_DEPENDENCY_RUNBOOK.md`
- Issue #22 readiness/mapping workflow: `docs/ISSUE22_OPERATOR_RUNBOOK.md`
- Input strategy: `docs/INPUT_PATH_STRATEGY.md`
- Backend/persona architecture: `docs/BACKEND_AND_TARGET_PERSONA_EXTENSIBILITY.md`
- Runtime/reverse-engineering handoff: `docs/ISSUE14_RUNTIME_HANDOFF.md`
