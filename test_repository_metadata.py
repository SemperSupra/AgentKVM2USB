import json
from pathlib import Path

import scripts.render_agent_prompt as prompt_renderer
import scripts.validate_repository_metadata as validator


ROOT = Path(__file__).resolve().parent


def test_metadata_manifest_is_project_specific_and_complete():
    manifest = json.loads((ROOT / ".github" / "repository-metadata.json").read_text(encoding="utf-8"))
    repo = manifest["repository"]
    project = manifest["project"]

    assert repo["name_with_owner"] == "SemperSupra/AgentKVM2USB"
    assert repo["display_name"] == "AgentKVM2USB"
    assert "Epiphan KVM2USB 3.0" in repo["description"]
    assert repo["default_branch"] == "main"
    assert repo["visibility"] == "public"
    assert {"hid", "kvm", "usb", "uvc", "python"}.issubset(set(repo["topics"]))
    assert project["canonical_workstreams"]["input_path"] == 8
    assert project["canonical_workstreams"]["downstream_hid_recovery"] == 14
    assert project["canonical_workstreams"]["repository_governance"] == 16
    assert project["canonical_prompts"]["local_agent_kickoff"] == "prompts/LOCAL_AGENT_KICKOFF.md"
    assert project["canonical_prompts"]["web_agent_review"] == "prompts/WEB_AGENT_REVIEW.md"
    assert project["canonical_prompts"]["new_repository_bootstrap"] == "prompts/NEW_REPOSITORY_BOOTSTRAP.md"
    assert project["canonical_prompts"]["renderer"] == "scripts/render_agent_prompt.py"


def test_required_coordination_artifacts_exist():
    required = (
        "AGENTS.md",
        "docs/REMOTE_AGENT_COORDINATION.md",
        ".github/repository-metadata.json",
        ".github/agent-handoff.schema.json",
        ".github/ISSUE_TEMPLATE/agent-work.yml",
        ".github/pull_request_template.md",
        "prompts/LOCAL_AGENT_KICKOFF.md",
        "prompts/WEB_AGENT_REVIEW.md",
        "prompts/NEW_REPOSITORY_BOOTSTRAP.md",
        "scripts/render_agent_prompt.py",
        "scripts/validate_repository_metadata.py",
        "scripts/apply_repository_metadata.py",
    )
    for rel in required:
        assert (ROOT / rel).is_file(), rel


def test_prompt_renderer_populates_repository_and_issue():
    local = prompt_renderer.render("local", "SemperSupra/AgentKVM2USB", 16)
    web = prompt_renderer.render("web", "SemperSupra/AgentKVM2USB", 14)
    bootstrap = prompt_renderer.render("bootstrap", "SemperSupra/NewProject", None)

    assert "SemperSupra/AgentKVM2USB" in local
    assert "issue #16" in local.lower()
    assert "SemperSupra/AgentKVM2USB" in web
    assert "issue #14" in web.lower()
    assert "SemperSupra/NewProject" in bootstrap
    assert "{{REPOSITORY}}" not in local + web + bootstrap
    assert "{{ISSUE}}" not in local + web + bootstrap


def test_prompt_renderer_requires_issue_for_workstream_prompts():
    for mode in ("local", "web"):
        try:
            prompt_renderer.render(mode, "SemperSupra/AgentKVM2USB", None)
        except ValueError as exc:
            assert "--issue is required" in str(exc)
        else:
            raise AssertionError(f"{mode} prompt accepted a missing issue")


def test_branch_conventions_are_bounded():
    accepted = (
        "main",
        "issue-16-agent-coordination-governance",
        "governance/agent-coordination",
        "docs/coordination-protocol",
        "release/v0-3-0",
        "hotfix/hid-release-all",
        "recovery/agentkvm2usb-app-capabilities",
    )
    rejected = (
        "feature/misc",
        "agent-work",
        "issue-x-vague",
        "Issue-16-Governance",
        "main-work",
    )
    for branch in accepted:
        assert any(pattern.fullmatch(branch) for pattern in validator.BRANCH_PATTERNS), branch
    for branch in rejected:
        assert not any(pattern.fullmatch(branch) for pattern in validator.BRANCH_PATTERNS), branch


def test_remote_metadata_drift_is_reported():
    manifest = json.loads((ROOT / ".github" / "repository-metadata.json").read_text(encoding="utf-8"))
    remote = {
        "nameWithOwner": "SemperSupra/AgentKVM2USB",
        "description": "generic project",
        "homepageUrl": None,
        "repositoryTopics": [{"name": "python"}],
        "defaultBranchRef": {"name": "master"},
        "visibility": "PUBLIC",
        "isArchived": False,
    }
    errors = []
    warnings = []
    validator.validate_remote(manifest, remote, errors, warnings)
    assert any("description drift" in error for error in errors)
    assert any("default branch drift" in error for error in errors)
    assert any("topics missing" in error for error in errors)


def test_handoff_schema_requires_remote_coordination_identity():
    schema = json.loads((ROOT / ".github" / "agent-handoff.schema.json").read_text(encoding="utf-8"))
    required = set(schema["required"])
    assert {"record_type", "actor", "repository", "issue", "branch", "base_sha", "head_sha"}.issubset(required)
    assert {"validation", "blockers", "next_step", "safety"}.issubset(required)
