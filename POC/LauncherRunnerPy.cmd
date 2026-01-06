@echo off
setlocal enableextensions

REM DEPRECATED for the current PoC.
REM Use PowerShell RemoteApp to run:
REM   powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\S1C\Launcher.ps1

REM PowerShell-free runner: uses Python to call the broker API and launch SmartConsole.
REM
REM Recommended RemoteApp target:
REM   Path:      C:\Windows\System32\cmd.exe
REM   Arguments: /c C:\S1C\LauncherRunnerPy.cmd

set "SCRIPT_DIR=%~dp0"
set "LAUNCHER_PY=%SCRIPT_DIR%LauncherPy.py"

if not exist "%LAUNCHER_PY%" (
  echo [ERROR] Missing: "%LAUNCHER_PY%"
  exit /b 1
)

REM Prefer the Python launcher if installed (py.exe). Fallback to python.exe.
where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3.13 "%LAUNCHER_PY%" %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python "%LAUNCHER_PY%" %*
  exit /b %ERRORLEVEL%
)

echo [ERROR] Python not found. Install Python 3.13+ and ensure "py" or "python" is in PATH.
exit /b 1
