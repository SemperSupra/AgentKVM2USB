[CmdletBinding()]
param([string]$WslDistribution = 'Ubuntu')

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$envFile = if (Test-Path (Join-Path $repoRoot '.work\re\.env.re.lock')) { '.work/re/.env.re.lock' } else { '.work/re/.env.re' }
$wslRepo = (& wsl.exe -d $WslDistribution -- wslpath -a $repoRoot).Trim()
if (-not $wslRepo) { throw 'Unable to convert repository path for WSL.' }

function Quote-Bash([string]$Value) {
    $singleQuoteEscape = "'" + [char]34 + "'" + [char]34 + "'"
    return "'" + $Value.Replace("'", $singleQuoteEscape) + "'"
}

$runnerCheck = Quote-Bash 'python3 --version && tshark --version | head -n 1 && arm-none-eabi-objdump --version | head -n 1'
$angrCheck = Quote-Bash 'import angr; print(angr.__version__)'
$checks = @(
    'docker version --format "Docker Engine {{.Server.Version}}"',
    'docker compose version',
    "docker compose --env-file $envFile -f compose.re.yml config >/dev/null",
    "docker compose --env-file $envFile -f compose.re.yml run --rm runner $runnerCheck",
    "docker compose --env-file $envFile -f compose.re.yml run --rm radare2 -v",
    "docker compose --env-file $envFile -f compose.re.yml run --rm angr -c $angrCheck",
    "docker compose --env-file $envFile -f compose.re.yml run --rm ghidra",
    "docker compose --env-file $envFile -f compose.re.yml run --rm binwalk --help >/dev/null"
)

foreach ($check in $checks) {
    Write-Host "==> $check"
    $command = "cd $(Quote-Bash $wslRepo) && $check"
    & wsl.exe -d $WslDistribution -- bash -lc $command
    if ($LASTEXITCODE -ne 0) { throw "Verification failed: $check" }
}

$inventory = Join-Path $repoRoot '.work\vendor\totalphase\inventory.json'
if (-not (Test-Path -LiteralPath $inventory)) {
    throw 'Total Phase inventory is missing. Run bootstrap with -RefreshVendorInventory.'
}
$data = Get-Content -LiteralPath $inventory -Raw | ConvertFrom-Json
if (@($data.linux_beagle_api_candidates).Count -eq 0) {
    Write-Warning 'No Linux Beagle API candidate was detected in the staged Total Phase downloads.'
} else {
    Write-Host "Total Phase Linux API candidates: $(@($data.linux_beagle_api_candidates).Count)"
}

Write-Host 'Container toolchain verification passed.'
