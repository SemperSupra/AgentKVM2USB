# Issue #22 — Workstation capture dependencies and USBPcap mapping

Resume `SemperSupra/AgentKVM2USB` issue #22 using GitHub as the authoritative coordination surface.

## Purpose

Complete every non-live preparation step required for the official-app differential experiment without installing software automatically, elevating privileges, starting capture, sending target input, or changing hardware topology.

This work unblocks issue #14. It does not authorize the issue #14 experiment.

## Authoritative starting point

- Issue: #22
- Parent technical gate: #14
- Roadmap epic: #23
- Branch: `issue-22-workstation-capture-deps`
- Base: `recovery/agentkvm2usb-app-capabilities`
- Initial branch point: recovery head containing merged PR #25 (`33a3f49aef35ed818afdebdd34642398730d58a4`)
- PR #13 and PR #7 are out of scope

Always fetch GitHub first. A newer remote head, issue comment, review, or claim supersedes this snapshot.

## Safety boundary

Permitted:

- repository reconciliation by clean fast-forward;
- read-only Git/GitHub inspection;
- read-only Windows command, registry, PnP, USB topology, path, version, and disk inspection;
- `USBPcapCMD.exe -d` interface enumeration when installed;
- tests, compile checks, preflight, and blocked manifest generation;
- creation of ignored sanitized readiness evidence;
- preparation of operator commands and rollback instructions.

Prohibited:

- automatic UAC approval or elevation;
- installing, upgrading, uninstalling, or repairing software;
- starting USBPcap, TShark, Wireshark, Beagle, camera, microphone, or screen capture;
- sending keyboard, pointer, touch, macro, system-control, or other target input;
- recabling or changing the Beagle position;
- vendor OUT transfers;
- firmware, FPGA, EDID, flash, or persistent device writes;
- committing vendor binaries, credentials, raw captures, or private evidence;
- modifying, rebasing, merging, or refreshing PR #7 or PR #13;
- reset, clean, automatic stash, destructive worktree changes, or force push.

## 1. Reconcile local and remote state

Start in:

```text
C:\Users\Mark\Projects\AgentKVM2USB
```

Inspect all worktrees before changing anything:

```powershell
git worktree list --porcelain
git status --short --branch
git branch --show-current
git rev-parse HEAD
git log -5 --oneline --decorate
git stash list
```

Fetch authoritative state:

```powershell
git fetch --all --prune --tags
gh auth status
gh issue view 22 --repo SemperSupra/AgentKVM2USB --comments
gh issue view 14 --repo SemperSupra/AgentKVM2USB --comments
gh issue view 23 --repo SemperSupra/AgentKVM2USB --comments
gh pr view 7 --repo SemperSupra/AgentKVM2USB --json state,isDraft,mergeable,baseRefName,baseRefOid,headRefName,headRefOid,url
gh pr view 13 --repo SemperSupra/AgentKVM2USB --json state,isDraft,mergeable,baseRefName,baseRefOid,headRefName,headRefOid,url
```

If the canonical recovery checkout is clean and only behind its upstream, fast-forward it:

```powershell
git switch recovery/agentkvm2usb-app-capabilities
git merge --ff-only origin/recovery/agentkvm2usb-app-capabilities
```

Do not disturb the other worktrees. If any uncommitted, untracked, staged, detached, local-only, or divergent state exists, preserve it and stop before implementation.

## 2. Claim issue #22

Run the repository claim-preflight helper against issue #22 and the current remote branch head. Do not proceed with an unexpired conflicting claim.

Post a finite four-hour `START` record containing:

- actor/tool and workstation;
- unique claim ID;
- issued and expiry UTC;
- issue, branch, base, and expected remote head;
- exact no-live scope;
- validation plan;
- explicit safety boundary.

Renew with `CHECKPOINT` if needed. Finish with `HANDOFF` and release the claim.

## 3. Locate or create the issue worktree

Use the existing remote branch `issue-22-workstation-capture-deps`. Do not create a duplicate branch or worktree.

A suitable isolated worktree is:

```text
C:\Users\Mark\Projects\AgentKVM2USB-worktrees\issue-22-workstation-capture-deps
```

Create it only when absent:

```powershell
git worktree add C:\Users\Mark\Projects\AgentKVM2USB-worktrees\issue-22-workstation-capture-deps issue-22-workstation-capture-deps
```

