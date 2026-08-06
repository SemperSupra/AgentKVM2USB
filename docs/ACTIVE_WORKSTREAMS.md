# Active Workstreams and Multi-Agent Boundaries

This document is the current execution map for AgentKVM2USB. GitHub issues, pull requests, and finite claims remain authoritative when they contain newer information.

## Current integration branch

- Integration branch: `recovery/agentkvm2usb-app-capabilities`
- Last branch point for issue #27: `73f02886f48aa5340df78557a50bf209b0f5a123`
- Do not develop directly on the integration branch.
- Every active slice uses one issue, one branch, one isolated worktree, one draft PR, and one finite claim.

## Critical path

```text
windows-package-foundry #1 eligibility policy
              |
              +--> windows-package-foundry #2 USBPcap package
              |                       |
AgentKVM2USB #27 dependency workflow --+
              |
              v
AgentKVM2USB #22 readiness + USBPcap mapping
              |
              v
AgentKVM2USB #14 separately authorized experiment
              |
              v
PR #13 / issue #8 Phase B target receipt
              |
              v
issue #8 Phases C-E -> issue #12 -> media/audio/speech roadmap
```

## Parallel work lanes

### Lane A — AgentKVM2USB issue #27

**Branch:** `issue-27-operator-dependencies`

Owns:

- reuse of `SupraCraft/minecraft-infra/scripts/local/Invoke-Elevated.ps1`;
- read-only dependency planning and inventory;
- exact public WinGet installation for Wireshark/TShark after human consent;
- fail-closed USBPcap handling until Package Foundry #2 is approved;
- local hash/provenance staging for Total Phase and Epiphan artifacts;
- operator-present invocation of a staged vendor installer when explicitly selected;
- reboot detection and post-install verification;
- tests, runbook, and sanitized ignored evidence.

Does not own:

- USBPcap package development;
- vendor login automation;
- capture, target input, recabling, firmware, FPGA, EDID, or flash work;
- PR #13 changes;
- issue #14 authorization or experiment execution.

### Lane B — Windows Package Foundry issues #1 and #2

**Repository:** `SemperSupra/windows-package-foundry`

Owns:

- four-way package eligibility classification;
- manual-vendor and blocked-artifact exclusions;
- USBPcap provenance, licensing, Windows 11, signing, silent install, uninstall, reboot, and rollback assessment;
- a reviewed Foundry package only if USBPcap is eligible.

Does not own AgentKVM2USB scripts or hardware experiments.

### Lane C — AgentKVM2USB issue #22

Blocked until issue #27 is usable and USBPcap has an approved installation path.

Owns only:

- readiness inventory after dependencies are present;
- USBPcap interface-to-KVM2USB root-hub mapping;
- physical topology and harmless target-state records;
- no-live preflight and manifest generation.

It does not acquire dependencies and it does not authorize capture.

### Lane D — AgentKVM2USB issue #14

Blocked until issue #22 reports `ok: true`.

Owns the later synchronized official-application differential experiment. It requires a new experiment-specific authorization with exact target, allowed input, issued UTC, expiry UTC, output root, interfaces, stop conditions, and forbidden actions.

### Lane E — PR #13 / issue #8 Phase B

Frozen while #22 and #14 are incomplete. Do not rebase, refresh, merge, or alter the keyboard branch as part of dependency or capture-preparation work.

## Claim protocol

Before changing an active lane:

1. Fetch and inspect all issue comments and the remote branch head.
2. Run the repository claim preflight.
3. Refuse to proceed when an unexpired conflicting claim exists.
4. Post `START` with a unique claim ID, exact branch/head, scope, safety boundary, and finite lease.
5. Post `CHECKPOINT` before lease expiry when work continues.
6. Push only after verifying the expected remote head.
7. Post `HANDOFF`, release the claim, and leave the worktree clean.

## Worktree convention

Preferred locations:

```text
C:\Users\Mark\Projects\AgentKVM2USB
C:\Users\Mark\Projects\AgentKVM2USB-worktrees\issue-27-operator-dependencies
C:\Users\Mark\Projects\AgentKVM2USB-worktrees\issue-22-workstation-capture-deps
```

Before creating or changing a worktree, inspect every existing worktree, stash, local-only commit, detached head, untracked file, and ahead/behind state. Never use destructive cleanup to resolve ambiguity.

## Near-term momentum sequence

1. Complete and locally validate issue #27 in its draft PR.
2. In parallel, complete Windows Package Foundry #1 and #2.
3. Merge issue #27 after review; do not wait for USBPcap packaging to merge the fail-closed workflow.
4. Once an approved USBPcap path exists, use issue #27 to request human UAC and install dependencies.
5. Resume issue #22 for mapping and no-live `ok: true`.
6. Prepare a fresh issue #14 experiment authorization.
7. Run the bounded experiment and use its evidence to unblock PR #13 target-receipt validation.

## Stop conditions

Stop and report rather than improvising when:

- issue, branch, worktree, or claim ownership conflicts;
- a dependency is login-gated, personalized, expiring, or license-incompatible;
- a package ID or Foundry source is unapproved;
- the shared UAC helper is missing or not from `SupraCraft/minecraft-infra`;
- elevation would occur without a human-present consent prompt;
- an operation would capture, send target input, recable, reboot automatically, or write persistent device state;
- proprietary bytes, credentials, cookies, tokens, browser profiles, raw captures, or private machine evidence could enter Git.
