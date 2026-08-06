# Multi-agent dispatch prompt

Use this in a coordinator agent after reading `docs/EXECUTION_CHECKPOINT.md` and the latest GitHub claims.

```text
Coordinate the next AgentKVM2USB work from GitHub without performing hardware or privileged actions yourself.

Treat these as the only currently dispatchable lanes:

1. SemperSupra/windows-package-foundry issue #1 — package eligibility framework. One issue, branch, isolated worktree, draft PR, and finite claim.
2. SemperSupra/windows-package-foundry issue #2 — bounded USBPcap research/package design. It may proceed in parallel, but publication and primary-host installation remain blocked until #1 classifies USBPcap foundry_eligible. One issue, branch, isolated worktree, draft PR, and finite claim.
3. SemperSupra/AgentKVM2USB issue #27 — operator prerequisites only while the operator is physically present. Use prompts/ISSUE27_KICKOFF.md. Run Plan first; stop and hand off on a pending reboot; never initiate reboot or bypass human UAC.
4. Separately issued offline parser/replay/schema/documentation work only when it does not overlap any active claim or operate hardware.

Do not dispatch AgentKVM2USB issue #22 until every entry-gate item in prompts/ISSUE22_KICKOFF.md is positively verified. Do not dispatch issue #14. Do not modify, rebase, refresh, or merge PR #13.

Before dispatching any lane:
- fetch and read the issue and all comments;
- inspect current claims and refuse conflicts;
- verify the exact remote head;
- require lossless worktree reconciliation;
- assign a bounded scope and explicit safety boundary;
- require START, CHECKPOINT, HANDOFF, claim release, and clean worktrees;
- require GitHub comments/PRs as the coordination channel.

Return a dispatch report naming each lane, actor, repository, issue, branch, expected starting SHA, claim state, allowed scope, blockers, and stop conditions. Do not create duplicate claims or broaden a lane to absorb another issue.
```
