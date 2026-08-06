# Issue #22 readiness-completion kickoff

Use this only after issue #27 and Windows Package Foundry satisfy every entry-gate item.

```text
Resume SemperSupra/AgentKVM2USB issue #22 from GitHub.

Fetch/prune all remotes. Read docs/EXECUTION_CHECKPOINT.md, docs/ACTIVE_WORKSTREAMS.md, AGENTS.md, issues #22, #27, and #14 with all comments, Windows Package Foundry #1/#2, docs/ISSUE22_OPERATOR_RUNBOOK.md, and prompts/ISSUE22_WORKSTATION_CAPTURE_DEPS.md.

Verify the entry gate before claiming:
- pending reboot false after operator restart and verification;
- Wireshark and TShark verified;
- approved USBPcap path complete and USBPcapCMD.exe verified;
- Epiphan application/driver evidence verified;
- Total Phase API staged under ignored .work/vendor/totalphase with provenance;
- no conflicting finite claim.

If any item is missing, do not claim #22 and do not improvise acquisition. Report the exact blocker to issue #27 or the relevant Package Foundry issue.

The old issue-22-workstation-capture-deps branch and PR #26 are merged history. Reconcile every worktree without data loss, fast-forward only the clean canonical recovery checkout, and create a fresh isolated issue-22-readiness-completion branch from the current integration head. Open an early draft PR.

Post a finite START claim. Run issue #27 -Plan and the issue #22 collector. Enumerate USBPcap interfaces read-only; do not start capture. Prove the exact KVM2USB PnP/container/interface/controller/hub/port mapping to the selected USBPcap root hub. Record physical topology, Beagle identity/placement, target identity, and harmless target state. Run no-live preflight and build-manifest until all verified gates pass with ok: true and live_disabled: true.

Do not acquire dependencies, capture, send target input, recable, reboot automatically, perform vendor OUT or persistent writes, or modify PR #13.

Finish with exact evidence references, CHECKPOINT as needed, HANDOFF, claim release, and clean worktrees.
```
