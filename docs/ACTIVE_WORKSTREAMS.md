# Active Workstreams and Multi-Agent Boundaries

This is the authoritative execution map for AgentKVM2USB. The newest GitHub issue comments, finite claims, and remote branch heads override older notes.

## Current integration state

- Integration branch: `recovery/agentkvm2usb-app-capabilities`
- Verified integration head: `5a398ac529d1e050101a6f078153f3935498d6d2`
- PR #28: merged at `5a398ac`; its implementation branch is historical and must not be reused.
- Post-merge CI: run `31114396438`, 254 tests passed, PowerShell no-live integration checks passed, portable build reproduced, no artifacts uploaded.
- Current coordination issue: #31.
- Do not develop directly on the integration branch.

Read `docs/EXECUTION_CHECKPOINT.md` before accepting or dispatching work.

## Critical path

```text
PR #28 merged: issue #27 workflow implemented
              |
              +--> operator reboot + Wireshark + vendor staging
              |
windows-package-foundry #1 eligibility
              |
              +--> windows-package-foundry #2 USBPcap package
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

- USBPcap packaging;
- vendor login or license acceptance automation;
- capture, target input, recabling, automatic reboot, or persistent device writes;
- issue #22 mapping;
- issue #14 experiment authorization;
- PR #13 changes.

### Lane B — Windows Package Foundry #1

**Repository:** `SemperSupra/windows-package-foundry`

May proceed now on its own issue, branch, worktree, draft PR, and finite claim.

Owns the four-way package eligibility policy and manual-vendor exclusion registry. It must classify USBPcap before package publication and keep Total Phase/Epiphan manual-only unless licensing evidence changes.

### Lane C — Windows Package Foundry #2

**Repository:** `SemperSupra/windows-package-foundry`

May perform bounded research and package design in parallel, but publication and primary-host installation remain subordinate to #1.

Owns USBPcap provenance, signing, Windows support, silent behavior, detection, uninstall, reboot, rollback, and disposable-host validation.

### Lane D — AgentKVM2USB issue #22

**Status:** blocked.

Do not claim #22 until every entry-gate item is positively verified:

- reboot state clear after an operator-initiated restart;
- Wireshark and TShark present;
- approved USBPcap installation path complete and `USBPcapCMD.exe` present;
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
2. Preserve all unknown work; never reset, clean, auto-stash, rebase, or force-push to resolve ambiguity.
3. Run claim preflight and refuse an unexpired conflicting claim.
4. Post `START` with claim ID, branch/head, scope, safety boundary, and finite lease.
5. Renew with `CHECKPOINT`.
6. Verify the expected remote head immediately before push.
7. Post `HANDOFF`, release the claim, and leave all worktrees clean.

Preferred worktrees:

```text
C:\Users\Mark\Projects\AgentKVM2USB
C:\Users\Mark\Projects\AgentKVM2USB-worktrees\issue-31-multi-agent-resume
C:\Users\Mark\Projects\AgentKVM2USB-worktrees\issue-27-operator-actions
C:\Users\Mark\Projects\AgentKVM2USB-worktrees\issue-22-readiness-completion
```

## Momentum sequence

1. Merge issue #31 documentation reconciliation after hosted CI.
2. In parallel, execute Windows Package Foundry #1 and bounded #2 work.
3. With the operator present, run issue #27 `-Plan`.
4. If reboot remains pending, stop and request an operator-initiated restart; rerun `-Plan` under a fresh claim afterward.
5. Install Wireshark through the shared UAC helper only after explicit human consent.
6. Stage authorized vendor artifacts only when the operator supplies the exact files and provenance.
7. After Package Foundry produces an approved USBPcap path, install and verify it through the reviewed workflow.
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
