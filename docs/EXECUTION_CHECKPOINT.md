# Multi-Agent Execution Checkpoint

## Checkpoint identity

- Reviewed UTC date: `2026-08-06`
- Repository: `SemperSupra/AgentKVM2USB`
- Integration branch: `recovery/agentkvm2usb-app-capabilities`
- Verified integration head: `5a398ac529d1e050101a6f078153f3935498d6d2`
- Coordination issue: #31
- PR #28: merged
- Post-merge CI run: `31114396438` — successful, 254 tests, no-live PowerShell integration checks, reproducible portable build, no uploaded artifacts.

This file is the first repository document an agent should read after an interrupted or out-of-memory session. GitHub issue comments and finite claims remain authoritative when newer.

## Completed and integrated

- Issue #22 readiness collector and fail-closed framework are integrated from PR #26.
- Issue #27 operator dependency workflow is integrated from PR #28.
- Wireshark uses exact public WinGet metadata and the shared human-consent UAC helper.
- USBPcap has no direct-installer fallback.
- Total Phase and Epiphan remain operator-supplied, ignored local artifacts.
- The shared UAC helper must be tracked, clean, unmodified, origin-backed, and unambiguous.
- An Epiphan EXE/MSI must have a current valid Epiphan Authenticode signature and matching provenance thumbprint before elevation.
- CI validates Python, PowerShell no-live paths, and reproducible portable builds.

## Current blockers

- Workstation reports a pending file-rename reboot until an operator restarts and verifies.
- Wireshark/TShark are not yet installed.
- Windows Package Foundry #1 and #2 are open.
- USBPcap is not approved or installed.
- Total Phase API is not staged.
- Epiphan application/installer state is not yet satisfied for the issue #22 gate.
- Issue #22 mapping is therefore blocked.
- Issue #14 and PR #13 remain downstream blocked.

## Dispatch table

| Agent lane | May start now? | Authoritative item | Branch |
|---|---:|---|---|
| Coordination cleanup | Yes | AgentKVM2USB #31 | `issue-31-multi-agent-resume` |
| Operator prerequisites | Only with operator present | AgentKVM2USB #27 | fresh `issue-27-operator-actions` if needed |
| Package eligibility | Yes | windows-package-foundry #1 | issue-specific Foundry branch |
| USBPcap research/package | Bounded work yes; publish no until #1 | windows-package-foundry #2 | issue-specific Foundry branch |
| Readiness/mapping | No | AgentKVM2USB #22 | `issue-22-readiness-completion` after gate |
| Differential experiment | No | AgentKVM2USB #14 | fresh branch after #22 and approval |
| Keyboard PR | No | PR #13 / issue #8 Phase B | existing branch remains frozen |

## Recovery procedure for every agent

1. Treat GitHub as authoritative.
2. Fetch/prune all remotes.
3. Inspect every worktree, branch, stash, detached head, untracked file, and ahead/behind state.
4. Preserve unknown work; never use destructive cleanup.
5. Read the assigned issue and all comments.
6. Verify the remote head and claim state.
7. Use one issue, one branch, one isolated worktree, one draft PR for repository changes, and one finite claim.
8. Post `START`, renew with `CHECKPOINT`, finish with `HANDOFF`, and release the claim.
9. Keep raw captures, proprietary vendor files, credentials, and private machine evidence outside Git.

## Operator gate sequence

Run under issue #27:

1. `pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Plan`
2. If reboot is pending, stop. Ask the operator to restart Windows manually. Do not initiate the reboot.
3. After restart, use a fresh claim and rerun `-Plan`.
4. With explicit human consent at the keyboard:
   `pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Install Wireshark`
5. Stage only exact operator-supplied vendor files with HTTPS source-page provenance.
6. Keep `-Install USBPcap` blocked until Foundry #1/#2 complete.
7. Rerun `-Plan` and record sanitized verification.

## Issue #22 entry gate

Do not claim issue #22 until all are true:

- pending reboot is false;
- Wireshark and TShark are verified;
- approved USBPcap installation is complete and `USBPcapCMD.exe` is verified;
- Epiphan application/driver evidence is verified;
- Total Phase API is staged with hash/provenance;
- no conflicting claim exists.

Issue #22 may then perform read-only interface enumeration, positive root-hub mapping, topology evidence, and no-live preflight. It may not capture or send target input.

## Non-negotiable boundaries

No agent may infer permission to:

- automate UAC or suppress the human consent step;
- automate vendor login, cookies, tokens, entitlements, or license acceptance;
- use an unapproved package or direct USBPcap installer;
- reboot automatically;
- start capture or send target input;
- recable;
- write firmware, FPGA, EDID, flash, or other persistent device state;
- modify PR #13 outside its later target-receipt gate.
