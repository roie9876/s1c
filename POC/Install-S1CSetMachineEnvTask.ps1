<#
.SYNOPSIS
  One-time setup: installs a Scheduled Task that runs as SYSTEM and sets a Windows Machine/System environment variable.

.DESCRIPTION
  This is used by Launcher.ps1 when it is not running elevated, so it can still persist APPSTREAM_SESSION_CONTEXT as a System variable.

  Run this script ON THE AVD SESSION HOST as an Administrator.

  It creates:
    - C:\ProgramData\S1C\SetMachineEnvFromFile.ps1
    - Scheduled Task: S1C-SetMachineEnv (Run as SYSTEM, runs every minute)

.NOTES
  If your environment blocks Scheduled Tasks or PowerShell execution, you may need to adapt policy.
#>

[CmdletBinding()]
param(
  [string]$TaskName = "S1C-SetMachineEnv",
  [string]$RequestPath = "$env:ProgramData\S1C\machine-env-request.json",
  [string]$ScriptPath = "$env:ProgramData\S1C\SetMachineEnvFromFile.ps1",
  [string]$LogPath = "$env:ProgramData\S1C\SetMachineEnvFromFile.log"
)

$ErrorActionPreference = 'Stop'

function Assert-Admin {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $p = New-Object Security.Principal.WindowsPrincipal($id)
  if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "This script must be run as Administrator."
  }
}

function Ensure-Dir([string]$Path) {
  $dir = Split-Path -Parent $Path
  if (-not (Test-Path $dir)) {
    New-Item -Path $dir -ItemType Directory -Force | Out-Null
  }
}

Assert-Admin
Ensure-Dir -Path $RequestPath
Ensure-Dir -Path $ScriptPath
Ensure-Dir -Path $LogPath

# Allow non-admin AVD users to write the request file.
try {
  $folder = Split-Path -Parent $RequestPath
  & icacls.exe $folder /grant "Users:(OI)(CI)M" /T /C | Out-Null
} catch {
  Write-Host "[WARN] Failed to set ACLs on request folder: $($_.Exception.Message)" -ForegroundColor Yellow
}

$script = @"
param(
  [string]\$RequestPath = '$RequestPath',
  [string]\$LogPath = '$LogPath'
)
\$ErrorActionPreference = 'Stop'

function Log([string]\$Message) {
  try {
    \$ts = (Get-Date).ToString('s')
    Add-Content -Path \$LogPath -Value ("[\$ts] " + \$Message) -ErrorAction SilentlyContinue
  } catch { }
}

function Broadcast-EnvChange {
  try {
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class NativeMethods {
  [DllImport("user32.dll", SetLastError=true, CharSet=CharSet.Auto)]
  public static extern IntPtr SendMessageTimeout(IntPtr hWnd, int Msg, IntPtr wParam, string lParam, int fuFlags, int uTimeout, out IntPtr lpdwResult);
}
'@ -ErrorAction SilentlyContinue | Out-Null
    \$HWND_BROADCAST = [IntPtr]0xFFFF
    \$WM_SETTINGCHANGE = 0x001A
    \$SMTO_ABORTIFHUNG = 0x0002
    \$result = [IntPtr]::Zero
    [NativeMethods]::SendMessageTimeout(\$HWND_BROADCAST, \$WM_SETTINGCHANGE, [IntPtr]::Zero, "Environment", \$SMTO_ABORTIFHUNG, 2000, [ref]\$result) | Out-Null
  } catch { }
}

if (-not (Test-Path \$RequestPath)) { exit 0 }
\$raw = Get-Content -Path \$RequestPath -Raw -ErrorAction Stop
if (-not \$raw) { exit 0 }
\$obj = \$raw | ConvertFrom-Json
\$name = [string]\$obj.name
\$value = [string]\$obj.value
if ([string]::IsNullOrWhiteSpace(\$name)) { exit 0 }
if ([string]::IsNullOrWhiteSpace(\$value)) { exit 0 }

[Environment]::SetEnvironmentVariable(\$name, \$value, 'Machine')
Broadcast-EnvChange
Log ("Set Machine env var '" + \$name + "' to '" + \$value + "'.")
"@

Set-Content -Path $ScriptPath -Value $script -Encoding UTF8 -Force

# Create/replace the scheduled task
$action = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""

# schtasks needs a valid start time; pick the next minute.
$start = (Get-Date).AddMinutes(1)
$st = $start.ToString('HH:mm')

# Delete if exists (ignore failures)
$prevErrPref = $ErrorActionPreference
try {
  $ErrorActionPreference = 'SilentlyContinue'
  & schtasks.exe /Delete /TN $TaskName /F 2>$null | Out-Null
} finally {
  $ErrorActionPreference = $prevErrPref
}

& schtasks.exe /Create /TN $TaskName /SC MINUTE /MO 1 /ST $st /RL HIGHEST /RU SYSTEM /TR $action /F | Out-Null

# Runs every minute as SYSTEM and applies the most recent request file.
Write-Host "[OK] Installed Scheduled Task '$TaskName' and script at '$ScriptPath'." -ForegroundColor Green
Write-Host "      Launcher will write requests to: $RequestPath" -ForegroundColor DarkGray
Write-Host "      Verify: schtasks /Query /TN $TaskName" -ForegroundColor DarkGray
