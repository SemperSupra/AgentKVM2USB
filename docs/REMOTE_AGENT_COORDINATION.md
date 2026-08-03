# Remote Agent Coordination Protocol

GitHub is the authoritative coordination, communication, provenance, and status surface between the web assistant, local terminal agents, automation, and human reviewers.

This protocol applies to every AgentKVM2USB workstream. Workstream-specific issues may add stricter requirements, but they may not move required coordination into private chat or local-only state.

## Authority Model

The following records are authoritative, in descending order of specificity:

1. the canonical issue for the workstream;
2. accepted decisions and current assignments in that issue's comments;
3. the active branch and pull request;
4. reviewed commits, tests, checks, releases, and linked evidence records;
5. tracked project documents and metadata manifests.

Chat transcripts, terminal output that was not published, and an agent's private memory are not authoritative. An actor may use them as working context but must publish every material fact needed by the next actor.

## Canonical Records Per Workstream

Every workstream requires:

- one canonical issue for purpose, scope, constraints, current state, decisions, blockers, dependencies, artifacts, and exit criteria;
- one bounded branch per active implementation slice;
- one draft PR as the code and document review surface;
- linked commits and deterministic validation evidence;
- issue comments for cross-session coordination;
- PR review threads for file- and code-specific findings.

The canonical issue must link related repositories and their corresponding issues or PRs when work crosses repository boundaries.

## Turn Ownership and Concurrency

Only one actor owns an implementation branch at a time.

A normal turn proceeds as follows:

1. The web agent reads remote state and records a bounded assignment or review in GitHub.
2. The local terminal agent fetches remote state, confirms ownership, and posts `START`.
3. The local agent implements only the assigned slice, commits, pushes, and maintains the draft PR.
4. The local agent posts `CHECKPOINT`, `BLOCKER`, or `HANDOFF` with remote SHAs and validation.
5. The web agent reviews only remote repository state and records the next decision or slice.

Parallel work is allowed only when the canonical issue explicitly partitions it into separate issues or sub-issues, branches, and PRs. Two agents must not make concurrent implementation decisions on the same branch.

Ownership transfers must be explicit in the canonical issue and include the branch, head SHA, PR, unresolved work, and new owner.

## Branch Discipline

- Do not commit directly to `main` or another integration branch.
- Ordinary branches use `issue-<number>-<bounded-purpose>`.
- Approved governance, documentation, release, and emergency branches may use `governance/<purpose>`, `docs/<purpose>`, `release/<purpose>`, or `hotfix/<purpose>` when linked to a canonical issue.
- A branch contains one coherent implementation slice.
- Unrelated work requires another issue and branch.
- Never force-push a shared branch without an explicit issue decision and recovery plan.
- Do not modify another active worktree or PR without an ownership transfer.

## Required Coordination Records

Use these uppercase record types in the canonical issue.

### START

Post before material work:

```text
START
Actor/tool: <name and version>
Environment: <host, OS, worktree>
Issue: #<number>
Branch: <branch>
Base SHA: <sha>
Starting head: <sha>
PR: <number or not opened>
Assigned slice: <bounded objectives>
Planned validation: <commands and hardware gates>
Known blockers: <none or explicit list>
Safety boundary: <prohibited actions>
```

### CHECKPOINT

Post after a meaningful slice or before changing the plan:

```text
CHECKPOINT
Actor/tool: <actor>
Branch/head: <branch>@<sha>
Commits: <sha list>
Completed: <facts>
Changed paths: <paths>
Validation: <commands and outcomes>
Artifacts: <locations, classifications, hashes>
Decisions: <decisions and authority>
Blockers: <none or explicit list>
Next: <one bounded step>
```

### DECISION

Use for material design, dependency, security, safety, scope, or acceptance decisions:

```text
DECISION
Question: <what was decided>
Decision: <selected outcome>
Authority: <human approval, issue acceptance, specification, or evidence>
Evidence: <links and hashes>
Alternatives rejected: <brief list>
Consequences: <implementation, risk, and follow-up>
```

### BLOCKER

Use when progress stops or an assumption is disproved:

```text
BLOCKER
Branch/head: <branch>@<sha>
Blocked operation: <exact operation>
Observed evidence: <facts and logs/artifacts>
Impact: <what cannot proceed>
Safe work still possible: <bounded alternatives>
Human action required: <exact action or none>
```

