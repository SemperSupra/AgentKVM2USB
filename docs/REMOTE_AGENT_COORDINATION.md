# Remote Coordination Protocol

GitHub is the coordination point between the web assistant, local development
agents, and human reviewers. Do not rely on chat transcripts as the only record
of decisions, progress, tests, or unresolved questions.

## Canonical Records

For the input-path program:

- issue #8 is the canonical scope, status, and decision thread;
- `docs/INPUT_PATH_STRATEGY.md` is the canonical technical plan;
- the active implementation pull request is the canonical code review surface;
- commits and test artifacts referenced by the issue or PR are the canonical
  execution record.

The private research repository is used only for restricted captures and
proprietary artifacts. Public implementation work must remain independently
written and must not commit restricted evidence.

## Turn Model

Only one actor should be making implementation decisions at a time.

1. The web assistant reviews the remote repository and records scope or feedback.
2. A local agent fetches the remote state and performs the assigned implementation
   slice.
3. The local agent pushes commits, updates issue #8, and opens or updates a draft
   pull request.
4. The web assistant reviews the issue, commits, diff, tests, and PR discussion.
5. The web assistant records findings and the next bounded implementation slice
   in GitHub before returning the turn to the local agent.

The user should normally need to transfer only the minimal prompt identifying the
repository and canonical issue.

## Local Agent Startup Procedure

The local agent must:

1. clone or fetch `SemperSupra/AgentKVM2USB`;
2. read `AGENTS.md`, `PROJECT_STATUS.md`, issue #8, this document, and
   `docs/INPUT_PATH_STRATEGY.md`;
3. inspect open pull requests and recent issue #8 comments;
4. determine the current assigned phase and acceptance gate from GitHub;
5. create or continue the branch named in the issue or active PR;
6. post a short `START` comment to issue #8 before implementation.

The `START` comment should include:

```text
Actor: <agent/tool>
Branch: <branch>
Base commit: <sha>
Assigned slice: <phase and bounded objectives>
Planned validation: <commands and hardware tests>
Blocked by: <none or explicit blockers>
```

## Work Rules

- Preserve unrelated local changes.
- Do not commit directly to `main`.
- Keep implementation slices bounded by a phase exit gate.
- Do not add firmware, FPGA, EDID, flash, or other persistent device writes.
- Do not infer HID report formats from usage values alone.
- Keep proprietary binaries, raw captures, and decompiled vendor material out of
  this public repository.
- Use structured errors instead of silent exception suppression in new code.
- Add tests with each behavioral change.
- Record target-side validation, not only successful host writes.
- Do not close issue #8 until all phases and the full validation matrix are
  complete.

## Progress Updates

Use issue #8 for cross-session progress, decisions, and blockers. Use the pull
request for code-specific review.

Post a `CHECKPOINT` issue comment after each meaningful slice or when a blocker
changes the plan:

```text
Checkpoint: <short name>
Commits: <sha list>
Completed: <facts>
Validation: <commands and outcomes>
Hardware evidence: <sanitized summary or private artifact IDs>
Decisions needed: <none or explicit questions>
Next: <next bounded step>
```

Do not paste large logs into comments. Commit small sanitized fixtures where
appropriate, attach relevant CI results, or reference private artifact IDs.

## Pull Request Requirements

Open a draft PR as soon as there is a reviewable vertical slice. Link issue #8.
The PR description must include:

- assigned phase and exit gate;
- architecture and files changed;
- backward-compatibility impact;
- USB/HID assumptions and evidence basis;
- tests run and exact outcomes;
- hardware validation performed or still required;
- restricted inputs not used;
- remaining risks and blockers.

Keep the PR draft until the phase exit gate is met and review findings are
resolved.

## Completion Handoff

At the end of the local-agent turn, post a `HANDOFF` comment to issue #8:

```text
Handoff
Branch: <branch>
PR: <number or URL>
Head commit: <sha>
Implemented: <concise summary>
Validation: <commands, counts, and hardware targets>
Known gaps: <explicit list>
Recommended next step: <one bounded step>
Human action required: <none or exact action>
```

Push every intended commit before posting the handoff. The web assistant will
use the remote repository, issue, and PR—not a pasted chat summary—to assess the
work.

## Current First Slice

Unless issue #8 records a newer assignment, the first implementation slice is
**Phase A — Discovery and diagnostics** from `docs/INPUT_PATH_STRATEGY.md`.

Phase A must not alter input report bytes. Its purpose is to establish:

- device profiles;
- complete HID metadata capture;
- physical-device grouping;
- deterministic multi-device selection;
- structured discovery diagnostics;
- tests for missing, duplicate, partial, and multiple-device topologies.
