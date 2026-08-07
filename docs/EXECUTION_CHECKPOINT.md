# Multi-Agent Execution Checkpoint

## Checkpoint identity

- Reviewed UTC date: `2026-08-07`
- Repository: `SemperSupra/AgentKVM2USB`
- Integration branch: `recovery/agentkvm2usb-app-capabilities`
- Verified integration head: `831efef0fb21cf6fd6a77b6b655321201465551c`
- PR #32: merged at `e9f0abd73570bd44e5b00a95e81167b20f4524d1`
- PR #34: merged at `831efef0fb21cf6fd6a77b6b655321201465551c`
- Coordination issue #31: completed
- OOM-recovery hardening issue #35: active until this checkpoint package is reviewed and merged
- Package Foundry Gate 1: merged in `SemperSupra/windows-package-foundry-private` at `6f86487d2b6a4aafb37b1eb82e53f0529fa8d0de`

This is the first repository document an agent should read after an interrupted, compacted, or out-of-memory session. Then read and execute `prompts/OOM_RECOVERY_KICKOFF.md`. Newer GitHub issue comments, finite claims, pull-request heads, and remote branch heads remain authoritative.

A pasted recap, compacted context, terminal scrollback, or previous handoff is evidence only. It must never be treated as the current assignment until live GitHub state confirms it. A resumed agent must not merely repeat a completed report; it must identify the newly assigned lane and either begin that lane or report the exact live blocker.

## Repository authority

- `SemperSupra/windows-package-foundry-private` is the authoritative Package Foundry control repository. Issues #1 and #2, policy, catalog decisions, branches, and review work live there.
- `SemperSupra/windows-package-foundry` is the generated public deployment projection. It is not the issue tracker or control plane for Package Foundry work.
- Package Foundry issue #1 is complete. Issue #2 is the active USBPcap assessment and package lane.

## Completed and integrated

- PR #26 integrated the issue #22 readiness collector and fail-closed no-live framework.
- PR #28 integrated the issue #27 operator dependency workflow.
- PR #32 integrated the multi-agent resume checkpoint and dispatch controls.
- PR #34 corrected Package Foundry authority references and the manual USBPcap installation hold point.
- Wireshark uses exact public WinGet metadata and the shared human-consent UAC helper.
- USBPcap has no direct-installer fallback in AgentKVM2USB.
- Total Phase and Epiphan remain operator-supplied, ignored local artifacts.
- The shared UAC helper must be tracked by Git, unstaged and unmodified, contained by `origin/*`, and unambiguous.
- An Epiphan EXE/MSI must have a current valid Epiphan Authenticode signature and matching provenance thumbprint before elevation.
- Package Foundry Gate 1 prevents `manual_vendor` and `blocked` software from entering either public or private deployment output.

## Current blockers

- The workstation last reported a pending file-rename reboot. An operator must restart Windows manually and verify the state is clear.
- Wireshark/TShark are not yet installed.
- `SemperSupra/windows-package-foundry-private#2` must establish the approved USBPcap disposition and installation path.
- No remote `issue-2-usbpcap` branch or issue #2 pull request existed at the latest review; the prior local-agent response replayed completed issue #1 history instead of starting Lane C.
- USBPcap is not approved or installed.
- Total Phase API is not staged.
- Epiphan application/installer state is not yet satisfied for the issue #22 gate.
- Issue #22 mapping is blocked.
- Issue #14 and PR #13 remain downstream blocked.

The operator has offered to install USBPcap manually if needed. Do not request or perform that installation until Package Foundry issue #2 records the exact approved installer, hash/signing state, Windows 11 behavior, reboot and rollback procedure, and explicitly authorizes the manual path or supplies the reviewed Foundry path.

## Dispatch table

| Agent lane | May start now? | Authoritative item | Branch |
|---|---:|---|---|
| Package Foundry Gate 1 | Complete | `windows-package-foundry-private#1` | merged history |
| USBPcap assessment/package | Yes | `windows-package-foundry-private#2` | fresh `issue-2-usbpcap` |
| Operator prerequisites | Only with operator present | AgentKVM2USB #27 | fresh `issue-27-operator-actions` if needed |
| Readiness/mapping | No | AgentKVM2USB #22 | `issue-22-readiness-completion` after gate |
| Differential experiment | No | AgentKVM2USB #14 | fresh branch after #22 and approval |
| Keyboard PR | No | PR #13 / issue #8 Phase B | existing branch remains frozen |

## Recovery procedure for every agent

1. Treat GitHub as authoritative.
2. Fetch/prune all remotes before interpreting any recap.
3. Inspect every worktree, branch, stash, detached head, untracked file, and ahead/behind state.
4. Preserve unknown work; never reset, clean, auto-stash, rebase shared work, or force-push.
5. Read the assigned issue and every current comment.
6. Verify the remote head, pull-request state, and claim state.
7. Compare the live assignment with any pasted or compacted report. Mark the report `current`, `historical`, or `conflicting`.
8. If the report describes a completed or superseded lane, do not repeat it. State that it is historical and continue with the live assigned lane.
9. Use one issue, one branch, one isolated worktree, one early draft PR for repository changes, and one finite claim.
10. Post `START`, renew with `CHECKPOINT`, finish with `HANDOFF`, and release the claim.
11. Keep raw captures, proprietary vendor files, credentials, and private machine evidence outside Git.

## Operator gate sequence

Run under issue #27:

1. `pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Plan`
2. If reboot is pending, stop. Ask the operator to restart Windows manually. Do not initiate the reboot.
3. After restart, use a fresh claim and rerun `-Plan`.
4. With explicit human consent at the keyboard, install Wireshark through the shared UAC helper.
5. Stage only exact operator-supplied vendor files with HTTPS source-page provenance.
6. Keep `-Install USBPcap` blocked until `windows-package-foundry-private#2` completes and records the approved path.
7. Rerun `-Plan` and record sanitized verification.

## Issue #22 entry gate

Do not claim issue #22 until all are true:

- pending reboot is false;
- Wireshark and TShark are verified;
- approved USBPcap installation is complete and `USBPcapCMD.exe` is verified;
- Epiphan application/driver evidence is verified;
- Total Phase API is staged with hash and provenance;
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