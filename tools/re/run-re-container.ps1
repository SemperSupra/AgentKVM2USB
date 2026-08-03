[CmdletBinding()]
param(
    [Parameter(Mandatory, Position=0)]
    [ValidateSet('runner','r2','angr','ghidra','binwalk','syft','trivy','beagle')]
    [string]$Tool,

    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$ToolArguments,

    [string]$WslDistribution = 'Ubuntu'
)

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

if ($Tool -eq 'beagle') {
    $argsText = ($ToolArguments | ForEach-Object { Quote-Bash $_ }) -join ' '
    $command = "cd $(Quote-Bash $wslRepo) && bash tools/re/run-beagle-container.sh $argsText"
} else {
    $service = switch ($Tool) {
        'r2' { 'radare2' }
        default { $Tool }
    }
    $argsText = ($ToolArguments | ForEach-Object { Quote-Bash $_ }) -join ' '
    $command = "cd $(Quote-Bash $wslRepo) && docker compose --env-file $envFile -f compose.re.yml run --rm $service $argsText"
}

& wsl.exe -d $WslDistribution -- bash -lc $command
if ($LASTEXITCODE -ne 0) { throw "$Tool container exited with code $LASTEXITCODE" }
