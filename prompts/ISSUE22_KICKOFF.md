# Issue #22 minimal kickoff

Run this from `C:\Users\Mark\Projects\AgentKVM2USB` in the local agent session:

```text
Resume SemperSupra/AgentKVM2USB issue #22 from GitHub.

Fetch all remotes and read issue #22, draft PR #26, AGENTS.md, docs/REMOTE_AGENT_COORDINATION.md, and prompts/ISSUE22_WORKSTATION_CAPTURE_DEPS.md from origin/issue-22-workstation-capture-deps.

Reconcile all worktrees without data loss. Fast-forward the clean canonical recovery checkout only. If no local issue-22 branch exists, create a tracking branch from origin/issue-22-workstation-capture-deps; then create or reuse the isolated issue-22 worktree.

Run claim preflight and, if conflict-free, post a four-hour START claim. Execute the canonical prompt exactly. Validate the new work package and run the read-only readiness collector. Do not install, elevate, capture, send input, recable, modify PR #7 or PR #13, or perform persistent device writes.

Update issue #22 and PR #26, post CHECKPOINT and HANDOFF, release the claim, and report the exact human actions required next.
```

Equivalent manual branch/worktree setup when absent:

```powershell
git fetch --all --prune --tags
if (-not (git branch --list issue-22-workstation-capture-deps)) {
    git branch --track issue-22-workstation-capture-deps origin/issue-22-workstation-capture-deps
}
if (-not (Test-Path 'C:\Users\Mark\Projects\AgentKVM2USB-worktrees\issue-22-workstation-capture-deps')) {
    git worktree add 'C:\Users\Mark\Projects\AgentKVM2USB-worktrees\issue-22-workstation-capture-deps' issue-22-workstation-capture-deps
}
```
