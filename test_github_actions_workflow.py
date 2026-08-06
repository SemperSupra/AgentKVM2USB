from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
PLAN = ROOT / "docs" / "GITHUB_ACTIONS_CORRECTIVE_ACTION_PLAN.md"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing CI governance file: {path}"
    return path.read_text(encoding="utf-8")


def _normalized_words(text: str) -> str:
    return " ".join(text.split())


def test_ci_files_exist() -> None:
    assert WORKFLOW.is_file()
    assert PLAN.is_file()


def test_workflow_has_bounded_triggers_and_concurrency() -> None:
    text = _read(WORKFLOW)
    for required in (
        "pull_request:",
        "push:",
        "workflow_dispatch:",
        "main",
        "recovery/agentkvm2usb-app-capabilities",
        "concurrency:",
        "cancel-in-progress: true",
    ):
        assert required in text


def test_workflow_uses_least_privilege_and_current_actions() -> None:
    text = _read(WORKFLOW)
    for required in (
        "permissions:",
        "contents: read",
        "actions/checkout@v7",
        "persist-credentials: false",
        "actions/setup-python@v7",
        'python-version: "3.12"',
        "cache: pip",
        "cache-dependency-path: requirements.txt",
        "runs-on: windows-2025",
        "timeout-minutes: 20",
    ):
        assert required in text


def test_workflow_runs_required_validation() -> None:
    text = _read(WORKFLOW)
    for required in (
        "python -m pip install --requirement requirements.txt",
        "python -m compileall -q .",
        "python -m pytest -q",
        "scripts\\build_portable.py --version ci",
        "Get-FileHash -Algorithm SHA256",
        "Portable build is not reproducible",
        "QT_QPA_PLATFORM: offscreen",
    ):
        assert required in text


def test_workflow_has_no_privileged_or_hardware_operations() -> None:
    lowered = _read(WORKFLOW).lower()
    for forbidden in (
        "upload-artifact",
        "gh release",
        "create-release",
        "start-process",
        "-verb runas",
        "winget install",
        "usbpcapcmd",
        "tshark",
        "wireshark",
        "capture_beagle",
        "capture_mi00",
        "run_macro",
        "workflow_run:",
        "pull_request_target:",
    ):
        assert forbidden not in lowered


def test_corrective_plan_records_empty_initial_history_and_cleanup_rules() -> None:
    text = _normalized_words(_read(PLAN))
    for required in (
        "zero registered workflows",
        "zero workflow runs",
        "The root cause was therefore not a failing workflow",
        "Do not delete a run merely to make the history appear green.",
        "gh run delete <run-id>",
        "Never delete an unresolved failure",
        "uploads no artifacts",
        "actions/checkout@v7",
        "actions/setup-python@v7",
    ):
        assert required in text
