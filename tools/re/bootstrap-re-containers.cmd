@echo off
setlocal
set SCRIPT=%~dp0bootstrap-re-containers.ps1
where pwsh.exe >nul 2>nul
if %ERRORLEVEL%==0 (
  pwsh.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
) else (
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
)
exit /b %ERRORLEVEL%
