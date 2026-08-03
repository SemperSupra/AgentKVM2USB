# Container-First Reverse-Engineering Toolchain

This environment supports issue #14 while minimizing persistent changes to the
Windows host. Reverse-engineering and trace-analysis tools run headlessly in
short-lived containers. Raw captures, vendor binaries, extracted firmware, and
analysis databases stay under ignored `.work/` directories.

## Design rules

1. Reuse upstream or publisher-maintained images before creating a project image.
2. When an upstream project publishes a Dockerfile but not a maintained image,
   build that Dockerfile from a pinned, verified upstream release.
3. Build a project-specific image only for the small integration layer that no
   upstream image provides.
4. Run analysis containers with no network, a read-only root filesystem,
   dropped Linux capabilities, and `no-new-privileges` by default.
5. Mount evidence read-only and write generated results only to `.work/re/output`
   or `.work/re/projects`.
6. Resolve pulled tags to immutable repository digests and record image IDs,
   architecture, timestamps, and digests in `.work/re/images.lock.json`.
7. Keep proprietary Total Phase and Epiphan artifacts outside Git. Record hashes
   and provenance only.

## Tool selection and provenance

| Capability | Source | Deployment decision |
| --- | --- | --- |
| Radare2, r2ghidra, r2dec | `radare/radare2` publisher image | Pull the published versioned image and lock its digest. |
| angr symbolic/static analysis | Project runner image | The `angr/angr` publisher image is a bare dev base without angr installed, so angr is pinned in the runner's Python requirements and runs from `agentkvm2usb/re-runner`. |
| Ghidra headless/PyGhidra | NSA Ghidra release Dockerfile | Build the unmodified upstream Dockerfile from the official release ZIP after SHA-256 verification. A community image is opt-in only. |
| Binwalk v3 | ReFirmLabs upstream Dockerfile | Build the unmodified upstream Dockerfile from the pinned release tag. |
| USB trace decoding | Wireshark/TShark | Included in the small project runner because Wireshark does not publish a suitable stateless CLI image for this workflow. |
| ARM disassembly/debug helpers | GNU Arm binutils, GDB multiarch, QEMU user | Included in the runner from Debian packages. |
| Binary parsing | Capstone, Kaitai runtime, Construct, PyUSB, Scapy, r2pipe | Version-pinned Python dependencies inside the runner. |
| SBOM generation | Anchore Syft image (`v1.19.0`) | Pull the versioned tag and lock its digest; scan a temporary `docker save` archive without mounting the Docker socket. |
| Vulnerability scanning | Aqua Trivy image (`0.57.1`) | Pull the versioned tag and lock its digest; prefetch the database, then scan a temporary image archive offline without mounting the Docker socket. |
| Beagle USB 12 capture | Total Phase Linux x86-64 API | Stage the user-downloaded API under `.work/vendor`; mount it read-only into the runner. |

The only project-authored image is `agentkvm2usb/re-runner`. It contains the glue needed
for TShark, ARM utilities, Python trace parsers, and the mounted Total Phase API.
It does not contain vendor downloads or captured evidence.

## Docker runtime selection

Every toolchain entrypoint (`bootstrap`, `verify`, `run`, `scan`, `uninstall`)
accepts `-ContainerRuntime Auto|DockerDesktop|WslEngine` (default `Auto`) and
`-NoStartDockerDesktop`. A shared runtime adapter
(`tools/re/runtime.psm1` + `tools/re/re_runtime.py`) probes both candidates,
applies the issue #14 selection rules, records the decision in
`.work/re/runtime.json`, and routes every Docker/Compose operation through the
selected transport. The same selection is used across bootstrap, verification,
Compose, image builds, image locking, SBOM, Trivy, Beagle, run wrappers, and
uninstall — a runtime never switches silently mid-run.

- Docker Desktop mode runs the Windows `docker`/`docker compose` CLI from the
  Windows repository path and never performs Windows-to-WSL path conversion.
  It requires **positive Docker Desktop identity**: supported
  `docker desktop status` evidence, or (for older Desktop versions) installed
  Desktop application/service evidence plus a Desktop-owned Linux context
  (`desktop-linux` or a `dockerDesktopLinuxEngine` endpoint). An arbitrary
  custom or remote Windows context that merely reaches a Linux daemon is
  rejected. The user's global Docker context is never mutated.
- Every Docker Desktop command is invoked with the recorded context explicitly
  (`docker --context <recorded-context> ...`), and the recorded context/endpoint
  is re-verified before significant operations — a missing, changed, redirected,
  or Windows-container context fails closed instead of silently running against
  another daemon.
- WSL Engine mode runs Docker inside the selected WSL2 distribution through
  `wsl.exe --cd <wsl path> --exec docker`, so the repository path is converted
  once with a discrete `wslpath -a` argument and never re-parsed by a shell.
