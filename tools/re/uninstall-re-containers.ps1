[CmdletBinding(SupportsShouldProcess)]
param(
    [ValidateSet('Auto', 'DockerDesktop', 'WslEngine')]
    [string]$ContainerRuntime = 'Auto',
    [string]$WslDistribution = 'Ubuntu',
    [switch]$NoStartDockerDesktop,
    [int]$StartTimeoutSeconds = 120,
    [switch]$RemoveWorkData,
    [switch]$RemoveUsbipd,
    [switch]$RemoveWindowsCapture
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
Write-Host "Uninstalling with runtime: $runtime"
$verifyRc = Invoke-ReVerifyContext
if ($verifyRc -ne 0) { throw "Recorded runtime context verification failed (exit $verifyRc)." }

# Best-effort teardown of project containers, networks, volumes, and images
# through the same adapter used by bootstrap/verify/run.
$projectImages = @(
    'agentkvm2usb/re-runner:1',
    'agentkvm2usb/ghidra:12.1.2-upstream',
    'agentkvm2usb/binwalk:3.1.0-upstream'
)
if ($PSCmdlet.ShouldProcess('Project Docker resources', 'Remove')) {
    Invoke-ReCompose -- --env-file .work/re/.env.re -f compose.re.yml down --remove-orphans --volumes
    Invoke-ReDocker -- image rm $projectImages
}

if ($RemoveWorkData -and $PSCmdlet.ShouldProcess((Join-Path $repoRoot '.work\re'), 'Delete')) {
    Remove-Item -LiteralPath (Join-Path $repoRoot '.work\re') -Recurse -Force -ErrorAction SilentlyContinue
}
if ($RemoveUsbipd -and $PSCmdlet.ShouldProcess('dorssel.usbipd-win', 'winget uninstall')) {
    & winget.exe uninstall --id dorssel.usbipd-win --exact --silent
}
if ($RemoveWindowsCapture -and $PSCmdlet.ShouldProcess('WiresharkFoundation.Wireshark', 'winget uninstall')) {
    & winget.exe uninstall --id WiresharkFoundation.Wireshark --exact --silent
}
