<#
.SYNOPSIS
  AVD RemoteApp bootstrapper.
  Downloads the latest Launcher.ps1 from the Azure Function (/api/dl) and runs it.

.DESCRIPTION
  Use this script as the RemoteApp entrypoint:
    Path:      C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe
    Arguments: -NoProfile -ExecutionPolicy Bypass -File C:\S1C\LauncherRunner.ps1

  You can optionally pass -OverrideUser to force a specific userId for PoC.
#>

[CmdletBinding()]
param(
    [string]$FunctionBaseUrl = "https://s1c-function-11729.azurewebsites.net",
    [string]$OverrideUser
)

$ErrorActionPreference = "Stop"

try {
    # Ensure TLS 1.2 for older Windows builds
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    } catch {
        # If this fails, continue and let the web request decide.
    }

    $launcherUrl = "$FunctionBaseUrl/api/dl"
    $tempDir = Join-Path $env:TEMP "s1c-launcher"
    $launcherPath = Join-Path $tempDir "Launcher.ps1"

    if (-not (Test-Path $tempDir)) {
        New-Item -Path $tempDir -ItemType Directory -Force | Out-Null
    }

    Write-Host "[INFO] Downloading launcher from: $launcherUrl" -ForegroundColor Cyan
    Invoke-WebRequest -Uri $launcherUrl -UseBasicParsing -OutFile $launcherPath

    # Unblock (harmless if not needed)
    try { Unblock-File -Path $launcherPath -ErrorAction SilentlyContinue } catch {}

    Write-Host "[INFO] Running launcher..." -ForegroundColor Cyan

    $psArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $launcherPath
    )

    if ($OverrideUser) {
        $psArgs += @("-OverrideUser", $OverrideUser)
    }

    $p = Start-Process -FilePath "powershell.exe" -ArgumentList $psArgs -Wait -PassThru
    exit $p.ExitCode
}
catch {
    Write-Host "[ERROR] LauncherRunner failed: $($_.Exception.Message)" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}
