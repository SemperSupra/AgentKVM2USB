"""Deterministic mocked tests for the issue #14 Docker runtime selection and adapter.

No real Docker daemon is required. ``select_runtime``/``Adapter``/Beagle routing
are exercised through an injected runner that scripts subprocess responses, so
the full runtime matrix is covered deterministically on any host.
"""

from __future__ import annotations

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
DESKTOP_CONTEXT_LS = "desktop-linux *   Docker Desktop   npipe:////./pipe/dockerDesktopLinuxEngine"
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


def desktop_handlers(info: Proc = ok(DESKTOP_INFO), status: Proc = ok(DESKTOP_STATUS_RUNNING)):
    # Needles are anchored to docker.exe so they never cross-match the WSL
    # docker argv (which contains bare "docker --version"/"docker info").
    return {
        "docker.exe --version": ok(DESKTOP_VERSION),
        "docker.exe desktop status --format json": status,
        "docker.exe context show": ok(DESKTOP_CONTEXT_SHOW),
        "docker.exe context ls": ok(DESKTOP_CONTEXT_LS),
        "docker.exe info": info,
        "docker.exe compose version": ok(COMPOSE_VERSION),
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


def test_select_both_healthy_prefers_wsl_without_desktop_context(which):
    which({"docker": True, "wsl": True})
    handlers = dict(desktop_handlers())
    handlers["docker.exe context show"] = ok("custom")
    handlers["docker.exe context ls"] = ok("custom  custom  npipe:////./pipe/custom")
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
    handlers["docker.exe compose version"] = fail(1, "plugin not installed")
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
    assert meta["docker_desktop"]["active_context"] == "desktop-linux"
    assert "endpoint" in meta["docker_desktop"]
    assert meta["wsl"]["distribution"] == "Ubuntu"
    assert meta["wsl"]["version"] == 2
    assert "distributions" in meta["wsl"]
    assert sel["generated_utc"] == "2026-01-01T00:00:00+00:00"


# --------------------------------------------------------------------------- adapter


def wsl_selection():
    return {"selected_runtime": "WslEngine", "wsl_distribution": "Ubuntu"}


def desktop_selection():
    return {"selected_runtime": "DockerDesktop", "wsl_distribution": "Ubuntu"}


def wslpath_runner(converted):
    def runner(argv, **kwargs):
        assert argv[:4] == ["C:\\fake\\wsl.exe", "-d", "Ubuntu", "--exec"]
        assert argv[4] == "wslpath"
        assert argv[5] == "-a"
        assert len(argv) == 7  # the Windows path is a single discrete argument
        return Proc(0, converted)

    return runner


def test_adapter_desktop_argv():
    adapter = rt.Adapter(desktop_selection(), REPO, run=make_runner({}), wsl_exe="C:\\fake\\wsl.exe")
    assert adapter.docker(["--version"]) == ["docker", "--version"]
    assert adapter.compose(["version"]) == ["docker", "compose", "version"]
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
    adapter = rt.Adapter(desktop_selection(), REPO, run=make_runner({"docker info": fail(7, "boom")}), wsl_exe="C:\\fake\\wsl.exe")
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
        "metadata": {"os_type": "windows"},
    }
    path = os.path.join(str(tmp_path), "runtime.json")
    assert rt.write_runtime_json(selection, path) == os.path.abspath(path)
    restored = rt.read_runtime_json(path)
    adapter = rt.Adapter(restored, REPO, run=make_runner({}), wsl_exe="C:\\fake\\wsl.exe")
    assert adapter.runtime == "DockerDesktop"
    assert adapter.docker(["ps"]) == ["docker", "ps"]


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
