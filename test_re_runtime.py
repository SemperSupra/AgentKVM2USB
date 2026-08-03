"""Deterministic mocked tests for the issue #14 Docker runtime selection and adapter.

No real Docker daemon is required. ``select_runtime``/``Adapter``/Beagle routing
are exercised through an injected runner that scripts subprocess responses, so
the full runtime matrix is covered deterministically on any host.
"""

from __future__ import annotations

import json
import os

import pytest

from tools.re import re_runtime as rt


class Proc:
    def __init__(self, rc: int = 0, out: str = "", err: str = ""):
        self.returncode = rc
        self.stdout = out
        self.stderr = err


def ok(out: str = "") -> Proc:
    return Proc(0, out)


def fail(rc: int = 1, err: str = "error") -> Proc:
    return Proc(rc, "", err)


DESKTOP_VERSION = "Docker version 29.6.2, build dfc4efb"
COMPOSE_VERSION = "Docker Compose version v5.3.1"
DESKTOP_INFO = (
    "Client:\n Debug Mode: false\n"
    "Server:\n Containers: 0\n OSType: linux\n Server Version: 29.6.2\n"
)
DESKTOP_INFO_WINDOWS = "Client:\nServer:\n OSType: windows\n Server Version: 29.6.2\n"
DESKTOP_STATUS_RUNNING = '{"SessionID":"s","Status":"running"}'
DESKTOP_STATUS_STOPPED = '{"SessionID":"s","Status":"stopped"}'
DESKTOP_CONTEXT_SHOW = "desktop-linux"
DESKTOP_CONTEXT_ENDPOINT = "npipe:////./pipe/dockerDesktopLinuxEngine"
WSL_LIST = "  NAME      STATE       VERSION\n* Ubuntu    Running     2\n  docker-desktop  Stopped    2\n"
WSL_LIST_DEBIAN_V1 = "  NAME      STATE       VERSION\n* Debian    Running     1\n"
WSL_LIST_UBUNTU_ONLY = "  NAME      STATE       VERSION\n* Ubuntu    Running     2\n"
WSL_DOCKER_VERSION = "Docker version 27.0.0, build abc"
WSL_INFO = "Client:\n Debug Mode: false\nServer:\n OSType: linux\n Server Version: 27.0.0\n"
REPO = r"C:\Users\Mark\Projects\AgentKVM2USB-issue14"


def make_runner(handlers):
    """Build an injected runner from {substring: Proc|callable}. The first
    matching substring wins; any argv with no handler fails the test, which also
    proves commands that must NOT run (e.g. docker desktop start) never ran."""

    def runner(argv, **kwargs):
        joined = " ".join(str(a) for a in argv)
        for needle, response in handlers.items():
            if needle in joined:
                return response(argv, kwargs) if callable(response) else response
        raise AssertionError("no handler for argv: %r" % (list(argv),))

    return runner


@pytest.fixture
def which(monkeypatch):
    def install(exes):
        def _which(name):
            if name in exes:
                return "C:\\fake\\" + name + ".exe"
            return None

        monkeypatch.setattr(rt.shutil, "which", _which)
        return _which

    return install


@pytest.fixture
def clock(monkeypatch):
    """No-op sleep and a monotonically advancing clock so start-polling tests
    never wait on wall time."""
    monkeypatch.setattr(rt.time, "sleep", lambda seconds: None)
    state = {"now": 1000.0}

    def _monotonic():
        state["now"] += rt.START_POLL_SECONDS
        return state["now"]

    monkeypatch.setattr(rt.time, "monotonic", _monotonic)
    return state


def desktop_handlers(
    info: Proc = ok(DESKTOP_INFO),
    status: Proc = ok(DESKTOP_STATUS_RUNNING),
    context_names: Proc = ok("default\ndesktop-linux\n"),
    context_inspect: Proc = ok(DESKTOP_CONTEXT_ENDPOINT),
):
    # Needles are anchored to docker.exe so they never cross-match the WSL
    # docker argv (which contains bare "docker --version"/"docker info"). The
    # Desktop probe requires positive identity and a Desktop-owned Linux context.
    return {
        "docker.exe --version": ok(DESKTOP_VERSION),
        "docker.exe desktop status --format json": status,
        "docker.exe context ls --format": context_names,
        "docker.exe context show": ok(DESKTOP_CONTEXT_SHOW),
        "docker.exe context inspect desktop-linux --format": context_inspect,
        "docker.exe --context desktop-linux info": info,
        "docker.exe --context desktop-linux compose version": ok(COMPOSE_VERSION),
    }


def wsl_handlers(version: Proc = ok(WSL_DOCKER_VERSION), info: Proc = ok(WSL_INFO),
                 compose: Proc = ok(COMPOSE_VERSION), distro_list: Proc = ok(WSL_LIST)):
    return {
        "-l -v": distro_list,
        "--exec docker --version": version,
        "--exec docker info": info,
        "--exec docker compose version": compose,
    }


