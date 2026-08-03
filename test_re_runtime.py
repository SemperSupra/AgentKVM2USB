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
    # verify_context succeeds (healthy Desktop context); the actual op fails with
    # a distinct argv so exit code + stderr are preserved through the adapter.
    handlers = {
        "docker context inspect desktop-linux --format": ok(DESKTOP_CONTEXT_ENDPOINT),
        "docker --context desktop-linux info": ok(DESKTOP_INFO),
        "docker --context desktop-linux version": fail(7, "boom"),
    }
    adapter = rt.Adapter(desktop_selection(), REPO, run=make_runner(handlers), wsl_exe="C:\\fake\\wsl.exe")
    result = adapter.run(adapter.docker(["version"]))
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
        "docker context inspect desktop-linux --format": fail(1, "context not found"),
    }
    adapter = rt.Adapter(desktop_selection(), REPO, run=make_runner(handlers), wsl_exe="C:\\fake\\wsl.exe")
    result = adapter.verify_context()
    assert result.returncode != 0
    assert "missing" in result.stderr


def test_recorded_context_non_desktop_endpoint_fails_closed():
    # A context whose endpoint is not positively attributable to Docker Desktop
    # is rejected even though it is named desktop-linux.
    handlers = {
        "docker context inspect desktop-linux --format": ok("ssh://some.remote.host/engine"),
    }
    adapter = rt.Adapter(desktop_selection(), REPO, run=make_runner(handlers), wsl_exe="C:\\fake\\wsl.exe")
    result = adapter.verify_context()
    assert result.returncode != 0
    assert "not positively attributable" in result.stderr


def test_recorded_context_endpoint_changed_fails_closed():
    # A Desktop-attributable endpoint that is not the recorded one = drift.
    drifted = "npipe:////./pipe/dockerDesktopLinuxEngine2"
    handlers = {
        "docker context inspect desktop-linux --format": ok(drifted),
    }
    adapter = rt.Adapter(desktop_selection(), REPO, run=make_runner(handlers), wsl_exe="C:\\fake\\wsl.exe")
    result = adapter.verify_context()
    assert result.returncode != 0
    assert "endpoint changed" in result.stderr


def test_recorded_context_windows_mode_fails_closed():
    handlers = {
        "docker context inspect desktop-linux --format": ok(DESKTOP_CONTEXT_ENDPOINT),
        "docker --context desktop-linux info": ok(DESKTOP_INFO_WINDOWS),
    }
    adapter = rt.Adapter(desktop_selection(), REPO, run=make_runner(handlers), wsl_exe="C:\\fake\\wsl.exe")
    result = adapter.verify_context()
    assert result.returncode != 0
    assert "not Linux" in result.stderr


def test_endpoint_drift_between_two_operations_fails_closed():
    # Endpoint drift between two operations in one workflow: the first adapter
    # op verifies healthy, the context is then redefined to a drifted endpoint,
    # and the second op must fail closed.
    state = {"drifted": False}

    def handler(argv, **kwargs):
        joined = " ".join(argv)
        if "context inspect desktop-linux" in joined:
            if state["drifted"]:
                return ok("ssh://drifted.host/engine")
            return ok(DESKTOP_CONTEXT_ENDPOINT)
        if "--context desktop-linux info" in joined:
            return ok(DESKTOP_INFO)
        if "--context desktop-linux version" in joined:
            return ok("Docker version 29.6.2")
        raise AssertionError("no handler for argv: %r" % (argv,))

    adapter = rt.Adapter(desktop_selection(), REPO, run=handler, wsl_exe="C:\\fake\\wsl.exe")
    first = adapter.run(adapter.docker(["version"]))
    assert first.returncode == 0
    state["drifted"] = True
    second = adapter.run(adapter.docker(["version"]))
    assert second.returncode != 0
    assert "not positively attributable" in second.stderr or "endpoint changed" in second.stderr


