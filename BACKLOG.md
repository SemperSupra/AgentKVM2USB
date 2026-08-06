# AgentKVM2USB Backlog

This file contains actionable work only. Historical evidence belongs in `PROJECT_STATUS.md`, merged pull requests, and issue timelines.

Authoritative current state: `docs/EXECUTION_CHECKPOINT.md` and `docs/ACTIVE_WORKSTREAMS.md`.

## Completed foundation

- [x] PR #26 merged the issue #22 readiness collector and fail-closed no-live framework.
- [x] PR #28 merged the issue #27 operator dependency workflow at `5a398ac`.
- [x] The shared UAC helper trust boundary, HTTPS provenance, and Epiphan signature binding are implemented.
- [x] GitHub Actions CI is active; post-merge run `31114396438` passed 254 tests and reproducible-build verification.

## Current critical path

1. [ ] **Issue #31 — Post-merge coordination reconciliation**
   - publish the execution checkpoint and lane-specific prompts;
   - remove stale draft/unvalidated PR #28 language;
   - add documentation drift guards;
   - merge after hosted CI.

2. [ ] **Issue #27 — Operator prerequisites**
   - run `-Plan`;
   - when reported, perform an operator-initiated restart and verify reboot state is clear;
   - install exact `WiresharkFoundation.Wireshark` through the shared human-gated UAC helper;
   - stage authorized Total Phase API files under ignored `.work/vendor/totalphase/`;
   - stage and signature-verify the authorized Epiphan installer under ignored `.work/vendor/epiphan/`;
   - never install USBPcap by an ad hoc path.

3. [ ] **Windows Package Foundry #1 — Eligibility policy**
   - implement `existing_winget`, `foundry_eligible`, `manual_vendor`, and `blocked`;
   - exclude authenticated, personalized, expiring, and license-incompatible artifacts;
   - record AgentKVM2USB dependencies as worked examples.

4. [ ] **Windows Package Foundry #2 — USBPcap**
   - complete provenance, signing, Windows 11, silent-install, detection, reboot, uninstall, and rollback analysis;
   - validate first on a disposable or recoverable Windows environment;
   - publish only after #1 classifies it `foundry_eligible`.

5. [ ] **Issue #22 — Readiness completion**
   - begin only after every dependency entry gate passes;
   - use fresh branch `issue-22-readiness-completion`;
   - enumerate USBPcap interfaces without capture;
   - prove the exact KVM2USB-to-root-hub mapping;
   - record physical topology and harmless target state;
   - obtain no-live `ok: true` with `live_disabled: true`;
   - generate the experiment manifest.

6. [ ] **Issue #14 — Official-app differential**
   - create a new expiring authorization;
   - run the bounded synchronized host/target experiment;
   - keep raw evidence outside Git;
   - identify the first downstream HID divergence.

7. [ ] **PR #13 / issue #8 Phase B**
   - remain frozen until issue #14 evidence exists;
   - prove target receipt and release-all;
   - integrate only after the hardware gate passes.

## Work allowed in parallel

- [ ] Windows Package Foundry #1.
- [ ] Bounded research for Windows Package Foundry #2, subordinate to #1.
- [ ] Issue #27 operator actions when the operator is present.
- [ ] Separately issued offline parser, replay, schema, or documentation work with no hardware or branch overlap.

Each coding/documentation lane requires its own issue, branch, isolated worktree, draft PR, and finite claim. Operator-only execution still requires a finite claim and clean handoff.

## Next capability increments

- [ ] Issue #8 Phase C: generic relative mouse.
- [ ] Issue #8 Phase D: distinct pen/touch semantics.
- [ ] Issue #8 Phase E: stable physical grouping, reconnect, and two-KVM no-mixing validation.
- [ ] Issue #12: isolated workers, `TargetBundle`, target-addressed API, leases, and emergency stop.
- [ ] AgentWebCam #3: stable media IDs, camera/audio workers, voice notes, STT, and TTS.
- [ ] Issue #24: explicit controlled-target audio capability and adapter fallback.
- [ ] Epic #23: 2–4 target scale, bandwidth policy, dashboard, quotas, and soak tests.

## Deferred high-risk work

No current issue may absorb these implicitly:

- [ ] firmware flasher or updater;
- [ ] firmware/FPGA build or signing pipeline;
- [ ] raw EDID injection;
- [ ] unknown vendor OUT transfers;
- [ ] persistent device-state changes without dedicated authorization and rollback.

## Documentation index

- Resume checkpoint: `docs/EXECUTION_CHECKPOINT.md`
- Active lanes: `docs/ACTIVE_WORKSTREAMS.md`
- Agent rules: `AGENTS.md`
- Issue #27 runbook: `docs/ISSUE27_OPERATOR_DEPENDENCY_RUNBOOK.md`
- Issue #27 kickoff: `prompts/ISSUE27_KICKOFF.md`
- Issue #22 runbook: `docs/ISSUE22_OPERATOR_RUNBOOK.md`
- Issue #22 kickoff: `prompts/ISSUE22_KICKOFF.md`
- Long-term roadmap: `docs/MULTI_DEVICE_MEDIA_SPEECH_ROADMAP.md`
- Historical hardware evidence: `PROJECT_STATUS.md`
