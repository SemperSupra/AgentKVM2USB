# Issue #16 Governance Review Closeout

Use this prompt for a local terminal agent after the issue #16 correction pass has been pushed.

```text
Work in SemperSupra/AgentKVM2USB.

Canonical issue: #16
Pull request: #17
Branch: issue-16-agent-coordination-governance

GitHub is authoritative. Reconstruct the assignment from the current issue, PR, reviews, commits, checks, AGENTS.md, PROJECT_STATUS.md, .github/repository-metadata.json, .github/agent-handoff.schema.json, and docs/REMOTE_AGENT_COORDINATION.md. Do not treat this prompt, chat history, terminal history, or a machine-local worktree path as authoritative.

The last known reviewed head when this prompt was added was 35efdfff9d013ab84280bb020fa0d65b5fcbf15b. Fetch first and use the actual current remote head if it has advanced.

Current purpose: review and close out PR #17. Do not repeat completed corrections unless current remote review identifies a defect. The completed correction areas are:
- remote branch claim/lease lifecycle;
- current PROJECT_STATUS.md workstream snapshot;
- evidence-conservative repository capability metadata.

Before making any change:
1. Verify the intended worktree is clean; do not discard, stash, reset, or overwrite unknown changes.
2. Fetch origin and fast-forward only.
3. Read the latest issue #16 comments and PR #17 reviews.
4. Confirm the latest claim for the branch is released, transferred to you, or expired. Fail closed on an unexpired conflicting claim.
5. Compare the actual remote branch head with the expected head recorded in any active claim.

If no new implementation assignment exists, do not create commits merely to show activity. Report that PR #17 is awaiting remote review and leave the branch unchanged.

If a bounded correction is assigned:
- post START with a unique claim_id, active state, expected_remote_head, UTC claim time, and finite lease expiry;
- implement only the assigned correction;
- fetch and compare the remote head immediately before every normal non-force push;
- run the exact tests required by the issue and PR;
- update the PR body to the final head and exact evidence;
- post CHECKPOINT as needed and HANDOFF releasing or explicitly transferring the claim.

For final validation, use the current repository instructions. At minimum review or run, when applicable:
- python -m compileall -q scripts test_repository_metadata.py
- python -m pytest -q
- python scripts/render_agent_prompt.py local --issue 16
- python scripts/render_agent_prompt.py web --issue 16
- python scripts/validate_repository_metadata.py --remote off
- python scripts/validate_repository_metadata.py --remote required
- python scripts/apply_repository_metadata.py
- git diff --check

Do not modify PR #13 or PR #15 branches. Do not perform hardware operations, target input reports, firmware/FPGA/EDID/flash writes, host-software installation, force pushes, or destructive worktree cleanup.
```
