[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$WslDistribution = 'Ubuntu',
    [switch]$RemoveWorkData,
    [switch]$RemoveUsbipd,
    [switch]$RemoveWindowsCapture
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$wslRepo = (& wsl.exe -d $WslDistribution -- wslpath -a $repoRoot).Trim()

function Quote-Bash([string]$Value) {
    $singleQuoteEscape = "'" + [char]34 + "'" + [char]34 + "'"
    return "'" + $Value.Replace("'", $singleQuoteEscape) + "'"
}

if ($wslRepo) {
    $command = "cd $(Quote-Bash $wslRepo) && docker compose --env-file .work/re/.env.re -f compose.re.yml down --remove-orphans --volumes || true; docker image rm agentkvm2usb/re-runner:1 agentkvm2usb/ghidra:12.1.2-upstream agentkvm2usb/binwalk:3.1.0-upstream 2>/dev/null || true"
    if ($PSCmdlet.ShouldProcess('Project Docker resources', 'Remove')) {
        & wsl.exe -d $WslDistribution -- bash -lc $command
    }
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
