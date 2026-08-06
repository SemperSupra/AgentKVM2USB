# Active Workstreams and Multi-Agent Boundaries

This is the authoritative execution map for AgentKVM2USB. Newer GitHub issue comments, finite claims, and remote branch heads override older notes.

## Current integration state

- Integration branch: `recovery/agentkvm2usb-app-capabilities`
- Verified integration head: `e9f0abd73570bd44e5b00a95e81167b20f4524d1`
- PR #28 and PR #32 are merged history; their implementation branches must not be reused.
- Coordination issue #31 is complete.
- Package Foundry Gate 1 is merged in the private control repo at `6f86487d2b6a4aafb37b1eb82e53f0529fa8d0de`.
- Do not develop directly on the integration branch.

Read `docs/EXECUTION_CHECKPOINT.md` before accepting or dispatching work.

## Package Foundry authority

- Authoritative control repository: `SemperSupra/windows-package-foundry-private`
- Generated public deployment projection: `SemperSupra/windows-package-foundry`

Issues #1 and #2, package eligibility decisions, private catalog work, implementation branches, and pull requests belong to the private control repository. Do not dispatch issue work to the generated public projection.

## Critical path

```text
Package Foundry Gate 1 merged
              |
              +--> windows-package-foundry-private #2 USBPcap assessment/package
              |
PR #28 merged + operator present
              +--> reboot clearance + Wireshark + vendor staging
                                      |
                                      v
AgentKVM2USB #22 readiness + USBPcap mapping
              |
              v
AgentKVM2USB #14 separately authorized differential experiment
              |
              v
PR #13 / issue #8 Phase B target receipt
              |
              v
issue #8 Phases C-E -> issue #12 -> AgentWebCam #3 -> issue #24
```

No later lane may bypass an earlier entry gate.

## Parallel lanes

### Lane A — Issue #27 operator prerequisites

**Status:** implementation merged; operator and external gates remain.

Use `prompts/ISSUE27_KICKOFF.md`. Do not reuse `issue-27-operator-dependencies`.

A fresh execution slice may use `issue-27-operator-actions` from the current integration head. If no repository change is needed, the branch remains an execution anchor and no empty PR is required. Open a draft PR immediately if a genuine script, test, or documentation defect is found.

Owns:

- read-only `-Plan` inventory;
- reporting a pending reboot without initiating it;
- human-approved Wireshark installation through the trusted shared UAC helper;
- local staging of operator-supplied Total Phase and Epiphan artifacts;
- independent post-action verification;
- exact blocker reporting for USBPcap.

Does not own:

- USBPcap packaging or installer approval;
- vendor login or license acceptance automation;
- capture, target input, recabling, automatic reboot, or persistent device writes;
- issue #22 mapping;
- issue #14 experiment authorization;
- PR #13 changes.

### Lane B — Windows Package Foundry #1

**Repository:** `SemperSupra/windows-package-foundry-private`

**Status:** complete and merged at `6f86487d2b6a4aafb37b1eb82e53f0529fa8d0de`.

Gate 1 defines `existing_winget`, `foundry_eligible`, `manual_vendor`, and `blocked`, and excludes prohibited software from public and private deployment output. Do not reopen or duplicate it without new evidence and a dedicated issue.

### Lane C — Windows Package Foundry #2

**Repository:** `SemperSupra/windows-package-foundry-private`

**Status:** next coding/research lane; may start with a fresh finite claim.

Owns USBPcap provenance, current upstream version, installer hash, Authenticode and driver-signing state, Windows 11 support, exact supported install/uninstall behavior, detection, reboot handling, rollback, disposable-host validation, eligibility reclassification, and the reviewed consumer path.

The operator has offered to install USBPcap manually. Lane C must first determine whether that is the approved exception and publish the exact reviewed procedure. Do not ask the operator to install it before those gates are documented.

### Lane D — AgentKVM2USB issue #22

**Status:** blocked.

Do not claim #22 until every entry-gate item is positively verified:

- reboot state clear after an operator-initiated restart;
- Wireshark and TShark present;
- approved USBPcap installation complete and `USBPcapCMD.exe` present;
- Epiphan application/driver state verified;
- Total Phase API staged with provenance;
- no conflicting claim.

Then use fresh branch `issue-22-readiness-completion`, open an early draft PR, and run only mapping and no-live readiness work.

### Lane E — AgentKVM2USB issue #14

**Status:** blocked by issue #22 `ok: true`.

Requires a new, experiment-specific, expiring authorization immediately before execution. No old approval carries forward.

### Lane F — PR #13 / issue #8 Phase B

**Status:** frozen.

Do not rebase, refresh, merge, or alter PR #13 as part of dependency, mapping, or experiment-preparation work. Resume only after issue #14 produces target-side forwarding evidence.

### Lane G — safe offline parallel work

Only separately issued, non-overlapping work may proceed:

- deterministic parsers, replay fixtures, schemas, and documentation;
- static analysis using already acquired lawful artifacts and ignored evidence;
- no hardware operation, package installation, vendor acquisition, or active-branch overlap.

Future architecture work under #23, #12, AgentWebCam #3, and #24 must not enter the current single-device critical path.

## Claim and worktree protocol

For every active slice:

1. Fetch/prune and inspect the issue, comments, PR, remote head, all worktrees, stashes, detached heads, untracked files, and ahead/behind state.
2. Preserve all unknown work; never reset, clean, auto-stash, rebase shared work, or force-push.
3. Run claim preflight and refuse an unexpired conflicting claim.
4. Post `START` with claim ID, branch/head, scope, safety boundary, and finite lease.
5. Renew with `CHECKPOINT`.
6. Verify the expected remote head immediately before push.
7. Post `HANDOFF`, release the claim, and leave all worktrees clean.

## Momentum sequence

1. Dispatch `SemperSupra/windows-package-foundry-private#2` on a fresh issue-specific branch and claim.
2. Establish whether USBPcap is `foundry_eligible`, the exact package/manual path, and full rollback evidence.
3. With the operator present, run issue #27 `-Plan`.
4. If reboot remains pending, stop and request an operator-initiated restart; rerun `-Plan` under a fresh claim afterward.
5. Install Wireshark through the shared UAC helper only after explicit human consent.
6. Stage authorized vendor artifacts only when the operator supplies the exact files and provenance.
7. Request manual USBPcap installation only if issue #2 explicitly approves that path and records exact verification and rollback instructions; otherwise use the reviewed Foundry package.
8. Claim issue #22 and obtain no-live `ok: true`.
9. Create a fresh issue #14 authorization and run the bounded experiment.
10. Revalidate PR #13 target receipt, then advance issue #8 Phase C.

## Stop conditions

Stop and report rather than improvise when:

- issue, branch, worktree, expected head, or claim ownership conflicts;
- an operator-required action lacks a human at the keyboard;
- a dependency is login-gated, personalized, expiring, license-incompatible, or unapproved;
- the shared UAC helper is missing, modified, untracked, ambiguous, or not origin-backed;
- a vendor installer lacks a current valid vendor signature matching provenance;
- a pending reboot exists;
- an action would capture, send input, recable, reboot automatically, or write persistent state;
- credentials, proprietary bytes, raw captures, or private workstation evidence could enter Git.
