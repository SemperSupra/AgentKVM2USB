from pathlib import Path


ROOT = Path(__file__).resolve().parent
ACTIVE = ROOT / "docs" / "ACTIVE_WORKSTREAMS.md"
BACKLOG = ROOT / "BACKLOG.md"
CHECKPOINT = ROOT / "docs" / "EXECUTION_CHECKPOINT.md"
AGENTS = ROOT / "AGENTS.md"
RUNBOOK = ROOT / "docs" / "ISSUE27_OPERATOR_DEPENDENCY_RUNBOOK.md"
ISSUE27 = ROOT / "prompts" / "ISSUE27_KICKOFF.md"
ISSUE22 = ROOT / "prompts" / "ISSUE22_KICKOFF.md"


def read(path: Path) -> str:
    assert path.is_file(), f"missing coordination artifact: {path}"
    return path.read_text(encoding="utf-8")


def test_checkpoint_and_dispatch_artifacts_exist() -> None:
    for path in (ACTIVE, BACKLOG, CHECKPOINT, AGENTS, RUNBOOK, ISSUE27, ISSUE22):
        assert path.is_file()


def test_post_pr28_state_is_current() -> None:
    combined = "\n".join(read(path) for path in (ACTIVE, BACKLOG, CHECKPOINT, AGENTS, RUNBOOK, ISSUE27))
    assert "5a398ac529d1e050101a6f078153f3935498d6d2" in combined
    assert "PR #28: merged" in combined or "PR #28 is merged" in combined
    for stale in (
        "draft PR #28",
        "Active dependency-work PR: draft PR #28",
        "run full local Windows validation for issue #27 / PR #28",
        "review and merge PR #28 after validation",
    ):
        assert stale not in combined


def test_active_lanes_define_exact_gates() -> None:
    text = read(ACTIVE)
    for required in (
        "Lane A — Issue #27 operator prerequisites",
        "Lane B — Windows Package Foundry #1",
        "Lane C — Windows Package Foundry #2",
        "Lane D — AgentKVM2USB issue #22",
        "Lane E — AgentKVM2USB issue #14",
        "Lane F — PR #13 / issue #8 Phase B",
        "issue-27-operator-actions",
        "issue-22-readiness-completion",
        "START",
        "CHECKPOINT",
        "HANDOFF",
    ):
        assert required in text


def test_issue27_kickoff_does_not_reuse_merged_branch() -> None:
    text = read(ISSUE27)
    assert "PR #28 is merged" in text
    assert "Do not reuse or modify the historical issue-27-operator-dependencies branch" in text
    assert "issue-27-operator-actions" in text
    assert "operator to restart Windows manually" in text
    assert "Do not directly install USBPcap" in text


def test_issue22_kickoff_fails_closed_before_claim() -> None:
    text = read(ISSUE22)
    for required in (
        "Verify the entry gate before claiming",
        "pending reboot false",
        "USBPcapCMD.exe verified",
        "do not claim #22",
        "issue-22-readiness-completion",
        "ok: true",
        "live_disabled: true",
    ):
        assert required in text
    assert "Do not acquire dependencies" in text


def test_uac_and_vendor_trust_hardening_is_documented() -> None:
    combined = read(RUNBOOK) + "\n" + read(AGENTS)
    for required in (
        "tracked by Git",
        "unstaged and unmodified",
        "origin/*",
        "Authenticode status is `Valid`",
        "signer identifies Epiphan",
        "thumbprint matches",
        "never reboots",
    ):
        assert required in combined


def test_checkpoint_preserves_safety_boundaries() -> None:
    text = read(CHECKPOINT)
    for required in (
        "No agent may infer permission",
        "automate UAC",
        "automate vendor login",
        "reboot automatically",
        "start capture or send target input",
        "modify PR #13",
    ):
        assert required in text