def select(**overrides):
    kwargs = dict(
        requested="Auto",
        wsl_distribution="Ubuntu",
        no_start_docker_desktop=False,
        run=make_runner({}),
        repo_root=REPO,
        start_timeout_s=10,
        now_iso="2026-01-01T00:00:00+00:00",
    )
    kwargs.update(overrides)
    return rt.select_runtime(**kwargs)


# --------------------------------------------------------------------------- selection matrix


def test_select_docker_desktop_only(which):
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers())
    handlers.update(wsl_handlers(version=fail(1)))  # native docker missing in WSL
    sel = select(run=make_runner(handlers))
    assert sel["selected_runtime"] == "DockerDesktop"
    assert sel["selection_reason"] == "only Docker Desktop is healthy"
    assert sel["probes"]["DockerDesktop"]["healthy"] is True
    assert sel["probes"]["WslEngine"]["healthy"] is False
    assert sel["probes"]["WslEngine"]["reason"] == "cli_missing"


def test_select_wsl_engine_only(which):
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers(info=fail(1, "cannot connect to docker daemon")))
    handlers.update(wsl_handlers())
    sel = select(run=make_runner(handlers))
    assert sel["selected_runtime"] == "WslEngine"
    assert sel["probes"]["DockerDesktop"]["healthy"] is False
    assert sel["probes"]["DockerDesktop"]["reason"] == "daemon_unavailable"
    assert sel["probes"]["WslEngine"]["healthy"] is True


def test_select_both_healthy_prefers_desktop_active_context(which):
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers())
    handlers.update(wsl_handlers())
    sel = select(run=make_runner(handlers))
    assert sel["selected_runtime"] == "DockerDesktop"
    assert "active Docker Desktop Linux context preferred" in sel["selection_reason"]


def test_select_both_healthy_prefers_wsl_without_active_desktop_context(which):
    # Desktop is healthy with a Desktop-owned context (desktop-linux) that is NOT
    # the active global context (custom); both candidates healthy, so Auto
    # prefers the native WSL Engine because no active Desktop context is present.
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers())
    handlers["docker.exe context ls --format"] = ok("custom\ndesktop-linux\n")
    handlers["docker.exe context show"] = ok("custom")
    handlers["docker.exe context inspect custom --format"] = ok("npipe:////./pipe/custom")
    handlers.update(wsl_handlers())
    sel = select(run=make_runner(handlers))
    assert sel["selected_runtime"] == "WslEngine"
    assert "no active Docker Desktop Linux context" in sel["selection_reason"]


def test_select_neither_healthy_reports_both_without_installing(which):
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers(info=fail(1, "daemon down")))
    handlers.update(wsl_handlers(version=fail(1)))
    sel = select(run=make_runner(handlers))
    assert sel["selected_runtime"] is None
    assert len(sel["selection_error"]) == 2
    reasons = {e["candidate"]: e["reason"] for e in sel["selection_error"]}
    assert reasons["DockerDesktop"] == "daemon_unavailable"
    assert reasons["WslEngine"] == "cli_missing"


def test_desktop_stopped_start_allowed(which, clock):
    which({"docker": True, "wsl": True})
    info_calls = {"n": 0}

    def info_handler(argv, kwargs):
        info_calls["n"] += 1
        if info_calls["n"] == 1:
            return fail(1, "cannot connect")
        return ok(DESKTOP_INFO)

    handlers = dict(desktop_handlers(info=info_handler, status=ok(DESKTOP_STATUS_STOPPED)))
    handlers["desktop start"] = ok()
    handlers.update(wsl_handlers(version=fail(1)))
    sel = select(run=make_runner(handlers), start_timeout_s=10)
    assert sel["selected_runtime"] == "DockerDesktop"
    assert sel["probes"]["DockerDesktop"]["healthy"] is True
    assert any("starting it with bounded polling" in d for d in sel["probes"]["DockerDesktop"]["diagnostics"])


def test_desktop_stopped_start_disabled(which):
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers(info=fail(1, "cannot connect"), status=ok(DESKTOP_STATUS_STOPPED)))
    # No "desktop start" handler: if the probe tried to start, the runner raises.
    handlers.update(wsl_handlers(version=fail(1)))
    sel = select(
        requested="DockerDesktop", no_start_docker_desktop=True,
        run=make_runner(handlers), start_timeout_s=10,
    )
    assert sel["selected_runtime"] is None
    assert sel["probes"]["DockerDesktop"]["reason"] == "start_disabled"
    assert sel["probes"]["DockerDesktop"]["healthy"] is False


def test_desktop_start_timeout(which, clock):
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers(info=fail(1, "still down"), status=ok(DESKTOP_STATUS_STOPPED)))
    handlers["desktop start"] = ok()
    handlers.update(wsl_handlers(version=fail(1)))
    sel = select(run=make_runner(handlers), start_timeout_s=0.001)
    assert sel["probes"]["DockerDesktop"]["healthy"] is False
    assert sel["probes"]["DockerDesktop"]["reason"] == "start_timeout"