def test_direct_helper_fails_closed_after_endpoint_drift():
    # A standalone helper (write_image_lock/resolve_base_image style) uses
    # adapter.run, which re-verifies the context and fails closed after drift
    # before any Docker command reaches the daemon.
    handlers = {
        "docker context inspect desktop-linux --format": ok("ssh://drifted.host/engine"),
        "docker --context desktop-linux info": ok(DESKTOP_INFO),
        "docker --context desktop-linux image inspect": ok("[]"),
    }
    adapter = rt.Adapter(desktop_selection(), REPO, run=make_runner(handlers), wsl_exe="C:\\fake\\wsl.exe")
    result = adapter.run(adapter.docker(["image", "inspect", "python:3.12-slim-bookworm"]))
    assert result.returncode != 0
    assert "not positively attributable" in result.stderr


def test_fake_desktop_linux_name_with_remote_endpoint_rejected(which):
    # A context named desktop-linux whose endpoint is a remote/custom engine is
    # NOT accepted as Docker Desktop ownership evidence.
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers())
    handlers["docker.exe context ls --format"] = ok("desktop-linux\n")
    handlers["docker.exe context show"] = ok("desktop-linux")
    handlers["docker.exe context inspect desktop-linux --format"] = ok("ssh://some.remote.host/engine")
    handlers.update(wsl_handlers())
    sel = select(requested="DockerDesktop", run=make_runner(handlers))
    assert sel["selected_runtime"] is None
    assert sel["probes"]["DockerDesktop"]["reason"] == "no_desktop_linux_context"


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
        run=make_runner({
            "docker context inspect desktop-linux --format": ok(DESKTOP_CONTEXT_ENDPOINT),
            "docker --context desktop-linux info": ok(DESKTOP_INFO),
            "docker --context desktop-linux image inspect": ok(inspected),
        }),
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
        run=make_runner({
            "docker context inspect desktop-linux --format": ok(DESKTOP_CONTEXT_ENDPOINT),
            "docker --context desktop-linux info": ok(DESKTOP_INFO),
            "docker --context desktop-linux pull python:3.12-slim-bookworm": ok(),
            "docker --context desktop-linux image inspect": ok(inspected),
        }),
        wsl_exe="C:\\fake\\wsl.exe",
    )
    out = tmp_path / "base-image.lock.json"
    rec = rbi.resolve_base_image(adapter=adapter, image="python:3.12-slim-bookworm", output=out)
    assert rec["resolved_digest"] == "python@sha256:abcdef"
    assert rec["source_repository"] == "python"
    assert rec["requested_tag"] == "python:3.12-slim-bookworm"
    assert rec["architecture"] == "amd64"
    assert rec["retrieved_utc"]
    assert rec["remote_tag_changed"] is False
    assert out.exists()


def test_base_image_stale_local_tag_refreshed(tmp_path):
    # A stale local tag must not be accepted: resolve pulls the tag and records
    # the new remote digest plus the previously locked digest and change status.
    import json as _json
    import tools.re.resolve_base_image as rbi

    out = tmp_path / "base-image.lock.json"

    inspected = _json.dumps(
        [{"RepoDigests": ["python@sha256:newdigest"], "Id": "sha256:new", "Architecture": "amd64", "Os": "linux"}]
    )

    def handler(argv, **kwargs):
        joined = " ".join(argv)
        if "context inspect desktop-linux" in joined:
            return ok(DESKTOP_CONTEXT_ENDPOINT)
        if "--context desktop-linux info" in joined:
            return ok(DESKTOP_INFO)
        if "pull python:3.12-slim-bookworm" in joined:
            return ok()
        if "--context desktop-linux image inspect" in joined:
            return ok(inspected)
        raise AssertionError("no handler for argv: %r" % (argv,))

    adapter = rt.Adapter(desktop_selection(), str(tmp_path), run=handler, wsl_exe="C:\\fake\\wsl.exe")
    # Seed a stale previous lock.
    out.write_text(_json.dumps({"resolved_digest": "python@sha256:staleold"}), encoding="utf-8")
    rec = rbi.resolve_base_image(adapter=adapter, image="python:3.12-slim-bookworm", output=out)
    assert rec["previously_locked_digest"] == "python@sha256:staleold"
    assert rec["resolved_digest"] == "python@sha256:newdigest"
    assert rec["remote_tag_changed"] is True
    assert rec["resolution_method"]


