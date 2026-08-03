# Shared Docker runtime selection and adapter for the RE toolchain.
#
# This module is the PowerShell front end to tools/re/re_runtime.py, the single
# source of truth for probing, selecting, and invoking the Docker runtime.
# Every toolchain entrypoint imports this module and uses the same adapter so a
# runtime selected at bootstrap is never silently switched mid-run.
#
#   Import-Module (Join-Path $PSScriptRoot 'runtime.psm1') -Force
#   $selection = Select-ReRuntime -ContainerRuntime Auto -WslDistribution Ubuntu
#   Invoke-ReDocker -- --version
#   Invoke-ReCompose -- --env-file .work/re/.env.re.lock -f compose.re.yml config
#   Invoke-ReBashScript -Script tools/re/scan-re-image.sh -ScriptArgs 'image'
#   ConvertTo-ReWslPath -Path 'C:\Users\Mark\Projects\...'

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-ReRepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}

function Get-RePythonExe {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw 'python is required on PATH to use the RE runtime adapter.'
    }
    return $cmd.Source
}

function Get-ReRuntimeJsonPath {
    return Join-Path (Get-ReRepoRoot) '.work\re\runtime.json'
}

function Select-ReRuntime {
    <#
    Probe both runtime candidates and record the selection in
    .work/re/runtime.json. Explicit selection wins and fails clearly when that
    candidate is unavailable; Auto applies the issue #14 rules. A Docker Desktop
    that is installed but stopped may be started with bounded polling unless
    -NoStartDockerDesktop is passed. No runtime is ever installed.
    #>
    [CmdletBinding()]
    param(
        [ValidateSet('Auto', 'DockerDesktop', 'WslEngine')]
        [string]$ContainerRuntime = 'Auto',
        [string]$WslDistribution = 'Ubuntu',
        [switch]$NoStartDockerDesktop,
        [int]$StartTimeoutSeconds = 120
    )

    $repoRoot = Get-ReRepoRoot
    $py = Get-RePythonExe
    $runtimeJson = Get-ReRuntimeJsonPath

    $pyArgs = @(
        'tools/re/re_runtime.py', 'probe',
        '--requested', $ContainerRuntime,
        '--wsl-distribution', $WslDistribution,
        '--repo-root', $repoRoot,
        '--runtime-json', $runtimeJson,
        '--start-timeout-s', "$StartTimeoutSeconds"
    )
    if ($NoStartDockerDesktop) {
        $pyArgs += '--no-start-docker-desktop'
    }

    $probeOutput = & $py @pyArgs
    $exit = $LASTEXITCODE
    foreach ($line in $probeOutput) { Write-Host $line }
    if ($exit -ne 0) {
        throw "Runtime selection failed for -ContainerRuntime $ContainerRuntime (exit $exit). " +
            "See $runtimeJson for per-candidate diagnostics."
    }
    return Get-Content -LiteralPath $runtimeJson -Raw | ConvertFrom-Json
}

function Get-ReSelection {
    <# Read the previously selected runtime without re-probing. #>
    $runtimeJson = Get-ReRuntimeJsonPath
    if (-not (Test-Path -LiteralPath $runtimeJson)) {
        throw "runtime.json was not found at $runtimeJson. Run Select-ReRuntime first."
    }
    return Get-Content -LiteralPath $runtimeJson -Raw | ConvertFrom-Json
}

function Invoke-RePythonRunner {
    <#
    Run the re_runtime.py CLI. The child's stdout/stderr stream through and the
    process exit code is left in $LASTEXITCODE for the caller to inspect
    immediately after the call.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Command,
        [string[]]$CommandArgs
    )
    $repoRoot = Get-ReRepoRoot
    $py = Get-RePythonExe
    $runtimeJson = Get-ReRuntimeJsonPath
    $pyArgs = @('tools/re/re_runtime.py', $Command, '--runtime-json', $runtimeJson, '--repo-root', $repoRoot)
    if (@($CommandArgs).Count -gt 0) {
        $pyArgs += '--'
        $pyArgs += @($CommandArgs)
    }
    & $py @pyArgs
}

function Invoke-ReDocker {
    <#
    Run `docker <args>` through the selected adapter. Arguments after the
    function name are forwarded verbatim; use the same syntax you would pass to
    docker itself (e.g. Invoke-ReDocker image inspect agentkvm2usb/re-runner:1).
    #>
    param([Parameter(ValueFromRemainingArguments)][string[]]$DockerArgs)
    return Invoke-RePythonRunner -Command 'docker' -CommandArgs @($DockerArgs)
}

function Invoke-ReCompose {
    <#
    Run `docker compose <args>` through the selected adapter.
    #>
    param([Parameter(ValueFromRemainingArguments)][string[]]$ComposeArgs)
    return Invoke-RePythonRunner -Command 'compose' -CommandArgs @($ComposeArgs)
}

function Invoke-ReBashScript {
    <#
    Run a repository bash script through the WSL Engine adapter. Desktop mode
    drives the toolchain natively through PowerShell and raises instead.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Script,
        [string[]]$ScriptArgs = @(),
        [hashtable]$Environment = @{}
    )
    $repoRoot = Get-ReRepoRoot
    $py = Get-RePythonExe
    $runtimeJson = Get-ReRuntimeJsonPath
    $pyArgs = @('tools/re/re_runtime.py', 'bash', '--runtime-json', $runtimeJson, '--repo-root', $repoRoot, '--script', $Script)
    foreach ($entry in $Environment.GetEnumerator()) {
        $pyArgs += '--env'
        $pyArgs += "$($entry.Key)=$($entry.Value)"
    }
    if (@($ScriptArgs).Count -gt 0) {
        $pyArgs += '--'
        $pyArgs += @($ScriptArgs)
    }
    & $py @pyArgs
    return $LASTEXITCODE
}

function Find-ReLinuxBeagleApi {
    <# Return the staged Linux Beagle API library path, or $null when absent. #>
    $extractRoot = Join-Path (Get-ReRepoRoot) '.work\vendor\totalphase\extracted'
    if (-not (Test-Path -LiteralPath $extractRoot)) { return $null }
    $hit = Get-ChildItem -LiteralPath $extractRoot -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^(beagle\.so|libbeagle\.so)' } |
        Select-Object -First 1
    if ($hit) { return $hit.FullName }
    return $null
}

function Find-ReWindowsBeagleApi {
    <# Return the staged Windows Beagle API directory (contains beagle_py.py), or $null. #>
    $extractRoot = Join-Path (Get-ReRepoRoot) '.work\vendor\totalphase\extracted'
    if (-not (Test-Path -LiteralPath $extractRoot)) { return $null }
    $py = Get-ChildItem -LiteralPath $extractRoot -Filter 'beagle_py.py' -File -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($py) { return $py.Directory.FullName }
    return $null
}

function ConvertTo-ReWslPath {
    <# Convert a Windows path once through wslpath for the selected runtime. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    $repoRoot = Get-ReRepoRoot
    $py = Get-RePythonExe
    $runtimeJson = Get-ReRuntimeJsonPath
    $out = & $py 'tools/re/re_runtime.py' 'wslpath' '--runtime-json' $runtimeJson '--repo-root' $repoRoot '--path' $Path
    return ($out -join '').Trim()
}