### HANDOFF

Post before ending an agent turn:

```text
HANDOFF
Actor/tool and environment: <identity>
Branch: <branch>
PR: <number or URL>
Base/head: <base sha>..<head sha>
Implemented: <concise summary>
Validation: <commands, counts, and hardware targets>
Artifacts: <locations, classifications, hashes>
Decisions: <decision references>
Known gaps/blockers: <explicit list>
Human action required: <none or exact action>
Safety confirmation: <prohibited actions not performed>
Recommended next step: <one bounded step>
```

`.github/agent-handoff.schema.json` defines the machine-readable equivalent. Structured JSON may be attached or committed when useful, but the issue comment must remain understandable to a human reviewer.

## Pull Request Discipline

Open a draft PR as soon as there is a reviewable vertical slice.

The PR body must remain current and include:

- canonical issue and assigned slice;
- exit gate;
- architecture and changed paths;
- evidence basis and repository boundaries;
- exact validation results;
- hardware validation completed or required;
- compatibility, security, and safety effects;
- metadata changes;
- remaining blockers and human actions;
- latest branch head.

Use the PR for code-specific review. Use the canonical issue for cross-agent assignment, decisions, blockers, and handoff.

A PR remains draft until its issue exit gate is met and requested changes are resolved. Do not use a stale PR description as a historical log; keep the body accurate and use comments/commits for history.

## Metadata Governance

`.github/repository-metadata.json` defines the expected project-specific identity and canonical document locations.

Metadata includes:

- repository name, description, topics, visibility, homepage, archived state, and default branch;
- README and package/application identity;
- current supported capabilities and explicit exclusions;
- issue/PR titles, bodies, labels, milestones, dependencies, and states;
- release versions, notes, assets, checksums, and support status;
- canonical status, safety, coordination, and technical documents;
- related repository relationships.

Run:

```bash
python scripts/validate_repository_metadata.py --remote auto
```

Use `--remote required` for a release or metadata-governance gate when authenticated `gh` access is expected. The validator reports drift; it does not silently change GitHub settings.

When creating a new repository, populate the manifest with the actual project identity before copying templates. Generic or irrelevant topics, descriptions, issue forms, and release text are defects.

## Evidence and Provenance

Every material artifact should have:

- a stable repository or approved private evidence location;
- source and acquisition method;
- timestamp;
- producing actor/tool and version;
- hash when practical;
- public, sanitized, or private-reference classification;
- links from the canonical issue or PR.

Do not paste large raw logs into comments. Commit small sanitized fixtures, attach approved artifacts, cite CI results, or reference private artifact IDs and hashes.

Proprietary binaries, restricted captures, credentials, personal data, and raw decompiled vendor material must not enter a public repository.

## Cross-Repository Work

When a workstream spans repositories:

- create or identify a canonical issue in each affected repository;
- link both directions;
- state which repository owns the authoritative design or interface;
- use separate branches and PRs per repository;
- record dependency order and compatible commit/release identifiers;
- do not depend on unpushed local files;
- do not declare completion until each repository's metadata and coordination records are current.

## Local Agent Startup

A terminal agent must:

1. clone or fetch the remote repository;
2. fetch all relevant branches and PR refs;
3. read `AGENTS.md`, `PROJECT_STATUS.md`, `.github/repository-metadata.json`, this document, the canonical issue, and linked PRs;
4. confirm branch ownership and remote head;
5. inspect recent issue and PR comments for assignments, requested changes, decisions, and blockers;
6. create or reuse the issue branch without disturbing unrelated work;
7. post `START` before implementation.

If remote state is incomplete or contradictory, post `BLOCKER` or `DECISION NEEDED` to the canonical issue rather than resolving the discrepancy privately.

## End-of-Turn Gate

A local agent turn is incomplete until:

- intended commits are pushed;
- the draft PR body reflects the current head;
- tests and hardware evidence are recorded;
- artifacts and hashes are referenced;
- blockers and human actions are explicit;
- a `HANDOFF` is posted;
- the next actor can continue from GitHub alone.

## Current Canonical Workstreams

The machine-readable metadata manifest is authoritative for current mappings. At the time this protocol was generalized:

- issue #8 coordinates profile-driven input-path work;
- issue #14 coordinates downstream HID forwarding and activation recovery;
- issue #16 coordinates repository-native agent governance and metadata.
