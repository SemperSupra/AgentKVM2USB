# Instructions for AI Agents

These rules govern AI-agent work in AgentKVM2USB.

## Read first

Before changing code or operating hardware, read:

1. `docs/EXECUTION_CHECKPOINT.md` for the current verified resume state;
2. `docs/ACTIVE_WORKSTREAMS.md` for lane ownership and sequencing;
3. the assigned GitHub issue and every current comment;
4. the assigned remote branch and draft PR, when any;
5. the issue-specific runbook and canonical prompt;
6. `PROJECT_STATUS.md` for historical hardware evidence and known protocol gaps.

The checkpoint and newer GitHub claims/comments supersede stale repository-triage text in historical documents.

## Repository coordination

- Use one issue, one branch, one isolated worktree, one draft PR, and one finite claim per repository-change slice.
- Operator-only execution still requires a finite issue claim and explicit handoff.
- Inspect every worktree, stash, local-only commit, detached head, untracked file, and ahead/behind state before changing anything.
- Run claim preflight and refuse conflicting unexpired work.
- Post `START`, renew with `CHECKPOINT`, and finish with `HANDOFF` plus claim release.
- Push only after verifying the expected remote head.
- Never reset, clean, auto-stash, discard unknown work, rebase shared work, or force-push to resolve ambiguity.

## Current dependency boundary

PR #28 is merged. Issue #27 now owns only the remaining operator prerequisites and exact blocker verification.

- Reuse `SupraCraft/minecraft-infra/scripts/local/Invoke-Elevated.ps1`; do not copy or reimplement its consent flow.
- Accept the helper only when tracked, clean, unmodified, origin-backed, and unambiguous.
- Prefer exact public WinGet packages.
- Keep USBPcap blocked until Windows Package Foundry #1/#2 provide an approved package path.
- Treat Total Phase and Epiphan artifacts as operator-supplied, ignored local files.
- Require a current valid Epiphan signature matching staged provenance before elevation.
- Never automate vendor login, cookies, tokens, entitlements, personalized downloads, or license acceptance.
- Never commit or upload proprietary vendor bytes, credentials, raw captures, or private workstation evidence.

Issue #22 owns readiness, USBPcap mapping, topology, and no-live preflight after its entry gate. Issue #14 owns the later separately authorized experiment. PR #13 remains frozen.

## Hardware safety

- Verify target signal and identity before any authorized interaction.
- Treat all keyboard, pointer, touch, macro, system-control, and vendor OUT operations as physical target actions.
- Do not start capture, send target input, recable, reboot automatically, or write firmware, FPGA data, EDID, flash, or persistent device state without the exact issue gate and explicit human authorization.
- Keep screenshots, recordings, PCAPs, SRT files, session logs, and machine-specific evidence outside Git.

## Macro engine

For an authorized sequential target action, use `sdk.run_macro()` rather than separate calls. Macro availability does not itself authorize target input.

```python
routine = """
PRESS f2
DELAY 1000
PRESS down
PRESS enter
"""
sdk.run_macro(routine)
```

Review `MACROS.md` before using the macro engine.

## Screen and pointer conventions

- Read status with `sdk.get_status()` before an authorized target interaction.
- Read the current frame with `sdk.get_screen()` for analysis.
- `sdk.click()` coordinates are normalized percentages from `0.0` to `1.0`, not absolute pixels.