Fast-forward only. Never rebase or force-update this branch.

## 4. Read the work package

Read:

- `AGENTS.md`;
- `docs/REMOTE_AGENT_COORDINATION.md`;
- `docs/ISSUE22_OPERATOR_RUNBOOK.md`;
- `docs/MULTI_DEVICE_MEDIA_SPEECH_ROADMAP.md`;
- `scripts/collect_issue22_readiness.ps1`;
- `scripts/official_app_baseline.py`;
- `test_issue22_work_package.py`;
- the issue #20 readiness artifact under ignored `.work/evidence/issue-20-workstation-preflight/`, when present.

## 5. Run deterministic validation

```powershell
python -m compileall -q scripts test_official_app_baseline.py test_issue22_work_package.py
python -m pytest -q
git diff --check
```

Run the safe inventory collector:

```powershell
pwsh -NoProfile -File .\scripts\collect_issue22_readiness.ps1 -Pretty
```

When the Total Phase API directory is known, repeat with:

```powershell
pwsh -NoProfile -File .\scripts\collect_issue22_readiness.ps1 `
  -BeagleApiDir .\.work\vendor\totalphase `
  -Pretty
```

The script must remain read-only except for writing its sanitized JSON under ignored `.work` storage.

## 6. Exercise the fail-closed experiment framework

Use the current CLI help and schema to supply all evidence already available. Run no-live only:

```powershell
python .\scripts\official_app_baseline.py preflight --help
python .\scripts\official_app_baseline.py build-manifest --help
```

Then run the applicable preflight and build-manifest commands using sanitized evidence. Until every prerequisite is complete, return code 2 / `ok: false` / `live_disabled: true` is expected.

Do not weaken gates to obtain a passing result.

## 7. Build the operator action packet

For each missing prerequisite, record:

- current detected state;
- exact operator action or command;
- whether elevation is required;
- whether physical presence is required;
- expected result;
- verification command;
- rollback or uninstall command where applicable;
- evidence field that becomes satisfied;
- stop conditions.

Required categories:

1. USBPcap installation and `USBPcapCMD.exe` verification.
2. Wireshark/TShark installation and version verification.
3. Official Epiphan application and driver installation/verification.
4. Total Phase Windows Beagle API staging with provenance and hashes.
5. Read-only USBPcap interface-to-KVM2USB root-hub mapping.
6. Exact physical cable path and Beagle position confirmation.
7. Harmless, non-sensitive target-state confirmation.
8. Complete official-app and Beagle driver evidence.

Do not claim the mapping is proven from global KVM presence or from only one detected USBPcap interface. Tie the exact KVM2USB device instance and parent topology to an interface actually reported by `USBPcapCMD.exe -d`.

## 8. Evidence and repository updates

Default sanitized output:

```text
.work/evidence/issue-22-workstation-capture-deps/readiness.json
```

Confirm it is inside the repository and ignored:

```powershell
git check-ignore -v .work/evidence/issue-22-workstation-capture-deps/readiness.json
```

Do not commit workstation-specific readiness JSON.

Committed changes, if any, are limited to reusable tooling, tests, schemas, docs, and prompts. Do not commit merely to show activity.

Update issue #22 and its draft PR with:

- branch and head SHA;
- claim ID and lease state;
- validation results and return codes;
- sanitized device/tool/topology summary;
- mapping status and supporting evidence;
- exact numbered `HUMAN ACTION REQUIRED` sequence;
- discrepancies from issue #20 or the latest audit;
- confirmation that live operation remained disabled.

## Exit gate

Before `HANDOFF`:

- local/remote state is reconciled without data loss;
- the issue #22 worktree is clean;
- all deterministic tests pass;
- the safe readiness collector runs successfully;
- no-live preflight/build-manifest behavior is recorded;
- every missing prerequisite has an exact operator and rollback plan;
- USBPcap mapping is either positively proven or explicitly unproven;
- ignored readiness evidence is updated;
- draft PR and issue #22 are current;
- claim is released;
- no prohibited action occurred.

Return a concise final report with:

- local and remote heads;
- branch/PR state;
- claim lifecycle;
- validation results;
- completed preparation;
- exact remaining human actions;
- exact next operator action;
- whether issue #14 is ready for a separately authorized live experiment.