def test_desktop_windows_container_mode(which):
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers(info=ok(DESKTOP_INFO_WINDOWS)))
    handlers.update(wsl_handlers(version=fail(1)))
    sel = select(run=make_runner(handlers))
    assert sel["selected_runtime"] is None
    assert sel["probes"]["DockerDesktop"]["reason"] == "windows_container_mode"


def test_desktop_cli_missing(which):
    which({"wsl": True})
    handlers = wsl_handlers()
    sel = select(run=make_runner(handlers))
    assert sel["probes"]["DockerDesktop"]["reason"] == "docker_cli_missing"
    assert sel["probes"]["DockerDesktop"]["available"] is False


def test_desktop_server_unavailable(which):
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers(info=fail(1, "cannot connect")))
    handlers.update(wsl_handlers(version=fail(1)))
    sel = select(run=make_runner(handlers))
    assert sel["probes"]["DockerDesktop"]["reason"] == "daemon_unavailable"


def test_desktop_compose_missing(which):
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers())
    handlers["docker.exe --context desktop-linux compose version"] = fail(1, "plugin not installed")
    handlers.update(wsl_handlers(version=fail(1)))
    sel = select(run=make_runner(handlers))
    assert sel["probes"]["DockerDesktop"]["healthy"] is False
    assert sel["probes"]["DockerDesktop"]["reason"] == "compose_missing"


def test_wsl_distro_missing(which):
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers(info=fail(1)))
    handlers.update(wsl_handlers(distro_list=ok(WSL_LIST_UBUNTU_ONLY)))
    sel = select(wsl_distribution="Debian", run=make_runner(handlers))
    assert sel["probes"]["WslEngine"]["reason"] == "distro_missing"


def test_wsl_non_wsl2(which):
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers(info=fail(1)))
    handlers.update(wsl_handlers(distro_list=ok(WSL_LIST_DEBIAN_V1)))
    sel = select(wsl_distribution="Debian", run=make_runner(handlers))
    assert sel["probes"]["WslEngine"]["reason"] == "non_wsl2"


def test_wsl_daemon_unavailable(which):
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers(info=fail(1)))
    handlers.update(wsl_handlers(version=ok(WSL_DOCKER_VERSION), info=fail(1, "permission denied")))
    sel = select(requested="WslEngine", run=make_runner(handlers))
    assert sel["selected_runtime"] is None
    assert sel["probes"]["WslEngine"]["reason"] == "daemon_unavailable"


def test_explicit_unavailable_runtime_fails_without_switching(which):
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers(info=fail(1), status=ok(DESKTOP_STATUS_STOPPED)))
    handlers.update(wsl_handlers())
    sel = select(requested="DockerDesktop", no_start_docker_desktop=True, run=make_runner(handlers))
    # Explicit selection fails clearly; it must NOT silently switch to WslEngine.
    assert sel["selected_runtime"] is None
    assert "explicit DockerDesktop selection is unavailable" in sel["selection_reason"]


def test_runtime_metadata_recorded(which):
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers())
    handlers.update(wsl_handlers(version=fail(1)))
    sel = select(run=make_runner(handlers))
    meta = sel["metadata"]
    assert meta["os_type"] in ("windows", "posix")
    assert meta["client_version"] == DESKTOP_VERSION
    assert meta["server_version"] == "29.6.2"
    assert meta["server_os"] == "linux"
    assert meta["compose_version"] == COMPOSE_VERSION
    assert meta["context"] == "desktop-linux"
    assert meta["endpoint"] == DESKTOP_CONTEXT_ENDPOINT
    assert meta["docker_desktop"]["context"] == "desktop-linux"
    assert meta["docker_desktop"]["endpoint"] == DESKTOP_CONTEXT_ENDPOINT
    assert meta["docker_desktop"]["active_context"] == "desktop-linux"
    assert meta["docker_desktop"]["context_is_active"] is True
    assert meta["docker_desktop"]["desktop_identity"] == "desktop-status"
    assert meta["wsl"]["distribution"] == "Ubuntu"
    assert meta["wsl"]["version"] == 2
    assert "distributions" in meta["wsl"]
    assert sel["generated_utc"] == "2026-01-01T00:00:00+00:00"


# --------------------------------------------------------------------------- adapter


def wsl_selection():
    return {"selected_runtime": "WslEngine", "wsl_distribution": "Ubuntu"}


def desktop_selection():
    return {
        "selected_runtime": "DockerDesktop",
        "wsl_distribution": "Ubuntu",
        "metadata": {
            "context": "desktop-linux",
            "endpoint": DESKTOP_CONTEXT_ENDPOINT,
            "docker_desktop": {"context": "desktop-linux", "endpoint": DESKTOP_CONTEXT_ENDPOINT},
        },
    }


