[CmdletBinding()]
param(
    [string]$WslDistribution = 'Ubuntu',
    [string]$TotalPhaseDirectory = 'C:\Users\Mark\Downloads\TotalPhase',
    [switch]$InstallUsbipd,
    [switch]$InstallWindowsCapture,
    [switch]$SkipUpstreamBuilds,
    [switch]$RefreshVendorInventory,
    [switch]$AllowCommunityGhidraImage
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$directories = @(
    '.work\re\input', '.work\re\output', '.work\re\projects', '.work\re\cache',
    '.work\re\upstream', '.work\vendor'
)
foreach ($relative in $directories) {
    New-Item -ItemType Directory -Force -Path (Join-Path $repoRoot $relative) | Out-Null
}

function Quote-Bash([string]$Value) {
    $singleQuoteEscape = "'" + [char]34 + "'" + [char]34 + "'"
    return "'" + $Value.Replace("'", $singleQuoteEscape) + "'"
}

function Invoke-WingetInstall {
    param([Parameter(Mandatory)][string]$Id)
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw 'winget.exe is required for optional host package installation.'
    }
    & winget.exe install --id $Id --exact --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "winget install failed for $Id with exit code $LASTEXITCODE" }
}

function Test-WslDocker {
    & wsl.exe -d $WslDistribution -- bash -lc 'docker version >/dev/null 2>&1 && docker compose version >/dev/null 2>&1'
    return $LASTEXITCODE -eq 0
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw 'WSL is required. This project intentionally does not install Docker Desktop.'
}
if (-not (Test-WslDocker)) {
    throw "Docker Engine and the Compose plugin were not found in WSL distribution '$WslDistribution'. Use the existing WSL Docker setup before continuing."
}

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
    $usbPcap = Get-ChildItem 'C:\Program Files','C:\Program Files (x86)' -Filter USBPcapCMD.exe -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $usbPcap) {
        Write-Warning 'Wireshark was installed, but USBPcapCMD.exe was not found. Re-run the Wireshark installer and explicitly select USBPcap.'
    }
}

$wslRepo = (& wsl.exe -d $WslDistribution -- wslpath -a $repoRoot).Trim()
if (-not $wslRepo) { throw 'Unable to convert repository path for WSL.' }
$allowCommunity = if ($AllowCommunityGhidraImage) { '1' } else { '0' }
$skipBuilds = if ($SkipUpstreamBuilds) { '1' } else { '0' }
$command = "cd $(Quote-Bash $wslRepo) && ALLOW_COMMUNITY_GHIDRA=$allowCommunity SKIP_UPSTREAM_BUILDS=$skipBuilds bash tools/re/bootstrap-re-containers.sh"
& wsl.exe -d $WslDistribution -- bash -lc $command
if ($LASTEXITCODE -ne 0) { throw "Container bootstrap failed with exit code $LASTEXITCODE" }

Write-Host ''
Write-Host 'Container-first reverse-engineering environment is ready.'
Write-Host "Verify: pwsh -File .\tools\re\verify-re-containers.ps1 -WslDistribution $WslDistribution"
Write-Host 'No host reverse-engineering suites were installed.'
