# AgentKVM2USB Backlog

This file contains actionable work only. Historical evidence belongs in `PROJECT_STATUS.md`, merged pull requests, and issue timelines.

Authoritative current state: `docs/EXECUTION_CHECKPOINT.md` and `docs/ACTIVE_WORKSTREAMS.md`.

## Completed foundation

- [x] PR #26 merged the issue #22 readiness collector and fail-closed no-live framework.
- [x] PR #28 merged the issue #27 operator dependency workflow.
- [x] PR #32 merged the multi-agent execution checkpoint at `e9f0abd73570bd44e5b00a95e81167b20f4524d1`; issue #31 is complete.
- [x] The shared UAC helper trust boundary, HTTPS provenance, and Epiphan signature binding are implemented.
- [x] Package Foundry Gate 1 merged in `SemperSupra/windows-package-foundry-private` at `6f86487d2b6a4aafb37b1eb82e53f0529fa8d0de`.
- [x] Gate 1 excludes `manual_vendor` and `blocked` candidates from both public and private deployment output.
- [x] `SemperSupra/windows-package-foundry` is documented as the generated public projection; issue work belongs in `windows-package-foundry-private`.

## Current critical path

1. [ ] **Windows Package Foundry private #2 — USBPcap**
   - work in `SemperSupra/windows-package-foundry-private`;
   - verify the current authoritative upstream release and whether an adequate public WinGet package exists;
   - establish immutable provenance, SHA-256, Authenticode and driver-signing state;
   - establish supported Windows 11 install, detection, reinstall/upgrade, reboot, uninstall, and rollback behavior;
   - validate first on a disposable or recoverable Windows environment;
   - classify USBPcap `foundry_eligible`, `manual_vendor`, or `blocked` from evidence;
   - publish a package only when the Gate 1 rules and disposable-host evidence pass;
   - approve a manual-install exception only when the exact installer, verification, and rollback procedure are reviewed.

2. [ ] **Issue #27 — Operator prerequisites**
   - run `-Plan`;
   - when reported, perform an operator-initiated restart and verify reboot state is clear;
   - install exact `WiresharkFoundation.Wireshark` through the shared human-gated UAC helper;
   - stage authorized Total Phase API files under ignored `.work/vendor/totalphase/`;
   - stage and signature-verify the authorized Epiphan installer under ignored `.work/vendor/epiphan/`;
   - do not install USBPcap until private Foundry issue #2 approves the exact path.

3. [ ] **Issue #22 — Readiness completion**
   - begin only after every dependency entry gate passes;
   - use fresh branch `issue-22-readiness-completion`;
   - enumerate USBPcap interfaces without capture;
   - prove the exact KVM2USB-to-root-hub mapping;
   - record physical topology and harmless target state;
   - obtain no-live `ok: true` with `live_disabled: true`;
   - generate the experiment manifest.

4. [ ] **Issue #14 — Official-app differential**
   - create a new expiring authorization;
   - run the bounded synchronized host/target experiment;
   - keep raw evidence outside Git;
   - identify the first downstream HID divergence.

5. [ ] **PR #13 / issue #8 Phase B**
   - remain frozen until issue #14 evidence exists;
   - prove target receipt and release-all;
   - integrate only after the hardware gate passes.

## Work allowed in parallel

- [ ] Private Foundry issue #2 research and implementation under its own claim.
- [ ] Issue #27 operator actions when the operator is physically present.
- [ ] Separately issued offline parser, replay, schema, or documentation work with no hardware or branch overlap.

Each coding or documentation lane requires its own issue, branch, isolated worktree, early draft PR, and finite claim. Operator-only execution still requires a finite claim and clean handoff.

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
- Multi-agent dispatcher: `prompts/MULTI_AGENT_DISPATCH.md`
- Issue #27 runbook: `docs/ISSUE27_OPERATOR_DEPENDENCY_RUNBOOK.md`
- Issue #27 kickoff: `prompts/ISSUE27_KICKOFF.md`
- Issue #22 runbook: `docs/ISSUE22_OPERATOR_RUNBOOK.md`
- Issue #22 kickoff: `prompts/ISSUE22_KICKOFF.md`
- Long-term roadmap: `docs/MULTI_DEVICE_MEDIA_SPEECH_ROADMAP.md`
- Historical hardware evidence: `PROJECT_STATUS.md`