def wslpath_runner(converted):
    def runner(argv, **kwargs):
        assert argv[:4] == ["C:\\fake\\wsl.exe", "-d", "Ubuntu", "--exec"]
        assert argv[4] == "wslpath"
        assert argv[5] == "-a"
        assert len(argv) == 7  # the Windows path is a single discrete argument
        return Proc(0, converted)

    return runner


def test_adapter_desktop_argv_injects_recorded_context():
    adapter = rt.Adapter(desktop_selection(), REPO, run=make_runner({}), wsl_exe="C:\\fake\\wsl.exe")
    assert adapter.recorded_context == "desktop-linux"
    assert adapter.docker(["--version"]) == ["docker", "--context", "desktop-linux", "--version"]
    assert adapter.compose(["version"]) == ["docker", "--context", "desktop-linux", "compose", "version"]
    assert adapter.to_wsl_path(REPO) == REPO  # Desktop never converts paths


def test_adapter_wsl_argv_discrete_wslpath_argument():
    converted = "/mnt/c/Users/Mark/Projects/AgentKVM2USB-issue14"
    adapter = rt.Adapter(wsl_selection(), REPO, run=wslpath_runner(converted), wsl_exe="C:\\fake\\wsl.exe")
    assert adapter.wsl_repo_path == converted
    assert adapter.docker(["--version"]) == [
        "C:\\fake\\wsl.exe", "--cd", converted, "-d", "Ubuntu", "--exec", "docker", "--version",
    ]
    assert adapter.compose(["version"]) == [
        "C:\\fake\\wsl.exe", "--cd", converted, "-d", "Ubuntu", "--exec", "docker", "compose", "version",
    ]


def test_adapter_wsl_path_spaces_and_parentheses():
    def runner(argv, **kwargs):
        win = argv[6]
        assert "My Folder" in win and "x86" in win
        assert len(argv) == 7
        return Proc(0, "/mnt/c/Users/Mark/My Folder/Proj (x86)/Sub")

    adapter = rt.Adapter(wsl_selection(), REPO, run=runner, wsl_exe="C:\\fake\\wsl.exe")
    result = adapter.to_wsl_path(r"C:\Users\Mark\My Folder\Proj (x86)\Sub")
    assert result == "/mnt/c/Users/Mark/My Folder/Proj (x86)/Sub"


def test_adapter_wslpath_malformed_conversion_raises():
    def runner(argv, **kwargs):
        return Proc(127, "", "There is no distribution with the supplied name.")

    adapter = rt.Adapter(wsl_selection(), REPO, run=runner, wsl_exe="C:\\fake\\wsl.exe")
    with pytest.raises(RuntimeError, match="wslpath conversion failed"):
        adapter.to_wsl_path(REPO)


def test_adapter_wslpath_empty_conversion_raises():
    adapter = rt.Adapter(wsl_selection(), REPO, run=make_runner({"wslpath": ok("  ")}), wsl_exe="C:\\fake\\wsl.exe")
    with pytest.raises(RuntimeError, match="empty path"):
        adapter.to_wsl_path(REPO)


def test_adapter_bash_desktop_raises():
    adapter = rt.Adapter(desktop_selection(), REPO, run=make_runner({}), wsl_exe="C:\\fake\\wsl.exe")
    with pytest.raises(RuntimeError, match="Docker Desktop mode drives the toolchain natively"):
        adapter.bash("tools/re/scan-re-image.sh")


def test_adapter_bash_wsl_quotes_args():
    converted = "/mnt/c/repo"
    adapter = rt.Adapter(wsl_selection(), REPO, run=wslpath_runner(converted), wsl_exe="C:\\fake\\wsl.exe")
    argv = adapter.bash("tools/re/run-beagle-container.sh", ["python3", "/work/scripts/capture_beagle_usb12.py --help"])
    cmd = argv[-1]
    assert "bash tools/re/run-beagle-container.sh 'python3' '/work/scripts/capture_beagle_usb12.py --help'" in cmd
    argv = adapter.bash("tools/re/bootstrap-re-containers.sh", [], {"ALLOW_COMMUNITY_GHIDRA": "1", "SKIP_UPSTREAM_BUILDS": "0"})
    assert "ALLOW_COMMUNITY_GHIDRA='1' SKIP_UPSTREAM_BUILDS='0' bash tools/re/bootstrap-re-containers.sh" in argv[-1]


def test_adapter_preserves_exit_codes():
    adapter = rt.Adapter(desktop_selection(), REPO, run=make_runner({"docker --context desktop-linux info": fail(7, "boom")}), wsl_exe="C:\\fake\\wsl.exe")
    result = adapter.run(adapter.docker(["info"]))
    assert result.returncode == 7
    assert result.stderr == "boom"


def test_strip_separator():
    assert rt._strip_separator(["--", "pull", "x"]) == ["pull", "x"]
    assert rt._strip_separator(["pull", "x"]) == ["pull", "x"]
    assert rt._strip_separator([]) == []


