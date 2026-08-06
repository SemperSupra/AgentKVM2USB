# Issue #27 — Operator-controlled dependency acquisition and shared UAC workflow

Resume `SemperSupra/AgentKVM2USB` issue #27 using GitHub as the authoritative coordination surface.

## Objective

Complete and validate the reusable operator-facing dependency workflow required before issue #22 can finish. Reuse the existing human-gated UAC helper from `SupraCraft/minecraft-infra`; prefer exact WinGet packages; route Package Foundry candidates through approved metadata; and keep login-gated or license-restricted vendor files under manual local staging.

This issue does not authorize capture, target input, recabling, firmware, FPGA, EDID, flash, or automatic reboot.

## Authoritative scope

- Issue: #27
- Parent readiness gate: #22
- Later experiment: #14
- Branch: `issue-27-operator-dependencies`
- Base: `recovery/agentkvm2usb-app-capabilities`
- Initial branch point: `73f02886f48aa5340df78557a50bf209b0f5a123`
- Package policy: `SemperSupra/windows-package-foundry#1`
- USBPcap package candidate: `SemperSupra/windows-package-foundry#2`
- Shared UAC implementation: `SupraCraft/minecraft-infra/scripts/local/Invoke-Elevated.ps1`
- PR #13 is out of scope and remains untouched.

Always fetch current GitHub state. Newer issue comments, reviews, claims, or remote heads supersede this snapshot.

## Dependency dispositions

1. **Wireshark/TShark — existing public WinGet**
   - exact ID: `WiresharkFoundation.Wireshark`;
   - exact source: `winget`;
   - install only after shared-helper consent and ordinary Windows UAC;
   - independently verify package inventory, `Wireshark.exe`, and `tshark.exe`.

2. **USBPcap — Foundry candidate, blocked here**
   - do not use the stale `WiresharkFoundation.USBPcap` assumption;
   - do not run a direct upstream installer;
   - do not fall back to Chocolatey, Scoop, a browser download, or an arbitrary executable;
   - fail closed until Package Foundry #1 and #2 provide an approved source, package ID, hash, signing, install, uninstall, reboot, and rollback contract.

3. **Total Phase Beagle software/API/driver — manual vendor staging**
   - downloads require a vendor account and may be license-restricted;
   - never automate login, cookies, entitlement, click-through acceptance, or personalized URLs;
   - accept only an operator-supplied local file;
   - stage beneath ignored `.work/vendor/totalphase/` with hash/provenance;
   - portable API staging does not request UAC and never calls capture APIs.

4. **Epiphan KVM2USB application/driver — manual vendor staging/license review**
   - accept only an operator-supplied authorized file;
   - stage beneath ignored `.work/vendor/epiphan/`;
   - no Package Foundry publication without permission or a documented license determination;
   - when explicitly selected, invoke the exact staged installer through the shared UAC helper without invented silent switches or automatic license acceptance.

## Safety boundary

Permitted:

- lossless repository/worktree reconciliation;
- issue/PR/claim inspection and updates;
- read-only dependency, registry, PnP, path, signature, hash, disk, and reboot-state inventory;
- ignored local vendor staging from an operator-supplied file;
- read-only `-Plan` execution;
- operator-present UAC request through the trusted shared helper;
- exact WinGet installation of Wireshark after explicit consent;
- interactive launch of an exact staged Epiphan installer after explicit consent;
- deterministic tests, compile checks, and documentation updates.

Prohibited:

- automatic UAC approval or elevation;
- copying, forking, or reimplementing the shared consent logic;
- using `-SkipConsent`, `-Force`, auto mode, AFK mode, environment state, or agent instructions as consent;
- direct USBPcap installation before Package Foundry approval;
- vendor authentication, scraping, cookie/token reuse, or accepting terms for the operator;
- downloading proprietary vendor files;
- committing or uploading vendor binaries, credentials, raw captures, private evidence, browser profiles, or personalized URLs;
- capture through USBPcap, TShark, Wireshark, Beagle, UVC, microphone, or screen APIs;
- keyboard, mouse, touch, macro, system-control, or other target input;
- recabling or changing Beagle position;
- automatic reboot;
- firmware, FPGA, EDID, flash, vendor OUT, or persistent-device writes;
- modifying, rebasing, merging, or refreshing PR #13;
- reset, clean, automatic stash, destructive worktree actions, or force push.

