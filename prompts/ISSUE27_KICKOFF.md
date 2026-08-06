# Issue #27 minimal kickoff

Run this from `C:\Users\Mark\Projects\AgentKVM2USB` in the local agent session:

```text
Resume SemperSupra/AgentKVM2USB issue #27 and draft PR #28 from GitHub.

Fetch all remotes and read issue #27, PR #28, AGENTS.md, docs/ACTIVE_WORKSTREAMS.md, docs/ISSUE27_OPERATOR_DEPENDENCY_RUNBOOK.md, and prompts/ISSUE27_OPERATOR_DEPENDENCIES.md from origin/issue-27-operator-dependencies.

Reconcile every AgentKVM2USB worktree without data loss. Fast-forward the clean canonical recovery checkout only. Create or reuse a local tracking branch and isolated worktree for issue-27-operator-dependencies.

Run claim preflight and, if conflict-free, post a four-hour START claim. Execute the canonical prompt. Complete and validate the dependency preparation implementation, but run only -Plan and -WhatIf modes unless I am physically present and explicitly approve a named UAC action.

Do not bypass or copy the minecraft-infra UAC helper. Do not directly install USBPcap. Do not automate vendor login, cookies, license acceptance, capture, target input, recabling, reboot, firmware, FPGA, EDID, flash, or proprietary publication. Do not modify PR #13.

Update issue #27 and PR #28, post CHECKPOINT and HANDOFF, release the claim, and report the exact operator actions and remaining Package Foundry blockers.
```

Preferred worktree setup when absent:

```powershell
git fetch --all --prune --tags
if (-not (git branch --list issue-27-operator-dependencies)) {
    git branch --track issue-27-operator-dependencies origin/issue-27-operator-dependencies
}
if (-not (Test-Path 'C:\Users\Mark\Projects\AgentKVM2USB-worktrees\issue-27-operator-dependencies')) {
    git worktree add 'C:\Users\Mark\Projects\AgentKVM2USB-worktrees\issue-27-operator-dependencies' issue-27-operator-dependencies
}
```
