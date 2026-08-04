import datetime as dt
import json
from pathlib import Path
import subprocess

import scripts.apply_repository_metadata as applier
import scripts.claim_preflight as preflight
import scripts.render_agent_prompt as prompt_renderer
import scripts.validate_repository_metadata as validator


ROOT = Path(__file__).resolve().parent


def _base_claim(**overrides):
    claim = {
        "claim_id": "claim-1",
        "claim_state": "active",
        "actor": {"name": "test-agent", "environment": "test"},
        "repository": "SemperSupra/AgentKVM2USB",
        "issue": 16,
        "branch": "issue-16-agent-coordination-governance",
        "pull_request": 17,
        "expected_remote_head": "7b60c6c1c67f9b1a147d07bd25f3bdf40cce2f17",
        "claimed_at_utc": "2026-08-04T01:00:00+00:00",
        "lease_expires_utc": "2026-08-04T05:00:00+00:00",
        "assigned_slice": "test slice",
    }
    claim.update(overrides)
    return claim


def _now():
    return dt.datetime(2026, 8, 4, 2, 0, 0, tzinfo=dt.timezone.utc)


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
        "scripts/claim_preflight.py",
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


# --------------------------------------------------------------------------- claim/lease protocol


def test_new_valid_claim_is_active():
    claim = _base_claim()
    assert preflight.validate_claim_identity(claim) == []
    assert preflight.claim_is_active(claim, _now()) is True
    assert preflight.preflight_before_work(existing_claims=[], branch=claim["branch"], now_utc=_now())["allowed"] is True


def test_renewal_uses_same_claim_id_and_extends_expiry():
    claim = _base_claim()
    new_expiry = preflight.renewal_expiry(claim, now_utc=_now())
    renewed = dict(claim, claim_state="renewed", lease_expires_utc=new_expiry)
    # Same claim_id; expiry extended past the original.
    assert renewed["claim_id"] == claim["claim_id"]
    assert dt.datetime.fromisoformat(new_expiry) > dt.datetime.fromisoformat(claim["lease_expires_utc"])
    assert preflight.claim_is_active(renewed, _now()) is True


def test_explicit_release_is_not_active():
    claim = dict(_base_claim(), claim_state="released")
    assert preflight.claim_is_active(claim, _now()) is False


def test_explicit_transfer_is_not_active_for_old_actor():
    claim = dict(_base_claim(), claim_state="transferred", actor={"name": "next-agent", "environment": "other"})
    assert preflight.claim_is_active(claim, _now()) is False


def test_expired_claim_permits_new_owner():
    expired = dict(_base_claim(), lease_expires_utc="2026-08-04T00:30:00+00:00")
    assert preflight.claim_is_active(expired, _now()) is False
    result = preflight.preflight_before_work(existing_claims=[expired], branch=expired["branch"], now_utc=_now())
    assert result["allowed"] is True


def test_unexpired_conflicting_claim_fails():
    active = _base_claim()
    result = preflight.preflight_before_work(existing_claims=[active], branch=active["branch"], now_utc=_now())
    assert result["allowed"] is False
    assert "unexpired claim" in result["reason"]


def test_changed_remote_head_fails_before_push():
    claim = _base_claim()
    result = preflight.preflight_before_push(
        claim=claim,
        actual_remote_head="deadbeef0123456789abcdef0123456789abcdef",
        expected_remote_head=claim["expected_remote_head"],
        now_utc=_now(),
    )
    assert result["allowed"] is False
    assert any("head changed unexpectedly" in e for e in result["errors"])


def test_missing_claim_identity_or_expiry_fails_schema():
    errors = preflight.validate_claim_identity({})
    assert any("missing required claim field" in e for e in errors)
    incomplete = _base_claim(lease_expires_utc="")
    errors2 = preflight.validate_claim_identity(incomplete)
    assert any("lease_expires_utc must be a valid ISO-8601" in e for e in errors2)


def test_indefinite_claims_rejected():
    # A claim without an expiry, or one far in the future beyond the ceiling,
    # must be rejected.
    no_expiry = _base_claim(lease_expires_utc=None)
    errors = preflight.validate_claim_identity(no_expiry)
    assert any("lease_expires_utc must be a valid ISO-8601" in e for e in errors)
    far_future = _base_claim(lease_expires_utc="2099-01-01T00:00:00+00:00")
    errors2 = preflight.validate_claim_identity(far_future)
    assert any("ceiling" in e for e in errors2)


def test_worktree_path_is_optional_and_non_authoritative():
    claim = preflight.build_claim(
        claim_id="c-1", actor="agent-a", repository="SemperSupra/AgentKVM2USB",
        issue=16, branch="issue-16-agent-coordination-governance", pull_request=17,
        expected_remote_head="7b60c6c1c67f9b1a147d07bd25f3bdf40cce2f17",
        claimed_at_utc="2026-08-04T01:00:00+00:00",
        lease_expires_utc="2026-08-04T05:00:00+00:00",
        assigned_slice="slice", worktree_path=r"C:\some\machine\local\path",
    )
    assert claim["worktree_path"]["authoritative"] is False
    # A claim without a worktree path is fully valid.
    no_path = preflight.build_claim(
        claim_id="c-2", actor="agent-a", repository="SemperSupra/AgentKVM2USB",
        issue=16, branch="issue-16-agent-coordination-governance", pull_request=17,
        expected_remote_head="7b60c6c1c67f9b1a147d07bd25f3bdf40cce2f17",
        claimed_at_utc="2026-08-04T01:00:00+00:00",
        lease_expires_utc="2026-08-04T05:00:00+00:00",
        assigned_slice="slice",
    )
    assert "worktree_path" not in no_path
    assert preflight.validate_claim_identity(no_path) == []


