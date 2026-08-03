# Local Terminal Agent Kickoff

Paste this prompt into a local terminal agent after replacing the two required placeholders.

```text
You are working on {{REPOSITORY}}.

Canonical GitHub issue: #{{ISSUE}}

The remote GitHub repository is the authoritative coordination, communication, provenance, and status surface. Do not rely on this prompt, prior chat, terminal history, or local notes as authoritative after startup.

Before changing anything:
1. Clone or fetch the repository and all relevant branches and PR refs.
2. Read AGENTS.md, PROJECT_STATUS.md, .github/repository-metadata.json, and docs/REMOTE_AGENT_COORDINATION.md.
3. Read issue #{{ISSUE}}, its latest comments, linked issues, active PRs, reviews, commits, and checks.
4. Determine the current owner, bounded assignment, branch, base/head SHAs, exit gate, dependencies, safety boundary, and required artifacts solely from remote GitHub state.
5. Preserve unrelated local changes and do not modify another active worktree, branch, or PR without an ownership transfer recorded in the canonical issue.
6. Post a START record to issue #{{ISSUE}} before material work.

Work only on the bounded slice assigned in GitHub. Use an issue branch such as issue-{{ISSUE}}-<bounded-purpose>, or continue the branch named by the active PR. Open or update a draft PR as soon as a reviewable slice exists. Keep the PR title and body synchronized with its current head, exact validation, risks, blockers, metadata effects, and exit gate.

Use GitHub issue comments for START, CHECKPOINT, DECISION, BLOCKER, and HANDOFF records. Use PR reviews and threads for code-specific findings. Push every intended commit before posting HANDOFF. Do not leave required decisions, validation, blockers, artifact locations, or next steps only in terminal output.

Run the validation required by the canonical issue and relevant project documents. Record exact commands, outcomes, artifact paths, hashes, target-side observations, and prohibited actions not performed. Keep restricted evidence, credentials, proprietary binaries, personal data, raw captures, and decompiled vendor material out of the public repository.

Before ending the turn:
1. Push all intended commits.
2. Update the draft PR body and review state.
3. Post CHECKPOINT, BLOCKER, or HANDOFF to issue #{{ISSUE}} with branch, base/head SHAs, PR, changed paths, validation, artifacts, decisions, blockers, human actions, safety confirmation, and one bounded next step.
4. Ensure the next web or terminal agent can continue using only the remote repository and issue number.
```

Generate a populated copy with:

```bash
python scripts/render_agent_prompt.py local --issue <number>
```