## 1. Reconcile local state

Start in:

```text
C:\Users\Mark\Projects\AgentKVM2USB
```

Inspect every worktree and stash before changing anything:

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
gh issue view 27 --repo SemperSupra/AgentKVM2USB --comments
gh issue view 22 --repo SemperSupra/AgentKVM2USB --comments
gh issue view 14 --repo SemperSupra/AgentKVM2USB --comments
gh issue view 1 --repo SemperSupra/windows-package-foundry --comments
gh issue view 2 --repo SemperSupra/windows-package-foundry --comments
gh pr list --repo SemperSupra/AgentKVM2USB --state open --json number,title,isDraft,baseRefName,headRefName,headRefOid,url
```

If the canonical recovery checkout is clean and only behind, fast-forward it using `--ff-only`. Preserve and stop for any dirty, untracked, staged, detached, local-only, divergent, or unknown state.

## 2. Claim issue #27

Run the repository claim-preflight helper against issue #27 and the current remote branch head. Do not proceed with an unexpired conflicting claim.

Post a four-hour `START` record containing:

- actor/tool and workstation;
- claim ID;
- claimed and expiry UTC;
- issue, branch, base, expected remote head, and draft PR;
- exact implementation slice;
- planned validation;
- explicit safety boundary.

Renew with `CHECKPOINT` before expiry. Finish with `HANDOFF` and claim release.

## 3. Create or reuse the isolated worktree

Use the existing remote branch:

```text
issue-27-operator-dependencies
```

Preferred worktree:

```text
C:\Users\Mark\Projects\AgentKVM2USB-worktrees\issue-27-operator-dependencies
```

Create it only when absent. Fast-forward only. Never rebase or force-update the branch.

## 4. Read the work package

Read:

- `AGENTS.md`;
- `docs/ACTIVE_WORKSTREAMS.md`;
- `docs/ISSUE27_OPERATOR_DEPENDENCY_RUNBOOK.md`;
- `docs/ISSUE22_OPERATOR_RUNBOOK.md`;
- `prompts/ISSUE27_KICKOFF.md`;
- `scripts/prepare_issue22_dependencies.ps1`;
- `scripts/collect_issue22_readiness.ps1`;
- `test_issue27_work_package.py`;
- `test_issue22_work_package.py`;
- current Package Foundry #1/#2 state;
- the shared helper and its repository policy in the local `minecraft-infra` checkout.

## 5. Validate and complete the PowerShell workflow

The public operator interface must support:

```powershell
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Plan
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Install Wireshark
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Install USBPcap
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -StageVendorArtifact TotalPhaseBeagleApi -Path <file> -SourcePage <url> -AcquiredUtc <utc>
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -StageVendorArtifact EpiphanKvmApp -Path <file> -SourcePage <url> -AcquiredUtc <utc>
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -InstallStagedVendorArtifact EpiphanKvmApp -StagedPath <ignored-local-file>
```

Required behavior:

### Plan

- no elevation, install, vendor launch, capture, target input, or reboot;
- discover WinGet and exact tool paths/versions;
- discover both expected `minecraft-infra` layouts;
- verify the helper is from the expected Git repository;
- record dependency dispositions and blockers;
- inventory installed Epiphan/Total Phase applications and PnP driver state;
- inventory ignored vendor staging metadata only;
- report pending reboot indicators;
- write sanitized JSON only under ignored `.work/evidence/issue-27-operator-dependencies/`.

### Wireshark installation

- require a trusted helper;
- display exact package/source/actions;
- shared helper obtains human consent and launches ordinary UAC;
- elevated child invokes exact WinGet ID/source and explicit agreement flags;
- verify independently through WinGet and executable/version checks;
- report possible reboot without initiating it.

### USBPcap installation

- return a nonzero fail-closed result;
- identify Package Foundry #1/#2 as blockers;
- perform no download, installer invocation, source addition, or fallback.

### Vendor staging

- source must be a real operator-supplied local file;
- destination must be the correct ignored `.work/vendor/...` root;
- copy idempotently; refuse same-name/different-content collisions;
- record filename, size, SHA-256, signature status and signer when available, source page, acquisition UTC, disposition, and staged path relative to the repository;
- omit credentials, cookies, tokens, browser profiles, personalized query data, and proprietary bytes from output;
- portable staging never requests UAC.

### Staged Epiphan installation

- path must resolve inside ignored `.work/vendor/epiphan/`;
- provenance record and current hash must match;
- shared helper requests human consent and UAC;
- elevated child launches only the exact local file interactively;
- no invented unattended switches;
- no automatic terms acceptance;
- wait for completion, inventory resulting application/driver state, and report reboot status.

## 6. Deterministic tests

Add or complete tests for:

- all work-package files exist;
- active-workstream boundaries and dependency graph;
- shared-helper discovery in both layouts;
- trusted-origin validation;
- missing/untrusted helper fails closed;
- plan mode has no elevation/install path;
- auto/AFK cannot imply consent;
- exact Wireshark ID and source;
- USBPcap is blocked without direct-installer fallback;
- manual-vendor artifacts cannot enter the package-install path;
- ignored destination enforcement;
- hash/provenance and collision behavior;
- portable API staging does not request UAC;
- staged vendor install requests the shared helper;
- pending reboot is reported but no reboot command exists;
- no capture or target-input command is reachable;
- issue #22 docs no longer contain the stale USBPcap package ID or direct acquisition instructions.

Run:

```powershell
python -m compileall -q scripts test_issue22_work_package.py test_issue27_work_package.py
python -m pytest -q
git diff --check
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Plan
```

Do not perform a privileged installation merely to satisfy validation. Record actual privileged validation as pending operator action unless the operator is physically present and explicitly approves that exact action.

## 7. Documentation cleanup

Ensure the repository tells one consistent story:

- `docs/ACTIVE_WORKSTREAMS.md` is the current multi-agent execution map;
- issue #27 owns acquisition, staging, and human-gated UAC;
- issue #22 owns readiness, mapping, topology, and no-live preflight after dependencies exist;
- issue #14 owns the later separately authorized experiment;
- Package Foundry owns USBPcap eligibility/package work;
- PR #13 remains frozen;
- `AGENTS.md`, the #22 runbook/prompt, and tests contain no stale direct USBPcap package assumption.

Do not delete historical branches or evidence merely to make the repository look tidy. Mark superseded instructions and preserve provenance.

## 8. PR and issue updates

Update issue #27 and its draft PR with:

- branch and head SHA;
- claim ID/state;
- exact files changed;
- test and `-Plan` results;
- shared-helper discovery/trust status;
- dependency dispositions;
- USBPcap blocker state from Package Foundry;
- exact human actions remaining;
- confirmation that capture, target input, recabling, reboot, credentials, and proprietary publication did not occur.

Add a concise cross-link comment to issue #22 explaining that #27 now owns dependency acquisition and #22 resumes only after dependencies are ready.

## Exit gate

Before `HANDOFF`:

- branch/worktree state is clean and synchronized;
- issue #27 has no conflicting active claim;
- full tests and diff checks pass;
- `-Plan` succeeds on Windows without elevation;
- shared-helper discovery/trust works for the actual local layout;
- Wireshark command construction is exact and human-gated;
- USBPcap remains fail-closed unless Package Foundry has genuinely completed;
- vendor staging is ignored, hash-verified, and credential-free;
- no capture/input/reboot/persistent device operation occurred;
- issue #27, issue #22, and the draft PR are current;
- claim is released.

Return a concise report with:

- local and remote heads;
- branch/PR and claim lifecycle;
- files changed;
- validation results;
- dependency status;
- exact operator actions;
- Package Foundry blockers;
- whether issue #22 is ready to resume.