def test_base_image_selects_matching_repo_digest(tmp_path):
    # RepoDigests may contain entries for other repositories aliased onto the
    # same image; the resolver must select the one matching the requested repo.
    import json as _json
    import tools.re.resolve_base_image as rbi

    inspected = _json.dumps(
        [{"RepoDigests": ["otherrepo@sha256:fff", "python@sha256:correct"],
          "Id": "sha256:id", "Architecture": "amd64", "Os": "linux"}]
    )
    adapter = rt.Adapter(
        desktop_selection(), str(tmp_path),
        run=make_runner({
            "docker context inspect desktop-linux --format": ok(DESKTOP_CONTEXT_ENDPOINT),
            "docker --context desktop-linux info": ok(DESKTOP_INFO),
            "docker --context desktop-linux pull python:3.12-slim-bookworm": ok(),
            "docker --context desktop-linux image inspect": ok(inspected),
        }),
        wsl_exe="C:\\fake\\wsl.exe",
    )
    rec = rbi.resolve_base_image(adapter=adapter, image="python:3.12-slim-bookworm", output=tmp_path / "base-image.lock.json")
    assert rec["resolved_digest"] == "python@sha256:correct"


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


# --------------------------------------------------------------------------- hardening: Trivy triage + explicit policy


def make_policy_entry(advisory_id, package, ecosystem="debian", installed_version="1.0", **overrides):
    entry = {
        "advisory_id": advisory_id,
        "package": package,
        "ecosystem": ecosystem,
        "installed_version": installed_version,
        "decision": "retain",
        "rationale": "explicit test policy entry",
        "package_necessity": "test necessity",
        "functionality_exercised": "test exercised",
        "mitigating_controls": "test controls",
        "review_date": "2026-08-03",
        "review_condition": "re-review when a vendor fix is published",
    }
    entry.update(overrides)
    return entry


def critical_sample(*crits):
    vulns = []
    for cid, pkg, version in crits:
        vulns.append({"VulnerabilityID": cid, "Severity": "CRITICAL", "PkgName": pkg,
                      "InstalledVersion": version, "FixedVersion": ""})
    return {"Results": [{"Class": "os-pkgs", "Type": "debian", "Vulnerabilities": vulns}]}


def test_trivy_new_unfixed_critical_without_policy_fails():
    import tools.re.summarize_trivy as st
    sample = critical_sample(("CVE-NEW", "zlib1g", "1.2.13"))
    s = st.summarize(sample, policy=[])  # no policy entries
    assert s["gate"]["all_unfixed_critical_policy_matched"] is False
    assert s["gate"]["unfixed_critical_policy_failures"][0]["reason"] == "missing policy entry"
    assert s["gate"]["ok"] is False
    r = s["criticals"][0]
    assert r["policy"]["match_kind"] == "missing"
    assert r["policy"]["decision"] is None
    # Generated recommendation is present but never counts as acceptance.
    assert "recommendation" in r["policy"]


def test_trivy_exact_policy_match_passes():
    import tools.re.summarize_trivy as st
    sample = critical_sample(("CVE-1", "zlib1g", "1.2.13"))
    policy = [make_policy_entry("CVE-1", "zlib1g", installed_version="1.2.13")]
    s = st.summarize(sample, policy=policy)
    assert s["gate"]["ok"] is True
    assert s["gate"]["all_unfixed_critical_policy_matched"] is True
    r = s["criticals"][0]
    assert r["policy"]["match_kind"] == "exact"
    assert r["policy"]["decision"]["decision"] == "retain"
    assert r["policy"]["decision"]["review_condition"]


def test_trivy_changed_installed_version_fails():
    import tools.re.summarize_trivy as st
    sample = critical_sample(("CVE-1", "zlib1g", "1.2.13"))
    policy = [make_policy_entry("CVE-1", "zlib1g", installed_version="9.9.9")]  # stale version
    s = st.summarize(sample, policy=policy)
    assert s["gate"]["ok"] is False
    r = s["criticals"][0]
    assert r["policy"]["match_kind"] == "mismatch"
    assert "installed version" in r["policy"]["reason"]


