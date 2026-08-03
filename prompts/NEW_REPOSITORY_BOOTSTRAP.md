# New Repository Governance Bootstrap Prompt

```text
Establish repository-native agent coordination and accurate project metadata for {{REPOSITORY}} immediately after repository creation.

Use the remote GitHub repository as the authoritative coordination, communication, provenance, and status surface. Do not create a chat-only or local-only workflow.

Create a canonical governance issue before implementation. On a bounded issue branch, add project-specific—not generic copied—versions of:
- AGENTS.md;
- docs/REMOTE_AGENT_COORDINATION.md;
- .github/repository-metadata.json;
- .github/agent-handoff.schema.json;
- .github/ISSUE_TEMPLATE/agent-work.yml;
- .github/pull_request_template.md;
- prompts/LOCAL_AGENT_KICKOFF.md;
- prompts/WEB_AGENT_REVIEW.md;
- prompts/NEW_REPOSITORY_BOOTSTRAP.md;
- scripts/render_agent_prompt.py;
- scripts/validate_repository_metadata.py;
- scripts/apply_repository_metadata.py;
- tests for required artifacts, branch discipline, prompt rendering, and metadata drift.

Populate the metadata manifest from the actual project: repository name, purpose, description, topics, visibility, default branch, homepage, capabilities, exclusions, canonical documents, workstreams, related repositories, releases, and public/private evidence boundaries. Do not claim capabilities, packages, integrations, or support states that have not been verified.

Open a draft PR against the default branch. Record START, CHECKPOINT, DECISION, BLOCKER, and HANDOFF in the canonical issue. Validate local files and authenticated remote metadata. Metadata application must require an explicit reviewed action and must fail closed for visibility, archive-state, or other high-risk changes.

The exit gate is reached only when a new terminal or web agent can start with the repository URL and canonical issue number, recover the entire assignment from GitHub, and continue without prior chat history or unpushed local files.
```

Generate a populated copy with:

```bash
python scripts/render_agent_prompt.py bootstrap --repository owner/name
```
