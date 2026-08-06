# Instructions for AI Agents

These rules govern AI-agent work in AgentKVM2USB.

## Read first

Before changing code or operating hardware, read:

1. `docs/ACTIVE_WORKSTREAMS.md` for the current multi-agent execution map;
2. the assigned GitHub issue and every current comment;
3. the assigned branch and draft PR;
4. `PROJECT_STATUS.md` for hardware validation and known gaps;
5. the issue-specific runbook and canonical prompt.

GitHub claims and newer issue comments supersede older local notes.

## Repository coordination

- Use one issue, one branch, one isolated worktree, one draft PR, and one finite claim per active slice.
- Inspect every worktree, stash, local-only commit, detached head, untracked file, and ahead/behind state before changing anything.
- Run claim preflight and refuse conflicting unexpired work.
- Post `START`, renew with `CHECKPOINT`, and finish with `HANDOFF` plus claim release.
- Push only after verifying the expected remote head.
- Never reset, clean, auto-stash, discard unknown work, or force-push to resolve ambiguity.

## Current dependency boundary

Issue #27 owns dependency planning, manual vendor staging, and operator-controlled elevation.

- Reuse `SupraCraft/minecraft-infra/scripts/local/Invoke-Elevated.ps1`; do not copy or reimplement its consent flow.
- Prefer exact public WinGet packages.
- Keep USBPcap blocked until Windows Package Foundry #1/#2 provide an approved package path.
- Treat Total Phase and Epiphan artifacts as operator-supplied, ignored local files unless licensing and packaging eligibility are explicitly resolved.
- Never automate vendor login, cookies, tokens, entitlements, personalized downloads, or license acceptance.
- Never commit or upload proprietary vendor bytes, credentials, raw captures, or private workstation evidence.

Issue #22 owns readiness, USBPcap mapping, topology, and no-live preflight after dependencies are ready. Issue #14 owns the later separately authorized experiment. PR #13 is not part of dependency or capture-preparation work.

## Hardware safety

- Verify target signal and identity before any interaction.
- Treat all keyboard, pointer, touch, macro, system-control, and vendor OUT operations as physical target actions.
- Do not start capture, send target input, recable, reboot automatically, or write firmware, FPGA data, EDID, flash, or persistent device state without the exact issue gate and explicit human authorization.
- Keep screenshots, recordings, PCAPs, SRT files, session logs, and machine-specific evidence outside Git.

## Macro engine

For an authorized sequential target action, use `sdk.run_macro()` rather than separate calls. This improves timing, readability, and auditability.

```python
routine = """
PRESS f2
DELAY 1000
PRESS down
PRESS enter
"""
sdk.run_macro(routine)
```

Review `MACROS.md` before using the macro engine. Macro availability does not itself authorize target input.

## Screen and pointer conventions

- Read status with `sdk.get_status()` before an authorized target interaction.
- Read the current frame with `sdk.get_screen()` for analysis.
- `sdk.click()` coordinates are normalized percentages from `0.0` to `1.0`, not absolute pixels.