- `Auto` selects a single healthy runtime; when both are healthy it prefers the
  active healthy Docker Desktop Linux context, otherwise the native WSL Engine.
  An explicit selection wins and fails clearly when that candidate is
  unavailable. If neither is healthy a structured diagnostic is emitted and
  nothing is installed.
- A Docker Desktop that is installed but stopped may be started through
  `docker desktop start` with bounded polling unless `-NoStartDockerDesktop` is
  passed. Docker Desktop and Docker Engine are never installed automatically.
- A context is accepted as Docker Desktop only when its endpoint is positively
  attributable to Docker Desktop (the Docker Desktop Linux named-pipe
  endpoint). A context merely named `desktop-linux` with a custom or remote
  endpoint is rejected. Every adapter-backed Docker/Compose operation
  re-verifies the recorded context (exists, still Desktop-attributable, still
  resolves to the recorded endpoint, still reports a Linux daemon) and fails
  closed on drift, including inside `resolve_base_image.py` and
  `write_image_lock.py`. Verification never recurses (it uses the raw runner).

## Reproducible build inputs

- The official Python base image (`python:3.12-slim-bookworm`) is pulled and
  inspected on every bootstrap refresh through the selected adapter/context, so
  a stale local cache is never treated as the current registry state. The
  RepoDigest matching the requested repository is selected (not the first
  entry). `.work/re/base-image.lock.json` records the requested tag, the
  previously locked digest, the newly resolved digest, whether the remote tag
  changed, architecture/OS, resolution method, and retrieval timestamp. The
  resolved digest is passed to the build as
  `PYTHON_BASE_IMAGE=python@sha256:<digest>`.
- Python dependencies are hash-locked: `containers/re-runner/requirements.in` is
  the human-maintained input, and the generated
  `containers/re-runner/requirements.lock.txt` (pip-compile `--generate-hashes`)
  is installed with `--require-hashes`.
- Debian package versions are captured in the generated CycloneDX/SPDX SBOMs.
- All pulled images use versioned publisher tags (no `:latest` fallback) and are
  resolved to immutable digests; the exact requested tag and resolved digest are
  recorded in `.work/re/images.lock.json`, whose `runtime` block embeds the
  selected runtime, context/distribution, endpoint, client/server versions,
  server OS, Compose version, the SHA-256 of `.work/re/runtime.json`, and both
  the runtime-selection and image-lock timestamps.

## Vulnerability triage

`tools/re/summarize_trivy.py` produces a sanitized JSON and Markdown triage with
an **individual record for every CRITICAL and HIGH advisory** (package-level HIGH
aggregation is an additional view, never a replacement). The full Trivy JSON is
preserved only under ignored `.work/re/output`.

Each record includes advisory/CVE ID, severity, package and ecosystem, installed
and fixed version, fixed/unfixed status, Trivy vendor status and data source
when available, source layer, dependency path, presence in the final runtime
image, package purpose, and a **package-specific reachability/exposure
assessment** — base/runtime libraries (zlib, glib, SQLite, Perl, libxml2, …) are
assessed as exercised at container startup or ordinary analysis, not only while
processing mounted evidence.

Every remaining unfixed CRITICAL carries an explicit decision record
(`remove`, `isolate`, `split`, or `retain`) with rationale, package necessity,
whether affected functionality is exercised, mitigating isolation controls, and
a review/expiry condition (e.g. a vendor fix being published).

The acceptance gate (`--gate`) fails when any CRITICAL finding has a
vendor-provided fixed version, fails when any unfixed CRITICAL lacks a complete
decision record, and reports fixable HIGH findings separately. It never claims
that runtime hardening eliminates an underlying vulnerability.

## Host boundary

The following remain on the Windows/WSL host because containers cannot replace
them:

- A usable Docker runtime: the Windows Docker Desktop Linux engine or a native
  WSL2 Docker Engine with the Compose plugin. Neither is installed by the
  toolchain.
- `usbipd-win`, only when the Beagle must be attached to WSL. Installation and
  removal use WinGet.
- Wireshark/USBPcap, only for capturing the Windows official Epiphan KvmApp's
  host-facing USB traffic. Installation and removal use WinGet. Analysis of the
  resulting capture occurs in the container.
- The official Epiphan application, drivers, and Total Phase downloads when a
  differential experiment specifically requires them.

Ghidra, Java, Python analysis environments, Radare2, angr, Binwalk, TShark,
GNU Arm tools, Syft, and Trivy are not installed on Windows. No analysis container receives the Docker daemon socket.

## Total Phase staging

The default source is:

```text
C:\Users\Mark\Downloads\TotalPhase
```

