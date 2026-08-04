[CmdletBinding()]
param(
    [ValidateSet('Auto', 'DockerDesktop', 'WslEngine')]
    [string]$ContainerRuntime = 'Auto',
    [string]$WslDistribution = 'Ubuntu',
    [string]$TotalPhaseDirectory = 'C:\Users\Mark\Downloads\TotalPhase',
    [switch]$InstallUsbipd,
    [switch]$InstallWindowsCapture,
    [switch]$SkipUpstreamBuilds,
    [switch]$RefreshVendorInventory,
    [switch]$AllowCommunityGhidraImage,
    [switch]$NoStartDockerDesktop,
    [int]$StartTimeoutSeconds = 120,
    [string]$GhidraVersion = '12.1.2',
    [string]$BinwalkVersion = '3.1.0'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'runtime.psm1') -Force

$repoRoot = Get-ReRepoRoot
$directories = @(
    '.work\re\input', '.work\re\output', '.work\re\projects', '.work\re\cache',
    '.work\re\upstream', '.work\vendor'
)
foreach ($relative in $directories) {
    New-Item -ItemType Directory -Force -Path (Join-Path $repoRoot $relative) | Out-Null
}

function Invoke-WingetInstall {
    param([Parameter(Mandatory)][string]$Id)
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw 'winget.exe is required for optional host package installation.'
    }
    & winget.exe install --id $Id --exact --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "winget install failed for $Id with exit code $LASTEXITCODE" }
}

# Probe and select the Docker runtime. Explicit selection wins and fails clearly
# when that candidate is unavailable; Auto applies the issue #14 rules. The
# selection is recorded in .work/re/runtime.json and every operation below uses
# the same adapter, so the runtime never switches mid-run.
$selection = Select-ReRuntime `
    -ContainerRuntime $ContainerRuntime `
    -WslDistribution $WslDistribution `
    -NoStartDockerDesktop:$NoStartDockerDesktop `
    -StartTimeoutSeconds $StartTimeoutSeconds
$runtime = $selection.selected_runtime
Write-Host "Selected runtime: $runtime ($($selection.selection_reason))"
if ($runtime -eq 'DockerDesktop') {
    Write-Host "Pinned Desktop context: $($selection.metadata.context) -> $($selection.metadata.endpoint)"
}

# Fail closed unless the recorded runtime still resolves as selected before any
# significant Docker operation (pulls, builds, locks, scans, cleanup).
$verifyRc = Invoke-ReVerifyContext
if ($verifyRc -ne 0) { throw "Recorded runtime context verification failed (exit $verifyRc)." }

$inventoryScript = Join-Path $PSScriptRoot 'inventory-totalphase.ps1'
$inventoryPath = Join-Path $repoRoot '.work\vendor\totalphase\inventory.json'
if ($RefreshVendorInventory -or -not (Test-Path -LiteralPath $inventoryPath)) {
    & $inventoryScript -SourceDirectory $TotalPhaseDirectory -DestinationDirectory (Join-Path $repoRoot '.work\vendor\totalphase') -Force:$RefreshVendorInventory
}

if ($InstallUsbipd) {
    Invoke-WingetInstall -Id 'dorssel.usbipd-win'
}
if ($InstallWindowsCapture) {
    Invoke-WingetInstall -Id 'WiresharkFoundation.Wireshark'
    $usbPcap = Get-ChildItem 'C:\Program Files', 'C:\Program Files (x86)' -Filter USBPcapCMD.exe -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $usbPcap) {
        Write-Warning 'Wireshark was installed, but USBPcapCMD.exe was not found. Re-run the Wireshark installer and explicitly select USBPcap.'
    }
}

# Human-editable build configuration copied from the packaged default seed.
$envFile = '.work/re/.env.re'
$envPath = Join-Path $repoRoot $envFile
if (-not (Test-Path -LiteralPath $envPath)) {
    Copy-Item -LiteralPath (Join-Path $repoRoot '.env.re.example') -Destination $envPath
}

