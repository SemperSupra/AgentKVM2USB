# Issue #22 — Readiness completion and USBPcap mapping

Resume `SemperSupra/AgentKVM2USB` issue #22 only after issue #27 and the relevant Windows Package Foundry work have produced a usable dependency state.

## Purpose

Complete the remaining read-only preparation for the issue #14 official-application differential experiment:

- verify installed/staged dependencies;
- prove the exact USBPcap interface-to-KVM2USB root-hub mapping;
- record physical topology and harmless target state;
- run no-live preflight until `ok: true`;
- generate a valid manifest without capture or target input.

Issue #22 does not acquire software and does not authorize the later experiment.

## Authoritative ownership

- Issue #27 owns dependency planning, human-gated UAC, WinGet, and manual vendor staging.
- Windows Package Foundry #1/#2 own USBPcap eligibility and packaging.
- Issue #22 owns readiness, mapping, topology, and no-live preflight.
- Issue #14 owns the later separately authorized experiment.
- PR #13 is out of scope.

Read `docs/ACTIVE_WORKSTREAMS.md` and `docs/ISSUE22_OPERATOR_RUNBOOK.md` before proceeding.

## Entry gate

Do not claim issue #22 until:

- issue #27 has a reviewed usable dependency workflow;
- Wireshark/TShark are verified;
- USBPcap has an approved installation path and `USBPcapCMD.exe` is present;
- the Epiphan application/driver state is verified;
- the Total Phase API is staged under ignored local storage;
- any required reboot has been separately approved and verified;
- no conflicting issue #22 claim exists.

When the entry gate is incomplete, report the exact blocker and return the work to issue #27 or Package Foundry. Do not improvise an installer or source.

## Branch and worktree

The original `issue-22-workstation-capture-deps` branch and PR #26 are merged historical work. Do not resume new commits there.

After fetching current GitHub state and running claim preflight, create a fresh branch from the current integration head:

```text
issue-22-readiness-completion
```

Use an isolated worktree, an early draft PR, a four-hour `START` claim, `CHECKPOINT` renewals, and final `HANDOFF` plus claim release.

## Reconciliation

Start in:

```text
C:\Users\Mark\Projects\AgentKVM2USB
```

Inspect all worktrees, stashes, heads, upstreams, local-only commits, untracked files, and ahead/behind state. Fetch/prune remotes and read issues #22, #27, #14, Package Foundry #1/#2, open PRs, and current claims.

Preserve and stop for any unknown, dirty, detached, divergent, or conflicting state. Never reset, clean, auto-stash, discard, or force-push.

## Read-only validation

Run:

```powershell
python -m compileall -q scripts test_official_app_baseline.py test_issue22_work_package.py test_issue27_work_package.py
python -m pytest -q
git diff --check
pwsh -NoProfile -File .\scripts\prepare_issue22_dependencies.ps1 -Plan
pwsh -NoProfile -File .\scripts\collect_issue22_readiness.ps1 `
  -BeagleApiDir .\.work\vendor\totalphase `
  -Pretty
```

Confirm both JSON evidence files are under ignored `.work` storage.

## USBPcap enumeration and mapping

Run enumeration only:

```powershell
Get-Command USBPcapCMD.exe -ErrorAction Stop | Format-List Source,Version
& (Get-Command USBPcapCMD.exe).Source -d
```

Do not supply an output file or any capture-start option.

Build mapping evidence that ties the exact KVM2USB device instance, ContainerId, MI_00/MI_01/MI_03 interfaces, parent composite device, VIA hub, root controller, and location path to an interface actually listed by `USBPcapCMD.exe -d`.

Use the current `official_app_baseline.py` help, schema, and tests for the exact JSON shape. Do not infer mapping from global presence, a single interface, or an unverified physical assumption.

## Physical and target evidence

The operator records the exact:

- KVM2USB unit and device identity;
- host port/hub path;
- target-side cable path;
- Beagle identity, location, and orientation;
- target identity and current screen/state;
- harmless, non-sensitive target-state confirmation.

Do not recable under this slice.

## No-live preflight

Inspect current help:

```powershell
python .\scripts\official_app_baseline.py preflight --help
python .\scripts\official_app_baseline.py build-manifest --help
```

Run each with complete verified evidence. Do not weaken a gate.

The exit condition is:

- `ok: true`;
- `live_disabled: true`;
- positive mapping to the present KVM2USB;
- all tool, API, application, driver, topology, target, output, and disk gates pass;
- valid manifest generated;
- no capture or target input.

## Safety boundary

Do not:

- acquire or install dependencies outside issue #27;
- automate vendor login, cookies, tokens, entitlements, or license acceptance;
- start USBPcap, TShark, Wireshark, Beagle, UVC, microphone, or screen capture;
- send keyboard, pointer, touch, macro, system-control, or vendor OUT operations;
- recable or change Beagle position;
- reboot automatically;
- write firmware, FPGA data, EDID, flash, or persistent device state;
- commit proprietary bytes, credentials, raw captures, or private evidence;
- modify PR #13.

## Handoff

Update issue #22 and its new draft PR with claim state, branch/head, validation, mapping proof, topology/target evidence, preflight result, manifest result, and confirmation that live operation remained disabled.

Post `CHECKPOINT`, `HANDOFF`, release the claim, and leave the worktree clean.

Do not start issue #14. Report whether the repository is ready for a new experiment-specific authorization.