`inventory-totalphase.ps1` recursively copies those files into ignored
`.work/vendor/totalphase`, calculates SHA-256 for every artifact, extracts
archives, classifies drivers/API/Data Center packages, and locates Linux
x86-64 Beagle API candidates. Vendor files are never copied into a container
image or committed to Git.

For containerized capture:

1. Install `usbipd-win` using the bootstrap opt-in.
2. From an elevated Windows terminal, bind the Beagle once if required.
3. Attach it to WSL with `usbipd attach --wsl --busid <BUSID>`.
4. Run `run-re-container.ps1 beagle ...`.

The wrapper finds the attached USB device and staged Linux Beagle API, mounts
only the required device node and vendor directory, and removes the capture
container when it exits.

## Bootstrap

From the repository root:

```powershell
.\tools\re\bootstrap-re-containers.cmd -RefreshVendorInventory
```

Runtime selection is explicit when needed:

```powershell
.\tools\re\bootstrap-re-containers.cmd -ContainerRuntime DockerDesktop
.\tools\re\bootstrap-re-containers.cmd -ContainerRuntime WslEngine -WslDistribution Ubuntu
```

Install only the host USB plumbing needed for Beagle access:

```powershell
.\tools\re\bootstrap-re-containers.cmd `
  -RefreshVendorInventory `
  -InstallUsbipd
```

Add Windows USBPcap/Wireshark only for the official-app differential capture:

```powershell
.\tools\re\bootstrap-re-containers.cmd `
  -InstallWindowsCapture
```

The bootstrap deliberately does not install Docker Desktop or a WSL Docker
Engine. It probes and uses an available runtime (see "Docker runtime selection"
above), and an already-installed Docker Desktop may be started with bounded
polling unless `-NoStartDockerDesktop` is passed. In Docker Desktop mode the
pinned Ghidra/Binwalk upstream images are built by
`tools/re/build-upstream-images.ps1` through the Windows Docker CLI; in WSL
Engine mode the WSL-native `bootstrap-re-containers.sh` pipeline is used.

## Verification

```powershell
pwsh -NoProfile -File .\tools\re\verify-re-containers.ps1 -ContainerRuntime Auto
pwsh -NoProfile -File .\tools\re\verify-re-containers.ps1 -ContainerRuntime DockerDesktop
pwsh -NoProfile -File .\tools\re\verify-re-containers.ps1 -ContainerRuntime WslEngine -WslDistribution Ubuntu
```

Verification checks Docker/Compose, validates the Compose model, runs each
analysis tool in a disposable container, and confirms the Total Phase inventory.
The missing Linux Beagle API blocks only containerized live capture; the Windows
host shim (`scripts/capture_beagle_usb12.py --api-dir <windows api dir>`) emits
the same JSONL evidence for container analysis.

## Examples

Radare2:

```powershell
.\tools\re\run-re-container.ps1 r2 -A /work/input/kvm2usb3.img
```

angr script:

```powershell
.\tools\re\run-re-container.ps1 angr /work/scripts/analyze_fx3.py /work/input/kvm2usb3.img
```

Ghidra headless import:

```powershell
.\tools\re\run-re-container.ps1 ghidra `
  /home/ghidra/projects issue14 `
  -import /home/ghidra/input/kvm2usb3.img
```

Binwalk extraction:

```powershell
.\tools\re\run-re-container.ps1 binwalk -Me /analysis/input/kvm2usb3.img -C /analysis/output/binwalk
```

TShark USB summary:

```powershell
.\tools\re\run-re-container.ps1 runner `
  'tshark -r /work/input/official-kvmapp.pcapng -Y usb -T json > /work/output/official-usb.json'
```

Beagle capture wrapper:

```powershell
.\tools\re\run-re-container.ps1 beagle `
  python3 /work/scripts/capture_beagle_usb12.py --help
```

Image SBOM and vulnerability scan without exposing the Docker daemon socket to a container:

```powershell
pwsh -File .\tools\re\scan-re-image.ps1 agentkvm2usb/re-runner:1 -ContainerRuntime Auto
```

The PowerShell route uses the same runtime adapter as the rest of the toolchain;
`tools/re/scan-re-image.sh` remains available for direct WSL-native use.

## Lifecycle

Update pulled images and rebuild pinned upstream images by rerunning bootstrap.
The resulting immutable digests are written to `.work/re/.env.re.lock` and the lock manifest; `.work/re/.env.re` remains the ignored, human-editable build configuration copied from `.env.re.example`.

Remove project containers and images while retaining evidence:

```powershell
pwsh -File .\tools\re\uninstall-re-containers.ps1
```

Remove host USB plumbing only when explicitly requested:

```powershell
pwsh -File .\tools\re\uninstall-re-containers.ps1 `
  -RemoveUsbipd `
  -RemoveWindowsCapture
```

Use `-RemoveWorkData` only after evidence and provenance records have been
archived appropriately.
