# Issue #14 Runtime Correction Handoff

## Resume Point

Repository: `SemperSupra/AgentKVM2USB`

Worktree: `C:\Users\Mark\Projects\AgentKVM2USB-issue14`

Branch: `issue-14-container-re-toolchain`

PR: [#15](https://github.com/SemperSupra/AgentKVM2USB/pull/15)

Current base/head before this documentation commit: `914fc72120e98d2bc02f58aecc92db17927f420d` (`Document container-first reverse-engineering architecture`). PR #15 is draft and targets `recovery/agentkvm2usb-app-capabilities`.

PR #13 is unrelated Phase B keyboard work and must remain untouched.

## Latest GitHub Scope

The latest issue #14 review assigns only the runtime correction slice:

- detect and select Docker Desktop Linux or native Docker Engine inside WSL2;
- add `-ContainerRuntime Auto|DockerDesktop|WslEngine`, default `Auto`, and `-NoStartDockerDesktop`;
- use one runtime adapter across bootstrap, verification, Compose, image builds, image locking, SBOM, Trivy, Beagle, run wrappers, and uninstall;
- do not install Docker Desktop or Docker Engine automatically;
- fix Windows-to-WSL path conversion without an intermediate shell parser;
- enforce shell line endings with `.gitattributes` and validate the actual checkout;
- allow general tooling without the Linux Beagle API;
- retain a Windows Beagle API host-shim fallback that emits the normalized JSONL format;
- add deterministic mocked runtime/path/dependency tests;
- keep PR #15 draft until automatic and explicit runtime-selection workstation gates pass.

Authoritative review comment: issue #14 comment `5166102442`.

## Prior Validation Evidence

Archive:

- `C:\Users\Mark\Downloads\agentkvm2usb-container-re-toolchain.zip`
- Expected and verified SHA-256: `2579db0b829da5f2c16ba65ae978d81c1fed2fcf48628ff8cce73ed0e7a2922e`
- 23 members; no absolute paths, drive-qualified paths, traversal, or symlink entries.
- Extracted only to ignored `.work\incoming\agentkvm2usb-container-re-toolchain`.
- PR #15 was treated as authoritative. No archive-only differences were applied.

Total Phase inventory:

- Inventory: `.work\vendor\totalphase\inventory.json`
- Five source archives were staged and hashed under ignored `.work\vendor\totalphase`.
- Present: Windows Data Center v8.10, Linux Data Center v8.10, macOS Data Center v8.10, Windows Beagle API v6.00, and TotalPhaseUSB v4.0.0.
- Windows Beagle DLL/API files are present.
- Linux x86-64 `beagle.so` is absent. This must block only direct containerized live Beagle capture, not general image/tool validation.
- Vendor binaries must remain ignored and outside Git and container images.

Host/WSL evidence:

- Ubuntu WSL2 exists and was running.
- Ubuntu did not have a Docker CLI/daemon/Compose plugin available to the PR #15 bootstrap.
- A Windows Docker CLI and Docker Desktop Linux server were present during prior parse-only checks. Do not assume this remains healthy; probe it through the new adapter.
- Do not install Docker Desktop or Docker Engine automatically. An already-installed Desktop may be started only through its supported CLI, with bounded polling and `-NoStartDockerDesktop` honored.

Prior validation:

- Host `docker compose -f compose.re.yml config --format json`: passed parse-only.
- Seven services statically asserted: `network_mode: none`, `read_only: true`, `cap_drop: ALL`, `no-new-privileges:true`, and no Docker socket mounts.
- PowerShell syntax: 5 files passed.
- Raw WSL `bash -n` failed because checked-out `.sh` files had CRLF (`do\r`). Temporary LF-normalized copies passed, but that is insufficient for the new exit gate.
- Python compile passed.
- `git diff --check` passed.
- Unit tests: `68 passed`.
- No images were pulled or built; no image lock, SBOM, or Trivy result was generated.
- No target HID reports, vendor OUT transfers, firmware, FPGA, EDID, flash, or other persistent-device writes occurred.

## Implementation Plan For Next Agent

1. Fetch `origin/main`, `origin/issue-14-container-re-toolchain`, issue #14, and PR #15 reviews. Preserve this handoff and unrelated work.
2. Read the existing `tools/re/*.ps1`, `tools/re/*.sh`, `compose.re.yml`, `containers/re-runner`, and current tests.
3. Add a shared runtime module/implementation, preferably a PowerShell module or common script plus a small testable Python/helper layer where the repository’s existing patterns support it. Do not duplicate probes in each entrypoint.
4. Implement probes with structured diagnostics for:
   - Docker Desktop missing, stopped, start-disabled, Windows-container mode, CLI missing, server unavailable, Compose unavailable;
   - WSL distro missing, non-WSL2, Docker CLI missing, daemon stopped/unavailable, Compose unavailable, installed-but-stopped service;
   - explicit unavailable runtime overrides and `Auto` selection rules.
5. Write `.work\re\runtime.json` after selection with both probe results, selected runtime/reason, client/server/Compose versions, OS type, server OS, context/endpoint, WSL details, and timestamp.
6. Make all Docker operations consume the selected adapter. Docker Desktop uses Windows `docker.exe` from the Windows repo path. WslEngine converts the repo path once with a discrete `wslpath` argument and runs inside the selected distro. Preserve exit codes/stderr and avoid string-reparsed command construction.
7. Add path tests for the current repo, spaces, parentheses, another drive if available, invalid distro, and malformed conversion. The observed bug was `C:\Users\Mark\...` becoming `C:Users...`.
8. Add `.gitattributes` with at least:

   ```gitattributes
   *.sh text eol=lf
   *.ps1 text eol=crlf
   *.cmd text eol=crlf
   *.yml text eol=lf
   *.yaml text eol=lf
   ```

   Renormalize tracked shell files and run WSL `bash -n` against the actual checkout, not temporary copies.
9. Add a Docker Desktop-compatible PowerShell route for pinned Ghidra/Binwalk source verification, extraction, and `docker build`; do not run the Bash bootstrap through Ubuntu in Desktop mode.
10. Keep missing Linux Beagle API nonfatal for general tooling. Select Linux API mode only when `beagle.so` exists. Otherwise implement/use a minimal Windows API host shim that loads ignored vendor files, emits the existing normalized JSONL, records hashes/API version, and writes only ignored `.work` evidence.
11. Add mocked tests for every required runtime matrix case, metadata, path handling, no socket mounts, Linux API absence, and Windows API fallback. Tests must not require a daemon.
12. Run workstation commands in this order:

   ```powershell
   .\tools\re\bootstrap-re-containers.cmd -ContainerRuntime Auto -RefreshVendorInventory -InstallUsbipd
   pwsh -NoProfile -File .\tools\re\verify-re-containers.ps1 -ContainerRuntime Auto
   pwsh -NoProfile -File .\tools\re\verify-re-containers.ps1 -ContainerRuntime DockerDesktop
   pwsh -NoProfile -File .\tools\re\verify-re-containers.ps1 -ContainerRuntime WslEngine -WslDistribution Ubuntu
   ```

   Explicit runtime commands may fail clearly when that candidate is unavailable; record each probe rather than switching silently.
13. Validate Compose, runner, Ghidra, Radare2, angr, Binwalk, locks, SBOM, offline Trivy, Total Phase inventory, actual shell syntax, unit tests, and `git diff --check`.
14. Push the implementation, keep PR #15 draft, and post `CHECKPOINT` and `HANDOFF` to issue #14 with runtime metadata, probe results, selected runtime/reason, host actions, image results, tests, blockers, PR #13 untouched, and no persistent writes.

## Safety Rules

- Do not use the target KVM for this slice.
- Do not send keyboard reports, feature reports, unknown vendor OUT transfers, or re-enumeration requests.
- Do not flash or write firmware, FPGA, EDID, EEPROM, flash, or other persistent state.
- Do not install Docker Desktop, Docker Engine, reverse-engineering suites, Wireshark, or USBPcap automatically.
- Do not copy Total Phase or other vendor binaries into Git or images.
- Do not mount the Docker socket into any analysis container.
- Do not merge PR #15 or mark it ready before the required workstation gates pass.