def test_runtime_json_roundtrip_preserves_selection(tmp_path):
    # The adapter must be built from the exact recorded selection; writing and
    # reading runtime.json must not change the runtime (no silent switch).
    selection = {
        "schema_version": 1,
        "generated_utc": "2026-01-01T00:00:00+00:00",
        "requested_runtime": "DockerDesktop",
        "wsl_distribution": "Ubuntu",
        "no_start_docker_desktop": False,
        "selected_runtime": "DockerDesktop",
        "selection_reason": "explicit DockerDesktop selection is healthy",
        "probes": {},
        "metadata": {
            "os_type": "windows",
            "context": "desktop-linux",
            "endpoint": DESKTOP_CONTEXT_ENDPOINT,
            "docker_desktop": {"context": "desktop-linux", "endpoint": DESKTOP_CONTEXT_ENDPOINT},
        },
    }
    path = os.path.join(str(tmp_path), "runtime.json")
    assert rt.write_runtime_json(selection, path) == os.path.abspath(path)
    restored = rt.read_runtime_json(path)
    adapter = rt.Adapter(restored, REPO, run=make_runner({}), wsl_exe="C:\\fake\\wsl.exe")
    assert adapter.runtime == "DockerDesktop"
    assert adapter.docker(["ps"]) == ["docker", "--context", "desktop-linux", "ps"]


def test_parse_helpers():
    assert rt.parse_wsl_list("  NAME  STATE  VERSION\n* Ubuntu  Stopped  2\n  docker-desktop  Stopped  2\n") == {
        "Ubuntu": 2, "docker-desktop": 2,
    }
    assert rt.parse_wsl_list("* Debian  Running  1\n") == {"Debian": 1}
    assert rt.parse_docker_info(DESKTOP_INFO) == ("linux", "29.6.2")
    assert rt.parse_docker_info(DESKTOP_INFO_WINDOWS) == ("windows", "29.6.2")


def test_decode_utf16_wsl_list():
    raw = "  NAME  STATE  VERSION\n* Ubuntu  Stopped  2\n".encode("utf-16-le")
    assert rt._decode(raw) == "  NAME  STATE  VERSION\n* Ubuntu  Stopped  2\n"


# --------------------------------------------------------------------------- Beagle routing


def test_beagle_route_container(tmp_path):
    linux = tmp_path / "linux-x86_64"
    linux.mkdir()
    (linux / "beagle.so").write_bytes(b"ELF")
    api = tmp_path / "win-python"
    api.mkdir()
    (api / "beagle_py.py").write_text("x")
    assert rt.find_linux_beagle_api(str(tmp_path)) == str(linux / "beagle.so")
    assert rt.find_windows_beagle_api(str(tmp_path)) == str(api)
    route = rt.choose_beagle_route("WslEngine", str(linux / "beagle.so"), str(api))
    assert route["route"] == "container"


def test_beagle_route_windows_host_fallback(tmp_path):
    api = tmp_path / "win-python"
    api.mkdir()
    (api / "beagle_py.py").write_text("x")
    route = rt.choose_beagle_route("DockerDesktop", None, str(api))
    assert route["route"] == "windows_host"
    assert route["windows_api_dir"] == str(api)


def test_beagle_route_unavailable():
    assert rt.choose_beagle_route("DockerDesktop", None, None) == {"route": "unavailable"}


def test_missing_linux_beagle_api_does_not_block_selection(which):
    # Runtime selection and general tooling do not depend on the vendor Beagle API.
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers())
    handlers.update(wsl_handlers(version=fail(1)))
    sel = select(run=make_runner(handlers))
    assert sel["selected_runtime"] == "DockerDesktop"


# --------------------------------------------------------------------------- hardening: Desktop identity + context pinning


def test_desktop_status_unsupported_custom_context_rejected(which):
    # No supported desktop status and no installed Desktop evidence: a custom or
    # remote Windows context must NOT be accepted as Docker Desktop.
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers(status=fail(1, "unsupported")))
    handlers["docker.exe desktop --help"] = fail(1)
    handlers["sc query com.docker.service"] = fail(1)
    handlers.update(wsl_handlers())
    sel = select(requested="DockerDesktop", run=make_runner(handlers))
    assert sel["selected_runtime"] is None
    assert sel["probes"]["DockerDesktop"]["reason"] == "desktop_identity_unsupported"


def test_desktop_status_unsupported_with_installed_evidence_and_desktop_context_accepted(which):
    # Older Desktop: status unsupported, but installed Desktop evidence plus a
    # Desktop-owned Linux context is accepted.
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers(status=fail(1, "unsupported")))
    handlers["docker.exe desktop --help"] = ok("usage: docker desktop")
    handlers["sc query com.docker.service"] = ok("SERVICE_NAME: com.docker.service")
    handlers.update(wsl_handlers(version=fail(1)))
    sel = select(run=make_runner(handlers))
    assert sel["selected_runtime"] == "DockerDesktop"
    dd = sel["probes"]["DockerDesktop"]["details"]
    assert dd["desktop_identity"] == "installed-evidence"
    assert dd["context"] == "desktop-linux"
    assert dd["endpoint"] == DESKTOP_CONTEXT_ENDPOINT