def test_trivy_changed_package_or_ecosystem_fails():
    import tools.re.summarize_trivy as st
    sample = critical_sample(("CVE-1", "libsqlite3-0", "3.40.1"))
    policy = [make_policy_entry("CVE-1", "zlib1g", installed_version="3.40.1")]  # wrong package
    s = st.summarize(sample, policy=policy)
    assert s["gate"]["ok"] is False
    assert s["criticals"][0]["policy"]["match_kind"] == "mismatch"
    # wrong ecosystem
    policy2 = [make_policy_entry("CVE-1", "libsqlite3-0", ecosystem="alpine", installed_version="3.40.1")]
    s2 = st.summarize(sample, policy=policy2)
    assert s2["gate"]["ok"] is False
    assert s2["criticals"][0]["policy"]["match_kind"] == "mismatch"
    assert "ecosystem" in s2["criticals"][0]["policy"]["reason"]


def test_trivy_incomplete_policy_fails():
    import tools.re.summarize_trivy as st
    sample = critical_sample(("CVE-1", "zlib1g", "1.2.13"))
    # Missing package_necessity -> incomplete.
    policy = [make_policy_entry("CVE-1", "zlib1g", installed_version="1.2.13", package_necessity="")]
    s = st.summarize(sample, policy=policy)
    assert s["gate"]["ok"] is False
    assert s["criticals"][0]["policy"]["match_kind"] == "incomplete"


def test_trivy_stale_and_orphaned_entries_reported_and_fail():
    import tools.re.summarize_trivy as st
    sample = critical_sample(("CVE-1", "zlib1g", "1.2.13"))
    policy = [
        make_policy_entry("CVE-1", "zlib1g", installed_version="1.2.13"),
        make_policy_entry("CVE-ORPHAN", "tar", installed_version="1.34"),  # not in scan
    ]
    s = st.summarize(sample, policy=policy)
    assert s["gate"]["ok"] is False
    assert len(s["gate"]["stale_policy_entries"]) == 1
    assert s["gate"]["stale_policy_entries"][0]["advisory_id"] == "CVE-ORPHAN"


def test_trivy_previously_accepted_now_fixable_fails():
    import tools.re.summarize_trivy as st
    # A policy entry whose advisory now has a fixed version.
    sample = {"Results": [{"Class": "os-pkgs", "Type": "debian", "Vulnerabilities": [
        {"VulnerabilityID": "CVE-1", "Severity": "CRITICAL", "PkgName": "zlib1g",
         "InstalledVersion": "1.2.13", "FixedVersion": "1.2.14"}
    ]}]}
    policy = [make_policy_entry("CVE-1", "zlib1g", installed_version="1.2.13")]
    s = st.summarize(sample, policy=policy)
    assert s["gate"]["zero_fixable_criticals"] is False
    assert s["gate"]["newly_fixable_accepted"] == [{
        "advisory_id": "CVE-1", "package": "zlib1g", "ecosystem": "debian",
        "installed_version": "1.2.13",
    }]
    assert s["gate"]["ok"] is False


def test_trivy_generated_suggestion_does_not_count_as_acceptance(tmp_path):
    import tools.re.summarize_trivy as st
    # Even a complete-looking generated recommendation must not satisfy the gate.
    sample = critical_sample(("CVE-G", "libxml2", "2.9.14"))
    s = st.summarize(sample, policy=[])
    assert s["gate"]["all_unfixed_critical_policy_matched"] is False
    inp = tmp_path / "in.json"
    inp.write_text(json.dumps(sample))
    empty_policy = tmp_path / "empty-policy.json"
    empty_policy.write_text(json.dumps({"entries": []}))
    rc = st.main(["--input", str(inp), "--output", str(tmp_path / "out.json"),
                  "--markdown", str(tmp_path / "out.md"), "--gate",
                  "--policy", str(empty_policy)])
    # empty policy -> no entries -> gate fails.
    assert rc == 1


def test_trivy_ambiguous_package_classification():
    import tools.re.summarize_trivy as st
    assert st.classify_package("libcapstone4")[2] == "capstone"
    assert st.classify_package("libcapstone4")[1] is False
    assert st.is_runtime_base("libcapstone4") is False
    assert st.classify_package("libcap")[2] == "runtime-base"
    assert st.is_runtime_base("libcap") is True
    assert st.classify_package("libcap2")[1] is True
    assert st.classify_package("libc6")[1] is True
    assert st.classify_package("libc-bin")[1] is True
    assert st.classify_package("tar")[1] is True
    assert st.classify_package("dash")[1] is True
    assert "libcap" not in st.classify_package("libcapstone4")[0].lower()