if ($runtime -eq 'WslEngine') {
    # WSL Engine mode: the WSL-native bash pipeline owns the work. The adapter
    # runs it inside the selected distribution from the validated WSL path.
    $bashEnv = @{
        ALLOW_COMMUNITY_GHIDRA = $(if ($AllowCommunityGhidraImage) { '1' } else { '0' })
        SKIP_UPSTREAM_BUILDS = $(if ($SkipUpstreamBuilds) { '1' } else { '0' })
        GHIDRA_VERSION = $GhidraVersion
        BINWALK_VERSION = $BinwalkVersion
    }
    Invoke-ReBashScript -Script 'tools/re/bootstrap-re-containers.sh' -Environment $bashEnv
    if ($LASTEXITCODE -ne 0) { throw "Container bootstrap failed with exit code $LASTEXITCODE" }
}
else {
    # Docker Desktop mode: drive the pipeline natively through the Windows Docker
    # CLI from the Windows repository path. No Ubuntu, no WSL path conversion.
    if (-not $SkipUpstreamBuilds) {
        # build-upstream-images.ps1 reuses the selection already recorded in
        # .work/re/runtime.json (no -ContainerRuntime), so the probe is not
        # re-run and the runtime never switches mid-run. It propagates
        # terminating errors on failure; $LASTEXITCODE is not set by a script
        # invocation, so do not read it here.
        & (Join-Path $PSScriptRoot 'build-upstream-images.ps1') `
            -Target 'all' `
            -GhidraVersion $GhidraVersion `
            -BinwalkVersion $BinwalkVersion
    }
    elseif ($AllowCommunityGhidraImage) {
        Invoke-ReDocker -- pull "blacktop/ghidra:${GhidraVersion}"
        if ($LASTEXITCODE -ne 0) { throw 'Community Ghidra image pull failed.' }
    }

    # Versioned publisher tags only; the unused angr/angr image is not pulled.
    $pullImages = @(
        'radare/radare2:6.1.8',
        'anchore/syft:v1.19.0',
        'aquasec/trivy:0.57.1'
    )
    foreach ($image in $pullImages) {
        Invoke-ReDocker -- pull $image
        if ($LASTEXITCODE -ne 0) { throw "docker pull $image failed with exit code $LASTEXITCODE" }
    }

    # Prime the Trivy database while networking is allowed; runtime scans use it
    # with networking disabled. Build the mount spec in a variable first: the
    # inline embedded-quote form mangles commas inside --mount args.
    New-Item -ItemType Directory -Force -Path (Join-Path $repoRoot '.work\re\cache\trivy') | Out-Null
    $trivyMount = "type=bind,src=$(Join-Path $repoRoot '.work\re\cache\trivy'),dst=/root/.cache/trivy"
    Invoke-ReDocker -- run --rm --mount $trivyMount aquasec/trivy:0.57.1 image --download-db-only
    if ($LASTEXITCODE -ne 0) {
        Write-Warning 'Trivy database prefetch failed; offline vulnerability scans will be unavailable until it succeeds.'
    }

    # Resolve the official Python base to an immutable digest and record it as a
    # build input before building the runner.
    $py = Get-RePythonExe
    $baseLock = Join-Path $repoRoot '.work\re\base-image.lock.json'
    $baseDigest = & $py 'tools/re/resolve_base_image.py' `
        --image 'python:3.12-slim-bookworm' `
        --output $baseLock `
        --repo-root $repoRoot
    if ($LASTEXITCODE -ne 0) { throw "Base image resolution failed with exit code $LASTEXITCODE" }
    $baseDigest = ($baseDigest | Select-Object -Last 1).Trim()
    Write-Host "Locked Python base: $baseDigest"
    # Record the locked base in the human-editable build config so compose passes
    # it as PYTHON_BASE_IMAGE to the runner build.
    $envText = Get-Content -LiteralPath $envPath
    $updated = @()
    $set = $false
    foreach ($line in $envText) {
        if ($line -match '^PYTHON_BASE_IMAGE=') {
            $updated += "PYTHON_BASE_IMAGE=$baseDigest"
            $set = $true
        }
        else { $updated += $line }
    }
    if (-not $set) { $updated += "PYTHON_BASE_IMAGE=$baseDigest" }
    Set-Content -LiteralPath $envPath -Value $updated -Encoding UTF8

    Invoke-ReCompose -- --env-file $envFile -f compose.re.yml build runner
    if ($LASTEXITCODE -ne 0) { throw "runner image build failed with exit code $LASTEXITCODE" }

    & $py 'tools/re/write_image_lock.py' `
        --env-file (Join-Path $repoRoot $envFile) `
        --locked-env (Join-Path $repoRoot '.work\re\.env.re.lock') `
        --output (Join-Path $repoRoot '.work\re\images.lock.json') `
        --repo-root $repoRoot
    if ($LASTEXITCODE -ne 0) { throw "Image lock failed with exit code $LASTEXITCODE" }

    Invoke-ReCompose -- --env-file $envFile -f compose.re.yml config | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Compose validation failed with exit code $LASTEXITCODE" }
}

Write-Host ''
Write-Host 'Container-first reverse-engineering environment is ready.'
Write-Host "Selected runtime: $runtime"
Write-Host "Verify: pwsh -File .\tools\re\verify-re-containers.ps1 -ContainerRuntime $runtime"
Write-Host 'No host reverse-engineering suites were installed.'