def test_explicit_desktop_with_custom_context_fails(which):
    # Explicit DockerDesktop with only a custom/remote Linux context must fail.
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers())
    handlers["docker.exe context ls --format"] = ok("custom\n")
    handlers["docker.exe context show"] = ok("custom")
    handlers["docker.exe context inspect custom --format"] = ok("npipe:////./pipe/custom")
    handlers.update(wsl_handlers())
    sel = select(requested="DockerDesktop", run=make_runner(handlers))
    assert sel["selected_runtime"] is None
    assert sel["probes"]["DockerDesktop"]["reason"] == "no_desktop_linux_context"


def test_global_context_changed_after_selection_uses_recorded_context():
    # The adapter is built from the recorded selection and always uses the
    # recorded context; a later global context change cannot redirect it. The
    # empty mock runner raises if any other context were used.
    selection = desktop_selection()
    adapter = rt.Adapter(selection, REPO, run=make_runner({}), wsl_exe="C:\\fake\\wsl.exe")
    assert adapter.docker(["info"]) == ["docker", "--context", "desktop-linux", "info"]
    assert adapter.compose(["ps"]) == ["docker", "--context", "desktop-linux", "compose", "ps"]
    assert adapter.docker(["image", "inspect", "x"]) == ["docker", "--context", "desktop-linux", "image", "inspect", "x"]


def test_recorded_context_removed_fails_closed():
    handlers = {
        "docker --context desktop-linux context inspect desktop-linux --format": fail(1, "context not found"),
    }
    adapter = rt.Adapter(desktop_selection(), REPO, run=make_runner(handlers), wsl_exe="C:\\fake\\wsl.exe")
    result = adapter.verify_context()
    assert result.returncode != 0
    assert "missing" in result.stderr


def test_recorded_context_endpoint_changed_fails_closed():
    handlers = {
        "docker --context desktop-linux context inspect desktop-linux --format": ok("npipe:////./pipe/something-else"),
    }
    adapter = rt.Adapter(desktop_selection(), REPO, run=make_runner(handlers), wsl_exe="C:\\fake\\wsl.exe")
    result = adapter.verify_context()
    assert result.returncode != 0
    assert "endpoint changed" in result.stderr


def test_recorded_context_windows_mode_fails_closed():
    handlers = {
        "docker --context desktop-linux context inspect desktop-linux --format": ok(DESKTOP_CONTEXT_ENDPOINT),
        "docker --context desktop-linux info": ok(DESKTOP_INFO_WINDOWS),
    }
    adapter = rt.Adapter(desktop_selection(), REPO, run=make_runner(handlers), wsl_exe="C:\\fake\\wsl.exe")
    result = adapter.verify_context()
    assert result.returncode != 0
    assert "not Linux" in result.stderr


def test_every_operation_includes_selected_context():
    adapter = rt.Adapter(desktop_selection(), REPO, run=make_runner({}), wsl_exe="C:\\fake\\wsl.exe")
    ops = [
        adapter.docker(["pull", "x"]),
        adapter.docker(["build", "-t", "x", "."]),
        adapter.docker(["image", "inspect", "x"]),
        adapter.docker(["image", "tag", "a", "b"]),
        adapter.docker(["save", "-o", "x.tar", "x"]),
        adapter.docker(["compose", "version"]),
        adapter.compose(["run", "--rm", "runner"]),
    ]
    for argv in ops:
        assert argv[0] == "docker"
        assert argv[1:3] == ["--context", "desktop-linux"], argv


def test_image_lock_uses_adapter(tmp_path):
    import json as _json
    import tools.re.write_image_lock as wil

    env = tmp_path / ".env.re"
    env.write_text("RADARE2_IMAGE=radare/radare2:6.1.8\nRE_RUNNER_IMAGE=agentkvm2usb/re-runner:1\n", encoding="utf-8")
    rt_json = tmp_path / "runtime.json"
    rt.write_runtime_json(desktop_selection(), str(rt_json))
    inspected = _json.dumps(
        [{"RepoDigests": ["radare/radare2@sha256:abc"], "Id": "sha256:id",
          "Created": "t", "Architecture": "amd64", "Os": "linux"}]
    )
    adapter = rt.Adapter(
        desktop_selection(), str(tmp_path),
        run=make_runner({"docker --context desktop-linux image inspect": ok(inspected)}),
        wsl_exe="C:\\fake\\wsl.exe",
    )
    lock = wil.write_image_lock(
        env_file=env, locked_env=tmp_path / ".env.re.lock", output=tmp_path / "lock.json",
        repo_root=str(tmp_path), runtime_json=str(rt_json), adapter=adapter,
    )
    assert lock["runtime"]["selected_runtime"] == "DockerDesktop"
    assert lock["runtime"]["context"] == "desktop-linux"
    assert lock["runtime"]["runtime_json_sha256"]
    assert lock["runtime"]["image_lock_generated_utc"]
    assert lock["images"][0]["immutable_reference"] == "radare/radare2@sha256:abc"
    locked = (tmp_path / ".env.re.lock").read_text(encoding="utf-8")
    assert "RADARE2_IMAGE=radare/radare2@sha256:abc" in locked