def test_trivy_libcapstone4_reachability_describes_disassembly():
    import tools.re.summarize_trivy as st
    sample = critical_sample(("CVE-2025-68114", "libcapstone4", "4.0.2-5"))
    s = st.summarize(sample, policy=[make_policy_entry("CVE-2025-68114", "libcapstone4", installed_version="4.0.2-5")])
    r = s["criticals"][0]
    assert r["family"] == "capstone"
    assert "angr/radare2" in r["reachability"]
    assert "runtime-base" not in r["reachability"]
    assert "disassembly" in r["purpose"]


def test_trivy_all_nine_current_critical_match_policy():
    import tools.re.summarize_trivy as st
    root = os.path.dirname(__file__)
    policy_path = os.path.join(root, "containers", "re-runner", "vulnerability-acceptance.json")
    entries = st.load_policy(policy_path)
    assert len(entries) == 9
    crits = [
        ("CVE-2025-68114", "libcapstone4", "4.0.2-5"),
        ("CVE-2026-58016", "libglib2.0-0", "2.74.6-2+deb12u9"),
        ("CVE-2025-7458", "libsqlite3-0", "3.40.1-2+deb12u2"),
        ("CVE-2026-6653", "libxml2", "2.9.14+dfsg-1.3~deb12u6"),
        ("CVE-2026-13221", "perl-base", "5.36.0-7+deb12u3"),
        ("CVE-2026-42496", "perl-base", "5.36.0-7+deb12u3"),
        ("CVE-2026-57433", "perl-base", "5.36.0-7+deb12u3"),
        ("CVE-2026-8376", "perl-base", "5.36.0-7+deb12u3"),
        ("CVE-2023-45853", "zlib1g", "1:1.2.13.dfsg-1"),
    ]
    sample = critical_sample(*crits)
    s = st.summarize(sample, policy=entries)
    assert s["gate"]["ok"] is True
    assert s["gate"]["all_unfixed_critical_policy_matched"] is True
    assert len(s["gate"]["stale_policy_entries"]) == 0
    assert all(c["policy"]["match_kind"] == "exact" for c in s["criticals"])


def test_trivy_every_high_advisory_survives_sanitization():
    import tools.re.summarize_trivy as st
    sample = {"Results": [{"Class": "os-pkgs", "Type": "debian", "Vulnerabilities": [
        {"VulnerabilityID": "CVE-H-1", "Severity": "HIGH", "PkgName": "libcurl3-gnutls",
         "InstalledVersion": "7.88", "FixedVersion": "7.88.1", "Layer": {"DiffID": "sha256:l1"}},
        {"VulnerabilityID": "CVE-H-2", "Severity": "HIGH", "PkgName": "libcurl3-gnutls",
         "InstalledVersion": "7.88", "FixedVersion": "", "Layer": {"DiffID": "sha256:l2"}},
        {"VulnerabilityID": "CVE-H-3", "Severity": "HIGH", "PkgName": "libexpat1",
         "InstalledVersion": "2.5", "FixedVersion": "", "Layer": {"DiffID": "sha256:l3"}},
    ]}]}
    s = st.summarize(sample, policy=[])
    ids = {r["id"] for r in s["highs"]}
    assert ids == {"CVE-H-1", "CVE-H-2", "CVE-H-3"}
    assert s["highs_by_package"][0]["findings"] == 2


def test_trivy_high_per_finding_fixed_versions_and_paths_preserved():
    import tools.re.summarize_trivy as st
    sample = {"Results": [{"Class": "lang-pkgs", "Type": "python", "Vulnerabilities": [
        {"VulnerabilityID": "CVE-P-1", "Severity": "HIGH", "PkgName": "angr",
         "InstalledVersion": "9.3.1", "FixedVersion": "9.3.2", "Paths": ["/usr/local/lib/angr"]},
        {"VulnerabilityID": "CVE-P-2", "Severity": "HIGH", "PkgName": "angr",
         "InstalledVersion": "9.3.1", "FixedVersion": "", "Paths": []},
    ]}]}
    s = st.summarize(sample, policy=[])
    by_id = {r["id"]: r for r in s["highs"]}
    assert by_id["CVE-P-1"]["fixed_version"] == "9.3.2"
    assert by_id["CVE-P-1"]["fixed_status"] == "fixed"
    assert by_id["CVE-P-1"]["dependency_path"] == ["/usr/local/lib/angr"]
    assert by_id["CVE-P-2"]["fixed_version"] is None
    assert by_id["CVE-P-2"]["fixed_status"] == "unfixed"


