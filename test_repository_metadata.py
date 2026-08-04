import json
from pathlib import Path
import subprocess

import scripts.apply_repository_metadata as applier
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


def test_homepage_null_and_empty_are_equivalent():
    # GitHub returns "" for no homepage; the manifest uses null. Both are the
    # same "no homepage" state and must not be reported as drift.
    manifest = json.loads((ROOT / ".github" / "repository-metadata.json").read_text(encoding="utf-8"))
    remote = {
        "nameWithOwner": "SemperSupra/AgentKVM2USB",
        "description": manifest["repository"]["description"],
        "homepageUrl": "",  # remote empty string
        "repositoryTopics": [{"name": t} for t in manifest["repository"]["topics"]],
        "defaultBranchRef": {"name": "main"},
        "visibility": "PUBLIC",
        "isArchived": False,
    }
    errors = []
    warnings = []
    validator.validate_remote(manifest, remote, errors, warnings)
    assert not errors, errors
    # Normalizers agree on the None/"" state.
    assert validator._homepage_equivalent(None) == validator._homepage_equivalent("")
    assert applier.homepage_equivalent(None) == applier.homepage_equivalent("")


def test_apply_refuses_visibility_drift(tmp_path, monkeypatch):
    import subprocess as _sp

    manifest = json.loads((ROOT / ".github" / "repository-metadata.json").read_text(encoding="utf-8"))
    repo_view = _sp.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps({
            "nameWithOwner": "SemperSupra/AgentKVM2USB",
            "description": manifest["repository"]["description"],
            "homepageUrl": "",
            "repositoryTopics": [{"name": t} for t in manifest["repository"]["topics"]],
            "defaultBranchRef": {"name": "main"},
            "visibility": "PRIVATE",  # drift: manifest says public
            "isArchived": False,
        }),
        stderr="",
    )
    monkeypatch.setattr(applier.shutil, "which", lambda name: "gh" if name == "gh" else None)
    monkeypatch.setattr(applier, "run", lambda argv, cwd: repo_view)
    # Apply must fail closed and never call gh repo edit for visibility drift.
    rc = applier.main(["--root", str(ROOT), "--apply"])
    assert rc == 3


def test_apply_refuses_archived_drift(tmp_path, monkeypatch):
    import subprocess as _sp

    manifest = json.loads((ROOT / ".github" / "repository-metadata.json").read_text(encoding="utf-8"))
    repo_view = _sp.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps({
            "nameWithOwner": "SemperSupra/AgentKVM2USB",
            "description": manifest["repository"]["description"],
            "homepageUrl": "",
            "repositoryTopics": [{"name": t} for t in manifest["repository"]["topics"]],
            "defaultBranchRef": {"name": "main"},
            "visibility": "PUBLIC",
            "isArchived": True,  # drift: manifest says not archived
        }),
        stderr="",
    )
    monkeypatch.setattr(applier.shutil, "which", lambda name: "gh" if name == "gh" else None)
    monkeypatch.setattr(applier, "run", lambda argv, cwd: repo_view)
    rc = applier.main(["--root", str(ROOT), "--apply"])
    assert rc == 3


def test_prompts_require_remote_reconstruction_and_handoff():
    local = (ROOT / "prompts" / "LOCAL_AGENT_KICKOFF.md").read_text(encoding="utf-8")
    web = (ROOT / "prompts" / "WEB_AGENT_REVIEW.md").read_text(encoding="utf-8")
    bootstrap = (ROOT / "prompts" / "NEW_REPOSITORY_BOOTSTRAP.md").read_text(encoding="utf-8")

    # Startup must reconstruct the assignment from remote GitHub state and post START.
    assert "remote GitHub repository is the authoritative" in local
    assert "solely from remote GitHub state" in local
    assert "Post a START record" in local
    assert "do not rely on this prompt, prior chat" in local.lower()
    assert "as authoritative" in local.lower()
    # End of turn must require pushed commits, PR body sync, and a HANDOFF record.
    assert "Push every intended commit" in local
    assert "Update the draft PR body" in local
    assert "HANDOFF" in local
    # Web review must rely on current remote state, not pasted chat.
    assert "only current remote GitHub state" in web
    assert "Do not evaluate from pasted chat summaries" in web
    # Bootstrap must require project-specific metadata, not generic copied text.
    assert "project-specific—not generic copied" in bootstrap
    assert "fail closed for visibility" in bootstrap


def test_topics_are_relevant_and_non_generic():
    manifest = json.loads((ROOT / ".github" / "repository-metadata.json").read_text(encoding="utf-8"))
    topics = set(manifest["repository"]["topics"])
    generic = {"awesome", "example", "demo", "test", "misc", "project"}
    assert not (topics & generic), topics & generic
    # Project-specific hardware/domain topics are present.
    assert {"epiphan", "kvm", "hid", "uvc", "usb"}.issubset(topics)
    for topic in topics:
        assert topic.islower() and topic.replace("-", "").isalnum(), topic
