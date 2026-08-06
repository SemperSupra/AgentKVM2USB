# Multi-agent dispatch prompt

Use this in a coordinator agent after reading `docs/EXECUTION_CHECKPOINT.md` and the latest GitHub claims.

```text
Coordinate the next AgentKVM2USB work from GitHub without performing hardware or privileged actions yourself.

Repository authority:

- SemperSupra/windows-package-foundry-private is the authoritative Package Foundry control repository and contains issues #1 and #2.
- SemperSupra/windows-package-foundry is the generated public deployment projection. Do not create or dispatch Package Foundry issue work there.
- Package Foundry Gate 1 / private issue #1 is merged at 6f86487d2b6a4aafb37b1eb82e53f0529fa8d0de.

Treat these as the only currently dispatchable lanes:

1. SemperSupra/windows-package-foundry-private issue #2 — USBPcap assessment and package design. Use one issue, branch, isolated worktree, early draft PR, and finite claim. Establish exact upstream provenance, hash, signing, Windows 11 behavior, supported install/uninstall, detection, reboot, rollback, and disposable-host evidence. Classify USBPcap under the merged Gate 1 policy before publication or primary-host installation.
2. SemperSupra/AgentKVM2USB issue #27 — operator prerequisites only while the operator is physically present. Use prompts/ISSUE27_KICKOFF.md. Run Plan first; stop and hand off on a pending reboot; never initiate reboot or bypass human UAC.
3. Separately issued offline parser/replay/schema/documentation work only when it does not overlap any active claim or operate hardware.

The operator has offered to install USBPcap manually if needed. Do not ask the operator to install it until private Foundry issue #2 explicitly records:

- the exact approved installer and immutable source;
- SHA-256 and signing state;
- Windows 11 suitability;
- exact install and verification procedure;
- reboot expectations;
- uninstall and rollback procedure;
- whether manual installation is the reviewed exception or a Foundry package must be used.

Do not dispatch AgentKVM2USB issue #22 until every entry-gate item in prompts/ISSUE22_KICKOFF.md is positively verified. Do not dispatch issue #14. Do not modify, rebase, refresh, or merge PR #13.

Before dispatching any lane:
- fetch and read the issue and all comments;
- inspect current claims and refuse conflicts;
- verify the exact remote head;
- require lossless worktree reconciliation;
- assign a bounded scope and explicit safety boundary;
- require START, CHECKPOINT, HANDOFF, claim release, and clean worktrees;
- require GitHub comments and PRs as the coordination channel.

Return a dispatch report naming each lane, actor, repository, issue, branch, expected starting SHA, claim state, allowed scope, blockers, and stop conditions. Do not create duplicate claims or broaden a lane to absorb another issue.
```
