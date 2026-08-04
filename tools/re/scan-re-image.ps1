[CmdletBinding()]
param(
    [Parameter(Mandatory, Position=0)]
    [string]$Image,

    [string]$Base = '',

    [ValidateSet('Auto', 'DockerDesktop', 'WslEngine')]
    [string]$ContainerRuntime = 'Auto',
    [string]$WslDistribution = 'Ubuntu',
    [switch]$NoStartDockerDesktop,
    [int]$StartTimeoutSeconds = 120
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'runtime.psm1') -Force

$repoRoot = Get-ReRepoRoot
$selection = Select-ReRuntime `
    -ContainerRuntime $ContainerRuntime `
    -WslDistribution $WslDistribution `
    -NoStartDockerDesktop:$NoStartDockerDesktop `
    -StartTimeoutSeconds $StartTimeoutSeconds
$runtime = $selection.selected_runtime
Write-Host "Scanning with runtime: $runtime"
$verifyRc = Invoke-ReVerifyContext
if ($verifyRc -ne 0) { throw "Recorded runtime context verification failed (exit $verifyRc)." }

$envFile = if (Test-Path (Join-Path $repoRoot '.work\re\.env.re.lock')) { '.work/re/.env.re.lock' } else { '.work/re/.env.re' }
if (-not $Base) { $Base = $Image -replace '[/:@]', '_' }
New-Item -ItemType Directory -Force -Path (Join-Path $repoRoot '.work\re\input'), (Join-Path $repoRoot '.work\re\output'), (Join-Path $repoRoot '.work\re\cache\trivy'), (Join-Path $repoRoot '.work\re\cache\scan-tmp'), (Join-Path $repoRoot '.work\re\cache\syft') | Out-Null

$archive = ".work/re/input/$Base.docker.tar"
try {
    Invoke-ReDocker -- image inspect $Image
    if ($LASTEXITCODE -ne 0) { throw "Image not found: $Image" }

    Invoke-ReDocker -- save --output $archive $Image
    if ($LASTEXITCODE -ne 0) { throw "docker save failed for $Image (exit $LASTEXITCODE)" }

    Invoke-ReCompose -- --env-file $envFile -f compose.re.yml run --rm syft "docker-archive:/input/$Base.docker.tar" -o "cyclonedx-json=/output/$Base.sbom.cdx.json" -o "spdx-json=/output/$Base.sbom.spdx.json"
    if ($LASTEXITCODE -ne 0) { throw "Syft SBOM scan failed (exit $LASTEXITCODE)" }

    Invoke-ReCompose -- --env-file $envFile -f compose.re.yml run --rm trivy image --input "/input/$Base.docker.tar" --skip-db-update --format json --output "/output/$Base.trivy.json"
    if ($LASTEXITCODE -ne 0) { throw "Trivy vulnerability scan failed (exit $LASTEXITCODE)" }
}
finally {
    Remove-Item -LiteralPath (Join-Path $repoRoot $archive) -Force -ErrorAction SilentlyContinue
}

Write-Host "SBOM and vulnerability reports written under $repoRoot\.work\re\output"
