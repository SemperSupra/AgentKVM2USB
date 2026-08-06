# Issue #22 minimal kickoff

Use this only after issue #27 and Windows Package Foundry have made the required dependencies available.

```text
Resume SemperSupra/AgentKVM2USB issue #22 from GitHub.

Fetch current state and read issues #22, #27, and #14; Windows Package Foundry #1/#2; AGENTS.md; docs/ACTIVE_WORKSTREAMS.md; docs/ISSUE22_OPERATOR_RUNBOOK.md; and prompts/ISSUE22_WORKSTATION_CAPTURE_DEPS.md.

Verify the issue #22 entry gate. If Wireshark/TShark, an approved USBPcap installation, Epiphan application/driver evidence, Total Phase API staging, or post-reboot verification is missing, do not claim #22. Report the blocker back to issue #27 or Package Foundry.

The original issue-22-workstation-capture-deps branch and PR #26 are merged history. After lossless worktree reconciliation and claim preflight, create or reuse a fresh issue-22-readiness-completion branch and isolated worktree from the current recovery integration head. Open an early draft PR.

Post a four-hour START claim, execute the canonical prompt, prove the USBPcap interface-to-KVM2USB root-hub mapping, record topology and harmless target state, and run no-live preflight/build-manifest until the verified gates pass.

Do not acquire dependencies, capture, send input, recable, reboot automatically, modify PR #13, or perform persistent device writes. Finish with CHECKPOINT, HANDOFF, claim release, and a clean worktree.
```