def test_trivy_gate_fails_on_fixable_critical(tmp_path):
    import tools.re.summarize_trivy as st
    sample = {"Results": [{"Class": "lang-pkgs", "Type": "python", "Vulnerabilities": [
        {"VulnerabilityID": "CVE-2", "Severity": "CRITICAL", "PkgName": "angr",
         "InstalledVersion": "9.3.1", "FixedVersion": "9.3.2"}
    ]}]}
    inp = tmp_path / "in.json"
    inp.write_text(json.dumps(sample))
    pol = tmp_path / "pol.json"
    pol.write_text(json.dumps({"entries": []}))
    rc = st.main(["--input", str(inp), "--output", str(tmp_path / "out.json"),
                  "--markdown", str(tmp_path / "out.md"), "--gate",
                  "--policy", str(pol)])
    # fixable critical -> gate fails regardless of policy.
    assert rc == 1


def test_trivy_cli_gate_uses_default_tracked_policy(tmp_path):
    # Without --policy, main() defaults to containers/re-runner/vulnerability-acceptance.json.
    # Use all 9 tracked criticals so no policy entry is stale.
    import tools.re.summarize_trivy as st
    root = os.path.dirname(__file__)
    crits = [
        ("CVE-2025-68114", "libcapstone4", "4.0.2-5"),
        ("CVE-2026-58016", "libglib2.0-0", "2.74.6-2+deb12u9"),
        ("CVE-2025-7458", "libsqlite3-0", "3.40.1-2+deb12u2"),
        ("CVE-2026-6653", "libxml2", "2.9.14+dfsg-1.3~deb12u6"),
        ("CVE-2026-13221", "perl-base", "5.36.0-7+deb12u3"),
        ("CVE-2026-42496", "perl-base", "5.36.0-7+deb12u3"),
        ("CVE-2026-57433", "perl-base", "5.36.0-7+deb12u3"),
        ("CVE-2026-8376", "perl-base", "5.36.0-7+deb12u3"),
        ("CVE-2023-45853", "zlib1g", "1:1.2.13.dfsg-1"),
    ]
    sample = critical_sample(*crits)
    inp = tmp_path / "in.json"
    inp.write_text(json.dumps(sample))
    # Run from the repo root so the default policy path resolves.
    cwd = os.getcwd()
    try:
        os.chdir(root)
        rc = st.main(["--input", str(inp), "--output", str(tmp_path / "out.json"),
                      "--markdown", str(tmp_path / "out.md"), "--gate"])
        assert rc == 0
    finally:
        os.chdir(cwd)
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
    # No mutable :latest image fallback remains in the compose defaults.
    assert "image: ${SYFT_IMAGE:-anchore/syft:v1.19.0}" in text
    assert "image: ${TRIVY_IMAGE:-aquasec/trivy:0.57.1}" in text


def test_no_latest_image_fallback_in_toolchain():
    root = os.path.dirname(__file__)
    tracked = [
        "compose.re.yml",
        ".env.re.example",
        "tools/re/bootstrap-re-containers.ps1",
        "tools/re/bootstrap-re-containers.sh",
        "tools/re/scan-re-image.ps1",
        "tools/re/build-upstream-images.ps1",
        "tools/re/re_runtime.py",
        "tools/re/write_image_lock.py",
        "tools/re/resolve_base_image.py",
        "tools/re/summarize_trivy.py",
        "tools/re/run-re-container.ps1",
        "tools/re/verify-re-containers.ps1",
        "tools/re/uninstall-re-containers.ps1",
    ]
    for rel in tracked:
        text = open(os.path.join(root, rel), encoding="utf-8").read()
        # A runtime/build image reference must never use :latest; versioned
        # seeds are allowed because the digest is resolved before use.
        lines = [
            ln for ln in text.splitlines()
            if ":latest" in ln and "angr/angr" not in ln and not ln.strip().startswith("#")
        ]
        assert not lines, f"{rel} contains :latest image reference: {lines}"
