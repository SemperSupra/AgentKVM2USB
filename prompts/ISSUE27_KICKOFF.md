# Issue #27 operator-actions kickoff

Use this from `C:\Users\Mark\Projects\AgentKVM2USB` only while the operator is available to make reboot, consent, vendor-download, and license decisions.

```text
Resume SemperSupra/AgentKVM2USB issue #27 from GitHub.

PR #28 is merged at recovery head 5a398ac529d1e050101a6f078153f3935498d6d2. Do not reuse or modify the historical issue-27-operator-dependencies branch.

Fetch/prune all remotes. Read docs/EXECUTION_CHECKPOINT.md, docs/ACTIVE_WORKSTREAMS.md, AGENTS.md, issue #27 and all comments, docs/ISSUE27_OPERATOR_DEPENDENCY_RUNBOOK.md, and Windows Package Foundry issues #1/#2.

Reconcile every AgentKVM2USB worktree without data loss. Fast-forward only a clean canonical recovery checkout. Run claim preflight. If conflict-free, post a finite START claim for the exact operator slice.

Use a fresh isolated worktree at the current recovery head. Prefer branch issue-27-operator-actions if a repository correction may be required. Do not open an empty PR; open a draft PR immediately if a genuine tracked-file defect is found.

First run:
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Plan

If pending_reboot is true, stop. Report the exact condition and ask the operator to restart Windows manually. Do not initiate or schedule a reboot. Post HANDOFF and release the claim. After restart, begin again under a fresh claim and rerun -Plan.

Only while the operator is physically present and explicitly approves the named action, request Wireshark installation:
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Install Wireshark

Do not directly install USBPcap. Keep it blocked until windows-package-foundry #1 classifies it foundry_eligible and #2 provides an approved reviewed package path.

Stage Total Phase or Epiphan files only when the operator supplies the exact authorized local file, HTTPS source page, and acquisition UTC. Do not automate login, cookies, tokens, entitlement, download, or license acceptance. Do not elevate an Epiphan installer unless the script verifies the current valid Epiphan signature and provenance thumbprint.

After each approved action, rerun -Plan and independently verify paths, versions, drivers, signatures, hashes, provenance, and reboot state.

Do not capture, send target input, recable, or write firmware/FPGA/EDID/flash/persistent state. Do not modify PR #13.

Correct genuine work-package defects only on the fresh branch with deterministic tests and an early draft PR. Finish with exact results, blockers, CHECKPOINT as needed, HANDOFF, claim release, and clean worktrees.
```
