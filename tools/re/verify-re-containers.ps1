[CmdletBinding()]
param(
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
Write-Host "Verifying with runtime: $runtime ($($selection.selection_reason))"
$verifyRc = Invoke-ReVerifyContext
if ($verifyRc -ne 0) { throw "Recorded runtime context verification failed (exit $verifyRc)." }

$envFile = if (Test-Path (Join-Path $repoRoot '.work\re\.env.re.lock')) { '.work/re/.env.re.lock' } else { '.work/re/.env.re' }
if (-not (Test-Path (Join-Path $repoRoot '.work\re\.env.re'))) {
    throw 'Bootstrap has not created .work/re/.env.re. Run bootstrap-re-containers.cmd first.'
}

function Invoke-ReCheck {
    param(
        [Parameter(Mandatory)][string]$Label,
        [scriptblock]$Action
    )
    Write-Host "==> $Label"
    & $Action
    if ($LASTEXITCODE -ne 0) { throw "Verification failed: $Label (exit $LASTEXITCODE)" }
}

Invoke-ReCheck -Label 'docker server version' -Action {
    Invoke-ReDocker -- version --format 'Docker Engine {{.Server.Version}}'
}
Invoke-ReCheck -Label 'docker compose version' -Action {
    Invoke-ReCompose -- version
}
Invoke-ReCheck -Label 'compose model validation' -Action {
    Invoke-ReCompose -- --env-file $envFile -f compose.re.yml config | Out-Null
}
Invoke-ReCheck -Label 'runner toolchain' -Action {
    Invoke-ReCompose -- --env-file $envFile -f compose.re.yml run --rm runner 'python3 --version && tshark --version | head -n 1'
}
Invoke-ReCheck -Label 'radare2' -Action {
    Invoke-ReCompose -- --env-file $envFile -f compose.re.yml run --rm radare2 -v
}
Invoke-ReCheck -Label 'angr' -Action {
    Invoke-ReCompose -- --env-file $envFile -f compose.re.yml run --rm angr -c 'import angr; print(angr.__version__)'
}
Invoke-ReCheck -Label 'ghidra headless import' -Action {
    # analyzeHeadless always requires an action; a real minimal import exercises
    # the full JVM + project + loader pipeline and exits 0.
    $smokeFile = Join-Path $repoRoot '.work\re\input\ghidra-smoke.bin'
    [System.IO.File]::WriteAllBytes($smokeFile, [byte[]](0xDE, 0xAD, 0xBE, 0xEF, 0x00, 0x01, 0x02, 0x03))
    Invoke-ReCompose -- --env-file $envFile -f compose.re.yml run --rm ghidra /home/ghidra/projects smoke -import /home/ghidra/input/ghidra-smoke.bin | Out-Null
}
Invoke-ReCheck -Label 'binwalk' -Action {
    Invoke-ReCompose -- --env-file $envFile -f compose.re.yml run --rm binwalk --help | Out-Null
}

# Total Phase inventory: the missing Linux Beagle API must not block general
# toolchain validation. Report which capture route is available.
$inventory = Join-Path $repoRoot '.work\vendor\totalphase\inventory.json'
if (-not (Test-Path -LiteralPath $inventory)) {
    throw 'Total Phase inventory is missing. Run bootstrap with -RefreshVendorInventory.'
}
$data = Get-Content -LiteralPath $inventory -Raw | ConvertFrom-Json
$linuxApi = @($data.linux_beagle_api_candidates).Count
$windowsApi = @($data.windows_beagle_api_candidates).Count
Write-Host "Total Phase Linux Beagle API candidates: $linuxApi"
Write-Host "Total Phase Windows Beagle API candidates: $windowsApi"
if ($linuxApi -eq 0 -and $windowsApi -eq 0) {
    Write-Warning 'No Beagle API was staged. Beagle capture will be unavailable; general tooling is unaffected.'
}
elseif ($linuxApi -eq 0) {
    Write-Host 'Linux Beagle API is absent; containerized live Beagle capture is unavailable. The Windows host shim remains available for capture, with decoding and analysis in containers.'
}

Write-Host 'Container toolchain verification passed.'
