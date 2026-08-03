[CmdletBinding()]
param(
    [Parameter(Position=0)]
    [ValidateSet('ghidra', 'binwalk', 'all')]
    [string]$Target = 'all',

    # When the bootstrap invokes this script it omits -ContainerRuntime so the
    # already-recorded selection in .work/re/runtime.json is reused and the probe
    # is not re-run (the runtime never switches mid-run). Standalone callers may
    # pass Auto|DockerDesktop|WslEngine to select fresh.
    [ValidateSet('Auto', 'DockerDesktop', 'WslEngine')]
    [string]$ContainerRuntime = $null,
    [string]$WslDistribution = 'Ubuntu',
    [switch]$NoStartDockerDesktop,
    [int]$StartTimeoutSeconds = 120,
    [string]$GhidraVersion = '12.1.2',
    [string]$BinwalkVersion = '3.1.0'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'runtime.psm1') -Force

$repoRoot = Get-ReRepoRoot
if ($ContainerRuntime) {
    $selection = Select-ReRuntime `
        -ContainerRuntime $ContainerRuntime `
        -WslDistribution $WslDistribution `
        -NoStartDockerDesktop:$NoStartDockerDesktop `
        -StartTimeoutSeconds $StartTimeoutSeconds
}
else {
    $selection = Get-ReSelection
}
$runtime = $selection.selected_runtime
Write-Host "Building upstream images with runtime: $runtime"

$upstream = Join-Path $repoRoot '.work\re\upstream'
New-Item -ItemType Directory -Force -Path $upstream | Out-Null

function Invoke-ReRequired {
    param([Parameter(Mandatory)][scriptblock]$Action, [Parameter(Mandatory)][string]$What)
    & $Action
    if ($LASTEXITCODE -ne 0) { throw "$What failed with exit code $LASTEXITCODE" }
}

function Get-ReReleaseDir {
    param([string]$ExtractRoot)
    $dir = Get-ChildItem -LiteralPath $ExtractRoot -Directory -Filter 'ghidra_*' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $dir) { throw "Extracted Ghidra release directory not found under $ExtractRoot" }
    return $dir.FullName
}

function Build-ReGhidra {
    $tag = "Ghidra_${GhidraVersion}_build"
    $metadataPath = Join-Path $upstream "ghidra-${GhidraVersion}-release.json"
    Write-Host "==> Resolving Ghidra release $tag from the NSA release metadata"

    if (-not (Test-Path -LiteralPath $metadataPath)) {
        $headers = @{ 'Accept' = 'application/vnd.github+json'; 'User-Agent' = 'AgentKVM2USB-bootstrap' }
        $release = Invoke-RestMethod -Uri "https://api.github.com/repos/NationalSecurityAgency/ghidra/releases/tags/$tag" -Headers $headers
        $asset = @($release.assets | Where-Object { $_.name -match '^ghidra_.*_PUBLIC_.*\.zip$' })
        if ($asset.Count -ne 1) { throw "Expected one Ghidra release ZIP asset, found $($asset.Count)" }
        $body = [string]$release.body
        $match = [regex]::Match($body, 'SHA-256:\s*`?([0-9a-fA-F]{64})')
        if (-not $match.Success) { throw "Ghidra release body did not contain an SHA-256 value" }
        $metadata = [ordered]@{
            tag = $tag
            asset_name = $asset[0].name
            asset_url = $asset[0].browser_download_url
            sha256 = $match.Groups[1].Value.ToLowerInvariant()
            release_url = $release.html_url
        }
        $metadata | ConvertTo-Json | Set-Content -LiteralPath $metadataPath -Encoding UTF8
    }
    $metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
    $zipPath = Join-Path $upstream $metadata.asset_name

    if (-not (Test-Path -LiteralPath $zipPath) -or (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $metadata.sha256) {
        Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
        Write-Host "==> Downloading $($metadata.asset_url)"
        & curl.exe --fail --location --retry 3 --output $zipPath $metadata.asset_url
        if ($LASTEXITCODE -ne 0) { throw "curl download of Ghidra asset failed with exit code $LASTEXITCODE" }
    }
    $actual = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $metadata.sha256) {
        throw "Ghidra SHA-256 mismatch: expected $($metadata.sha256), got $actual"
    }
    Write-Host "==> Ghidra SHA-256 verified: $actual"

    $extractRoot = Join-Path $upstream "ghidra-${GhidraVersion}"
    if (-not (Test-Path -LiteralPath $extractRoot)) {
        New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null
        Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force
    }
    $releaseDir = Get-ReReleaseDir -ExtractRoot $extractRoot
    $appProps = Join-Path $releaseDir 'Ghidra\application.properties'
    $version = $GhidraVersion
    $release = ''
    if (Test-Path -LiteralPath $appProps) {
        foreach ($line in (Get-Content -LiteralPath $appProps)) {
            if ($line -match '^application\.version=(.+)$') { $version = $Matches[1].Trim().Trim("`r") }
            elseif ($line -match '^application\.release\.name=(.+)$') { $release = $Matches[1].Trim().Trim("`r") }
        }
    }
    if (-not $release) { $release = $version }

    # Build the unmodified upstream Dockerfile from the verified release.
    $relativeRelease = $releaseDir.Substring($repoRoot.Length).TrimStart([char[]]@('\', '/')).Replace('\', '/')
    $dockerfile = if (Test-Path -LiteralPath (Join-Path $releaseDir 'docker\Dockerfile')) { "$relativeRelease/docker/Dockerfile" } else { "$relativeRelease/Dockerfile" }
    Write-Host "==> docker build $dockerfile (Ghidra $version, $release)"
    Invoke-ReRequired -What 'Ghidra upstream docker build' -Action {
        Invoke-ReDocker -- build --build-arg "GHIDRA_VERSION=$version" --build-arg "GHIDRA_RELEASE=$release" -f $dockerfile -t "ghidra/ghidra:${version}_${release}" $relativeRelease
    }
    Invoke-ReRequired -What 'Ghidra image retag' -Action {
        Invoke-ReDocker -- tag "ghidra/ghidra:${version}_${release}" "agentkvm2usb/ghidra:${GhidraVersion}-upstream"
    }
    Write-Host "==> Ghidra image ready: agentkvm2usb/ghidra:${GhidraVersion}-upstream"
}

function Build-ReBinwalk {
    $source = Join-Path $upstream "binwalk-${BinwalkVersion}"
    if (-not (Test-Path -LiteralPath (Join-Path $source '.git'))) {
        Remove-Item -LiteralPath $source -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "==> Cloning ReFirmLabs/binwalk at v${BinwalkVersion}"
        Invoke-ReRequired -What 'Binwalk git clone' -Action {
            & git.exe clone --depth 1 --branch "v${BinwalkVersion}" 'https://github.com/ReFirmLabs/binwalk.git' $source
        }
    }
    $relativeSource = $source.Substring($repoRoot.Length).TrimStart([char[]]@('\', '/')).Replace('\', '/')
    Write-Host "==> docker build binwalk $BinwalkVersion (context $relativeSource)"
    Invoke-ReRequired -What 'Binwalk upstream docker build' -Action {
        Invoke-ReDocker -- build --pull --tag "agentkvm2usb/binwalk:${BinwalkVersion}-upstream" $relativeSource
    }
    Write-Host "==> Binwalk image ready: agentkvm2usb/binwalk:${BinwalkVersion}-upstream"
}

if ($Target -eq 'ghidra' -or $Target -eq 'all') { Build-ReGhidra }
if ($Target -eq 'binwalk' -or $Target -eq 'all') { Build-ReBinwalk }
