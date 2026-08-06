# Issue #20 — Workstation reconciliation and no-live capture preflight

Resume `SemperSupra/AgentKVM2USB` issue #20 using GitHub as the authoritative coordination surface.

## Authoritative starting state

- Parent issue: #14
- Issue: #20
- Branch: `issue-20-workstation-capture-prep`
- Base: `recovery/agentkvm2usb-app-capabilities`
- PR #19 merged into the base at `8acf728e0dde8c24b4b7220c2514dd51a6649b5f`
- PR #13 must remain untouched

Always fetch GitHub first and use newer remote state when it differs from this snapshot.

## First: reconcile safely after the interrupted/OOM session

Inspect the canonical checkout and every AgentKVM2USB worktree before changing anything:

```powershell
$repo = 'C:\Users\Mark\Projects\AgentKVM2USB'
git -C $repo worktree list --porcelain
```

Likely worktree paths include:

```text
C:\Users\Mark\Projects\AgentKVM2USB
C:\Users\Mark\Projects\AgentKVM2USB-worktrees\issue-14-official-app-baseline
C:\Users\Mark\Projects\AgentKVM2USB-worktrees\issue-20-workstation-capture-prep
```

For each relevant checkout, record:

```powershell
git status --short --branch
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git log -5 --oneline --decorate
git reflog -10 --date=iso
git diff --stat
git diff
git diff --cached
git ls-files --others --exclude-standard
```

If uncommitted, staged, untracked, detached, divergent, or local-only work exists:

- do not reset, clean, discard, overwrite, automatically stash, or force-push;
- preserve an inventory under ignored `.work/recovery/<UTC-correlation-id>/`;
- create a protective local branch for an otherwise unreferenced commit when needed;
- compare local-only commits with the current remote branch before deciding anything;
- stop implementation work and report if histories cannot be reconciled by a clean fast-forward.

Do not print secrets, credentials, proprietary binaries, or raw restricted evidence.

## Fetch and reconstruct current remote state

```powershell
cd C:\Users\Mark\Projects\AgentKVM2USB
git fetch --prune origin
gh auth status
gh issue view 20 --repo SemperSupra/AgentKVM2USB --comments
gh issue view 14 --repo SemperSupra/AgentKVM2USB --comments
gh pr view 19 --repo SemperSupra/AgentKVM2USB --json state,isDraft,mergedAt,baseRefName,baseRefOid,headRefName,headRefOid,url
```

Read `AGENTS.md`, `PROJECT_STATUS.md`, `docs/REMOTE_AGENT_COORDINATION.md`, and this prompt.

Verify that PR #19 is merged. Fast-forward the recovery branch only:

```powershell
git switch recovery/agentkvm2usb-app-capabilities
git merge --ff-only origin/recovery/agentkvm2usb-app-capabilities
```

The recovery head must contain merge commit `8acf728e0dde8c24b4b7220c2514dd51a6649b5f` or a newer authoritative descendant.

Locate or create the issue #20 worktree from the existing remote branch. Do not create duplicate worktrees or branches when they already exist.

## Claim and coordination

Run the repository claim preflight for issue #20. Do not begin implementation with an unexpired conflicting claim.

Post `START` containing:

- actor/tool and workstation;
- unique claim ID;
- finite lease;
- branch and starting remote head;
- recovery-base head;
- reconciliation result;
- assigned no-live preparation slice;
- validation plan;
- explicit safety boundary.

Renew with `CHECKPOINT` when needed and finish with `HANDOFF` releasing the claim.

## Assigned work

### 1. Verify the merged framework

Run the applicable deterministic checks:

```powershell
python -m compileall -q scripts test_official_app_baseline.py
python -m pytest -q
git diff --check
```

Do not repeat expensive unrelated container builds unless remote drift or a current issue assignment requires them.

### 2. Run no-live workstation preflight

Run the merged no-live CLI from the issue branch:

```powershell
python scripts\official_app_baseline.py preflight
python scripts\official_app_baseline.py build-manifest
```

These commands are expected to fail closed until all required evidence is complete. Record return codes and sanitized output.

Detect and record, without installing or changing hardware:

- USBPcapCMD;
- Wireshark/TShark;
- official Epiphan app and driver;
- Total Phase Beagle Windows API directory;
- Beagle driver/device;
- KVM2USB VID/PID/device identity;
- detected USBPcap interfaces;
- free disk space on the evidence volume;
- `.work` output-root containment and `git check-ignore` result;
- current physical topology fields already known locally;
- missing topology and target-state confirmations.

### 3. Prepare exact human actions

Do not install, elevate, recable, or send input.

Produce exact operator actions for every remaining blocker, including as applicable:

- elevated installation command for USBPcap/Wireshark;
- official Epiphan app/driver installation or verification;
- Total Phase Beagle API staging and driver/device verification;
- safe disk-space remediation or relocation proposal without deleting unknown data;
- read-only PowerShell/USBPcap commands needed to map the KVM2USB device instance to the correct detected USBPcap root-hub interface;
- physical cable path and Beagle-position confirmation;
- harmless target-state confirmation.

Do not label an interface mapping as proven until the evidence ties the detected KVM2USB VID/PID/device instance to a USBPcap interface present on this workstation.

### 4. Readiness artifact

Write a sanitized machine-readable readiness report under ignored storage, for example:

```text
.work/evidence/issue-20-workstation-preflight/readiness.json
```

Include:

- correlation ID and UTC timestamps;
- repository, issue, branch, base and heads;
- reconciliation findings;
- tool and driver detections;
- device identity;
- interface enumeration and mapping status;
- topology and target-state fields;
- disk and output-root validation;
- commands executed and return codes;
- blockers and exact human actions;
- confirmation that live execution stayed disabled.

Raw captures, proprietary binaries, credentials, and restricted evidence remain outside Git.

### 5. Repository changes

Keep committed changes limited to reusable, independently written preparation tooling, tests, sanitized schemas/docs, and the canonical prompt. Do not commit workstation-specific raw evidence.

If no code change is needed after reconciliation and preflight, do not create a commit merely to show activity. Update the draft PR and issue with the readiness result and blockers instead.

If code changes are needed, keep them bounded to issue #20, add deterministic tests, and push normally only after verifying the remote head still matches the active claim.

## Exit gate

Before handoff:

- local/remote state is reconciled without data loss;
- the recovery branch contains PR #19's merge;
- issue #20 claim is released;
- no-live preflight and blocked-manifest behavior are recorded;
- all available workstation evidence is captured in ignored storage;
- exact remaining human actions are posted to issue #20 and the draft PR;
- applicable tests pass;
- the worktree is clean;
- no live capture/input, privileged installation, recabling, unknown vendor OUT, firmware/FPGA/EDID/flash write, destructive cleanup, or force push occurred.

Do not close parent issue #14 and do not modify PR #13.