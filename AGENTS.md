# Instructions for AI Agents

These instructions govern web agents, local terminal agents, automation, and human-assisted agent sessions working on AgentKVM2USB.

## Core Purpose

AgentKVM2USB is an independently written Python SDK and automation toolkit for Epiphan KVM2USB 3.0 hardware. It supports video capture and hardware KVM input research through standard HID and UVC interfaces.

## GitHub Is the Authoritative Coordination Surface

All durable coordination and communication between agents must occur through the remote GitHub repository after it exists.

Chat transcripts and local notes are not authoritative. They must never be the only record of:

- scope or assignments;
- design or safety decisions;
- progress and blockers;
- validation results;
- artifacts and provenance;
- ownership transfers;
- completion handoffs.

Every workstream must have a canonical issue, a bounded branch, and a draft pull request as soon as a reviewable slice exists. Use issue comments for cross-agent coordination and PR reviews for code-specific findings.

Read `docs/REMOTE_AGENT_COORDINATION.md` before beginning work.

## Required Startup Procedure

Before changing files, an agent must:

1. fetch the remote repository and all relevant branches;
2. read this file, `PROJECT_STATUS.md`, and `.github/repository-metadata.json`;
3. read the canonical issue body and its latest comments;
4. inspect linked and active pull requests, reviews, commits, and checks;
5. confirm the assigned branch, base commit, scope, exit gate, safety boundary, and current owner;
6. preserve unrelated local changes and avoid modifying another active worktree or PR;
7. post a `START` record to the canonical issue before material work.

A local agent must be able to recover the complete assignment from the repository URL and canonical issue number without chat history.

## Workstream and Branch Discipline

- Never commit directly to `main` or another integration branch.
- Use `issue-<number>-<bounded-purpose>` for ordinary workstreams.
- Use an approved namespaced branch such as `governance/<purpose>`, `docs/<purpose>`, `release/<purpose>`, or `hotfix/<purpose>` only when the canonical issue explains why.
- One implementation owner may modify a bounded branch at a time.
- Parallel work requires separate issues or explicit sub-issues and separate branches.
- Do not broaden scope inside an existing PR. Open another issue and branch.
- Do not alter another active PR unless the canonical issue records an ownership transfer.
- Open or update a draft PR before ending a local-agent turn when any reviewable change exists.
- Keep PR titles and bodies synchronized with the current head, validation state, risks, and blockers.

## Coordination Records

Post the following records to the canonical issue:

- `START` before material work;
- `CHECKPOINT` after a meaningful slice;
- `DECISION` when resolving a material design, safety, dependency, or scope question;
- `BLOCKER` when progress stops or the plan must change;
- `HANDOFF` before ending the agent turn.

Each record must identify the actor/tool and environment, issue, branch, base/head SHA, PR, assigned slice, changed paths, validation, artifacts, decisions, blockers, human actions, safety confirmation, and one next bounded step.

Use `.github/agent-handoff.schema.json` as the machine-readable field definition. A Markdown issue comment may include or link a JSON record conforming to that schema.

Push every intended commit before posting `HANDOFF`. The remote repository, not the local checkout, is the source of truth for the next actor.

## Metadata Discipline

Project metadata must remain accurate and project-specific.

- Treat `.github/repository-metadata.json` as the expected metadata manifest.
- Update README, status, package, release, issue, PR, and repository metadata when capabilities or support status change.
- Do not copy generic descriptions, topics, or templates that claim unsupported capabilities.
- Run `python scripts/validate_repository_metadata.py --remote auto` for governance, release, and material capability changes.
- The validator reports drift and must not silently rewrite GitHub metadata.
- Record intentional metadata differences in the canonical issue and update the manifest or remote metadata through a reviewed change.

## Evidence and Repository Boundaries

- Do not commit credentials, personal data, proprietary binaries, restricted captures, or raw decompiled vendor material.
- Public repositories contain sanitized facts, independently written code, manifests, hashes, references, and conclusions.
- Restricted evidence belongs in an approved private evidence repository and is referenced by stable artifact ID and hash where permitted.
- Do not make another repository depend on unpushed local files or undocumented chat context.
- Cross-repository work must link the relevant issues and PRs in both repositories.

## Hardware and Safety Boundary

- Treat firmware flashing, FPGA updates, EDID writes, user-mode writes, raw USB vendor OUT transfers, and other persistent device changes as high risk.
- Do not perform them unless the canonical issue contains explicit human approval and a hardware-safe test and recovery plan.
- Read `PROJECT_STATUS.md` before hardware actions.
- Record target-side receipt or observation, not only successful host API calls.
- Keep screenshots, recordings, SRT files, raw captures, and session logs out of commits unless they are intentionally sanitized fixtures.

## Utilizing the Macro Engine

For supported sequential actions, use the Macro Engine (`sdk.run_macro()`) rather than issuing individual calls across a remote boundary.

### Macro Engine Benefits

- **Reliability:** timing is handled locally rather than across agent/network latency;
- **Auditability:** one script records the full input sequence;
- **Suitability:** multi-step BIOS and setup routines can be reviewed before execution.

Example:

```python
routine = """
PRESS f2
DELAY 1000
PRESS down
PRESS enter
TYPE password
PRESS enter
"""
sdk.run_macro(routine)
```

Review `MACROS.md` for supported commands. Do not assume the macro engine proves target-side input receipt.

## Operational Guidelines

- Verify target signal and device status before interaction.
- Use `sdk.get_screen()` for current frames when screen evidence is required.
- Treat click coordinates as normalized values from `0.0` to `1.0` where the selected codec supports absolute input.
- Prefer explicit profile and capability checks over assumptions based on product names or HID usage alone.
- Use structured errors instead of silent exception suppression.
- Add deterministic tests with each behavioral change.

## Canonical Workstreams

The current project metadata manifest identifies canonical issues. At present:

- issue #8 coordinates the profile-driven input-path program;
- issue #14 coordinates downstream HID forwarding and activation recovery;
- issue #16 coordinates repository-native agent governance and metadata.

Before working on a workstream, read its canonical issue, latest comments, linked strategy documents, and active PR. The issue may supersede older instructions in this file for that bounded scope.

## End-of-Turn Rule

A local terminal agent must not finish with only a console summary. Before ending, it must:

1. commit and push all intended changes;
2. update the draft PR body and review state;
3. post a complete `CHECKPOINT`, `BLOCKER`, or `HANDOFF` to the canonical issue;
4. confirm prohibited actions not performed;
5. leave one bounded next step that another actor can execute using only GitHub.
