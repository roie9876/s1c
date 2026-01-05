@echo off
setlocal enableextensions

REM AVD RemoteApp bootstrapper (CMD wrapper)
REM Runs LauncherRunner.ps1 in a non-interactive, predictable way.
REM
REM Recommended RemoteApp target:
REM   Path:      C:\Windows\System32\cmd.exe
REM   Arguments: /c C:\S1C\LauncherRunner.cmd
REM
REM Optional override:
REM   /c C:\S1C\LauncherRunner.cmd -OverrideUser user@domain.com

set "SCRIPT_DIR=%~dp0"
set "RUNNER_PS1=%SCRIPT_DIR%LauncherRunner.ps1"

if not exist "%RUNNER_PS1%" (
  echo [ERROR] Missing: "%RUNNER_PS1%"
  exit /b 1
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%RUNNER_PS1%" %*
exit /b %ERRORLEVEL%