# --------------------------------------------------------------------------- hardening: selected-runtime provenance


def test_wsl_selected_metadata_has_no_desktop_leak(which):
    # Desktop client is present and identity-confirmed but its daemon is down;
    # WSL Engine is selected. The top-level metadata must carry only WSL values.
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers(info=fail(1, "cannot connect")))
    handlers.update(wsl_handlers())
    sel = select(run=make_runner(handlers))
    assert sel["selected_runtime"] == "WslEngine"
    meta = sel["metadata"]
    assert meta["client_version"] == WSL_DOCKER_VERSION
    assert meta["server_version"] == "27.0.0"
    assert meta["server_os"] == "linux"
    assert meta["compose_version"] == COMPOSE_VERSION
    assert meta["context"] is None
    assert meta["endpoint"] is None
    # The unhealthy Desktop client's values stay inside the labeled candidate
    # sub-object and never leak into the selected top-level metadata.
    assert meta["docker_desktop"]["client_version"] == DESKTOP_VERSION


def test_runtime_json_hash_in_provenance(tmp_path):
    import tools.re.write_image_lock as wil

    rt_json = tmp_path / "runtime.json"
    rt.write_runtime_json(desktop_selection(), str(rt_json))
    prov = wil.build_runtime_provenance(desktop_selection(), str(rt_json))
    assert prov["runtime_json_sha256"] == wil.sha256_of_file(str(rt_json))
    assert prov["selected_runtime"] == "DockerDesktop"
    assert prov["context"] == "desktop-linux"
    assert prov["endpoint"] == DESKTOP_CONTEXT_ENDPOINT


# --------------------------------------------------------------------------- hardening: mutable inputs + build locks


def test_unused_angr_image_not_pulled():
    root = os.path.dirname(__file__)
    # The unused angr/angr image is never pulled (the compose angr service uses
    # the project runner, which pins angr in its Python requirements).
    bootstrap = open(os.path.join(root, "tools", "re", "bootstrap-re-containers.ps1"), encoding="utf-8").read()
    assert "angr/angr:latest" not in bootstrap
    assert "pullImages" in bootstrap
    sh = open(os.path.join(root, "tools", "re", "bootstrap-re-containers.sh"), encoding="utf-8").read()
    assert "angr/angr" not in sh
    compose = open(os.path.join(root, "compose.re.yml"), encoding="utf-8").read()
    assert "image: ${ANGR_IMAGE:-agentkvm2usb/re-runner:1}" in compose
    env = open(os.path.join(root, ".env.re.example"), encoding="utf-8").read()
    assert "SYFT_IMAGE=anchore/syft:v" in env
    assert "TRIVY_IMAGE=aquasec/trivy:0." in env


def test_base_image_digest_recorded(tmp_path):
    import json as _json
    import tools.re.resolve_base_image as rbi

    inspected = _json.dumps(
        [{"RepoDigests": ["python@sha256:abcdef"], "Id": "sha256:id", "Architecture": "amd64", "Os": "linux"}]
    )
    adapter = rt.Adapter(
        desktop_selection(), str(tmp_path),
        run=make_runner({"docker --context desktop-linux image inspect": ok(inspected)}),
        wsl_exe="C:\\fake\\wsl.exe",
    )
    out = tmp_path / "base-image.lock.json"
    rec = rbi.resolve_base_image(adapter=adapter, image="python:3.12-slim-bookworm", output=out)
    assert rec["resolved_digest"] == "python@sha256:abcdef"
    assert rec["source_repository"] == "python"
    assert rec["requested_tag"] == "python:3.12-slim-bookworm"
    assert rec["architecture"] == "amd64"
    assert rec["retrieved_utc"]
    assert out.exists()


def test_python_hash_lock_enforced():
    root = os.path.dirname(__file__)
    lock = open(os.path.join(root, "containers", "re-runner", "requirements.lock.txt"), encoding="utf-8").read()
    assert "--hash=sha256" in lock
    assert "angr==" in lock
    dockerfile = open(os.path.join(root, "containers", "re-runner", "Dockerfile"), encoding="utf-8").read()
    assert "--require-hashes" in dockerfile
    assert "FROM ${PYTHON_BASE_IMAGE}" in dockerfile
    assert "requirements.lock.txt" in dockerfile
    inp = open(os.path.join(root, "containers", "re-runner", "requirements.in"), encoding="utf-8").read()
    assert "angr==" in inp


# --------------------------------------------------------------------------- hardening: Trivy triage


