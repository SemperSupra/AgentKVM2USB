[CmdletBinding()]
param(
    [Parameter(Mandatory, Position=0)]
    [ValidateSet('runner', 'r2', 'angr', 'ghidra', 'binwalk', 'syft', 'trivy', 'beagle')]
    [string]$Tool,

    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$ToolArguments,

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
$verifyRc = Invoke-ReVerifyContext
if ($verifyRc -ne 0) { throw "Recorded runtime context verification failed (exit $verifyRc)." }

$envFile = if (Test-Path (Join-Path $repoRoot '.work\re\.env.re.lock')) { '.work/re/.env.re.lock' } else { '.work/re/.env.re' }
if (-not (Test-Path (Join-Path $repoRoot '.work\re\.env.re'))) {
    throw 'Bootstrap has not created .work/re/.env.re. Run bootstrap-re-containers.cmd first.'
}

if ($Tool -eq 'beagle') {
    $routeJson = & (Get-RePythonExe) 'tools/re/re_runtime.py' 'beagle-route' --runtime-json (Get-ReRuntimeJsonPath) --repo-root $repoRoot
    $route = (($routeJson -join '') | ConvertFrom-Json)
    if ($route.route -eq 'container') {
        Invoke-ReBashScript -Script 'tools/re/run-beagle-container.sh' -ScriptArgs @($ToolArguments)
        if ($LASTEXITCODE -ne 0) { throw "Beagle container exited with code $LASTEXITCODE" }
    }
    elseif ($route.route -eq 'windows_host') {
        Write-Host "Beagle capture route: Windows host shim ($runtime runtime, no Linux Beagle API in container)"
        # Normalize container-style invocation to the host script arguments.
        $hostArgs = @($ToolArguments)
        if ($hostArgs.Count -ge 2 -and $hostArgs[0] -eq 'python3' -and $hostArgs[1] -like '*capture_beagle_usb12.py') {
            $hostArgs = @($hostArgs[2..($hostArgs.Count - 1)])
        }
        if ($hostArgs.Count -eq 0) { $hostArgs = @('--help') }
        & (Get-RePythonExe) 'scripts/capture_beagle_usb12.py' '--api-dir' $route.windows_api_dir @hostArgs
        if ($LASTEXITCODE -ne 0) { throw "Beagle host capture exited with code $LASTEXITCODE" }
    }
    else {
        throw 'No Beagle API was staged under .work\vendor\totalphase. Refresh the vendor inventory first.'
    }
    exit 0
}

$service = switch ($Tool) {
    'r2' { 'radare2' }
    default { $Tool }
}
Invoke-ReCompose -- --env-file $envFile -f compose.re.yml run --rm $service @ToolArguments
if ($LASTEXITCODE -ne 0) { throw "$Tool container exited with code $LASTEXITCODE" }