def test_handoff_schema_defines_claim_lease_fields():
    schema = json.loads((ROOT / ".github" / "agent-handoff.schema.json").read_text(encoding="utf-8"))
    claim = schema["properties"]["claim"]
    assert claim["type"] == "object"
    assert {"claim_id", "claim_state", "expected_remote_head", "claimed_at_utc", "lease_expires_utc"}.issubset(claim["required"])
    assert "active" in claim["properties"]["claim_state"]["enum"]
    assert "expired" in claim["properties"]["claim_state"]["enum"]
    # A worktree path, if present, must be explicitly non-authoritative.
    assert claim["properties"]["worktree_path"]["properties"]["authoritative"]["const"] is False


def test_prompts_require_claim_checks_before_work_and_push():
    local = (ROOT / "prompts" / "LOCAL_AGENT_KICKOFF.md").read_text(encoding="utf-8")
    web = (ROOT / "prompts" / "WEB_AGENT_REVIEW.md").read_text(encoding="utf-8")
    bootstrap = (ROOT / "prompts" / "NEW_REPOSITORY_BOOTSTRAP.md").read_text(encoding="utf-8")
    # Before-work claim preflight and before-push remote-head check.
    assert "claim preflight" in local.lower()
    assert "fail closed if another actor holds an unexpired claim" in local.lower()
    assert "before every push" in local.lower() and "non-force push" in local.lower()
    assert "claim_id" in local.lower()
    # Web review must evaluate the branch claim/lease state.
    assert "latest valid claim" in web.lower() and "lease expiry" in web.lower()
    # Bootstrap must include the claim helper and release/transfer semantics.
    assert "scripts/claim_preflight.py" in bootstrap
    assert "releasing or transferring the claim" in bootstrap.lower()


def test_no_instruction_permits_force_push_or_hard_reset():
    docs = (
        (ROOT / "AGENTS.md").read_text(encoding="utf-8").lower(),
        (ROOT / "docs" / "REMOTE_AGENT_COORDINATION.md").read_text(encoding="utf-8").lower(),
        (ROOT / "prompts" / "LOCAL_AGENT_KICKOFF.md").read_text(encoding="utf-8").lower(),
    )
    joined = "\n".join(docs)
    # The protocol forbids force-push of shared work; normal push is required.
    assert "never force-push" in joined or "do not force-push" in joined
    assert "non-force push" in joined
    assert "hard reset" not in joined


def test_project_status_mentions_registered_canonical_workstreams():
    manifest = json.loads((ROOT / ".github" / "repository-metadata.json").read_text(encoding="utf-8"))
    status = (ROOT / "PROJECT_STATUS.md").read_text(encoding="utf-8")
    workstreams = manifest["project"]["canonical_workstreams"]
    for role, issue in workstreams.items():
        assert f"#{issue}" in status, f"PROJECT_STATUS.md must mention issue #{issue} ({role})"
    # The status document must state it is a snapshot superseded by remote state.
    assert "supersedes" in status.lower()
    assert "last reviewed" in status.lower()


def test_project_status_does_not_refer_to_obsolete_work_as_active():
    status = (ROOT / "PROJECT_STATUS.md").read_text(encoding="utf-8")
    # Issue #5 / PR #6 were the prior package-foundry work and are no longer active.
    assert "**not** active work" in status
    # The status must name all three active workstream issues and their PRs.
    for issue, pr in (("#8", "#13"), ("#14", "#15"), ("#16", "#17")):
        assert issue in status and pr in status


def test_closeout_prompt_registered_in_manifest():
    manifest = json.loads((ROOT / ".github" / "repository-metadata.json").read_text(encoding="utf-8"))
    prompts = manifest["project"]["canonical_prompts"]
    assert prompts["issue16_review_closeout"] == "prompts/ISSUE16_REVIEW_CLOSEOUT.md"
    # The registered closeout prompt must actually exist.
    assert (ROOT / prompts["issue16_review_closeout"]).is_file()


def test_project_status_no_longer_undergoing_correction():
    status = (ROOT / "PROJECT_STATUS.md").read_text(encoding="utf-8")
    # The #16 row must state corrections are complete and the PR is in final
    # documentation validation/review, not still "undergoing correction".
    assert "governance corrections complete" in status.lower()
    assert "final documentation validation/review" in status.lower()
    assert "undergoing the governance correction pass" not in status.lower()
    # The validated implementation head 35efdff is recorded and readers are
    # directed to PR #17 for the authoritative current head.
    assert "35efdff" in status
    assert "PR #17" in status and "authoritative current head" in status.lower()