TRIVY_SAMPLE = {
    "Results": [
        {"Class": "os-pkgs", "Type": "debian", "Vulnerabilities": [
            {"VulnerabilityID": "CVE-2023-1", "Severity": "CRITICAL", "PkgName": "zlib1g",
             "InstalledVersion": "1.2.13-1", "FixedVersion": "", "Layer": {"DiffID": "sha256:layer1"}},
            {"VulnerabilityID": "CVE-2023-2", "Severity": "HIGH", "PkgName": "openssl",
             "InstalledVersion": "3.0", "FixedVersion": "3.0.1", "Layer": {"DiffID": "sha256:layer2"}},
        ]},
        {"Class": "lang-pkgs", "Type": "python", "Vulnerabilities": [
            {"VulnerabilityID": "CVE-2024-1", "Severity": "CRITICAL", "PkgName": "angr",
             "InstalledVersion": "9.3.1", "FixedVersion": "9.3.2", "Paths": ["/usr/local/lib/angr"]},
        ]},
    ]
}


def test_trivy_summary_classifies_critical_and_high():
    import tools.re.summarize_trivy as st
    s = st.summarize(TRIVY_SAMPLE)
    assert s["summary"]["criticals_total"] == 2
    assert s["summary"]["highs_total"] == 1
    assert s["summary"]["criticals_fixable"] == 1
    assert s["summary"]["criticals_unfixed"] == 1
    crits = {r["id"]: r for r in s["criticals"]}
    assert crits["CVE-2023-1"]["fixed_status"] == "unfixed"
    assert crits["CVE-2023-1"]["ecosystem"] == "debian"
    assert crits["CVE-2023-1"]["source_layer"] == "sha256:layer1"
    assert crits["CVE-2024-1"]["fixed_status"] == "fixed"
    assert crits["CVE-2024-1"]["dependency_path"] == ["/usr/local/lib/angr"]
    assert "angr" in crits["CVE-2024-1"]["purpose"].lower()
    assert crits["CVE-2023-1"]["present_in_final_runtime_image"] is True


def test_trivy_fixable_vs_unfixed_critical():
    import tools.re.summarize_trivy as st
    s = st.summarize(TRIVY_SAMPLE)
    # angr has a fixed version -> fixable -> gate fails.
    assert s["gate"]["zero_fixable_criticals"] is False
    assert s["gate"]["fixable_critical_ids"] == ["CVE-2024-1"]


def test_trivy_zero_fixable_critical_gate(tmp_path):
    import tools.re.summarize_trivy as st
    sample = {"Results": [{"Class": "os-pkgs", "Type": "debian", "Vulnerabilities": [
        {"VulnerabilityID": "CVE-1", "Severity": "CRITICAL", "PkgName": "zlib1g",
         "InstalledVersion": "1.0", "FixedVersion": ""}
    ]}]}
    s = st.summarize(sample)
    assert s["gate"]["zero_fixable_criticals"] is True
    inp = tmp_path / "in.json"
    inp.write_text(json.dumps(sample))
    rc = st.main(["--input", str(inp), "--output", str(tmp_path / "out.json"),
                  "--markdown", str(tmp_path / "out.md"), "--gate"])
    assert rc == 0


def test_trivy_gate_fails_on_fixable_critical(tmp_path):
    import tools.re.summarize_trivy as st
    sample = {"Results": [{"Class": "lang-pkgs", "Type": "python", "Vulnerabilities": [
        {"VulnerabilityID": "CVE-2", "Severity": "CRITICAL", "PkgName": "angr",
         "InstalledVersion": "9.3.1", "FixedVersion": "9.3.2"}
    ]}]}
    inp = tmp_path / "in.json"
    inp.write_text(json.dumps(sample))
    rc = st.main(["--input", str(inp), "--output", str(tmp_path / "out.json"),
                  "--markdown", str(tmp_path / "out.md"), "--gate"])
    assert rc == 1


# --------------------------------------------------------------------------- compose hardening


def test_compose_no_docker_socket_and_hardening():
    root = os.path.dirname(__file__)
    text = open(os.path.join(root, "compose.re.yml"), encoding="utf-8").read()
    assert "docker.sock" not in text
    assert "/var/run/docker.sock" not in text
    for svc in ("runner", "radare2", "angr", "ghidra", "binwalk", "syft", "trivy"):
        assert f"{svc}:" in text
    assert "network_mode: none" in text
    assert "read_only: true" in text
    assert "cap_drop:" in text
    assert "    - ALL" in text
    assert "no-new-privileges:true" in text
    # angr runs in the project runner image (the publisher image lacks angr).
    assert "image: ${ANGR_IMAGE:-agentkvm2usb/re-runner:1}" in text
    # syft/trivy use host-backed writable dirs, not the 512 MiB default tmpfs.
    assert "entrypoint: [\"/syft\"]" in text
    # runner build locks the Python base through a resolved immutable digest.
    assert "PYTHON_BASE_IMAGE: ${PYTHON_BASE_IMAGE:-python:3.12-slim-bookworm}" in text
