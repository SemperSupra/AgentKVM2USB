# Web Agent Review and Assignment Prompt

```text
Review {{REPOSITORY}} using only current remote GitHub state.

Canonical issue: #{{ISSUE}}

Read AGENTS.md, PROJECT_STATUS.md, .github/repository-metadata.json, docs/REMOTE_AGENT_COORDINATION.md, the issue body and latest comments, linked issues, active PRs, reviews, commits, checks, and relevant tracked documents.

Determine:
- the current work owner and branch;
- the latest valid claim for the branch (claim_id, claim_state, expected_remote_head, lease expiry) and whether it is active, renewed, released, transferred, or expired;
- the latest remote head and base;
- the assigned bounded slice and exit gate;
- implemented changes and exact validation evidence;
- unresolved review findings, blockers, dependencies, metadata drift, and human actions;
- whether safety and evidence boundaries were observed;
- whether the PR title, body, labels, links, and draft state accurately describe the current project state.

Do not evaluate from pasted chat summaries when remote evidence is available. Compare claims against commits, files, issue comments, PR discussion, and checks. Correct stale issue or PR metadata when authorized.

Publish every material conclusion to GitHub. Use a PR review for code-specific findings and the canonical issue for decisions, blockers, ownership transfers, and the next bounded assignment. Do not leave the local terminal agent dependent on this chat.

When assigning another terminal-agent turn, record a concise bounded slice in issue #{{ISSUE}} that includes branch/base/head, objectives, exclusions, validation, exit gate, safety constraints, the claim/lease expectation, and required START/CHECKPOINT/HANDOFF records. The next actor must be able to continue with only {{REPOSITORY}} and issue #{{ISSUE}}.
```

Generate a populated copy with:

```bash
python scripts/render_agent_prompt.py web --issue <number>
```
