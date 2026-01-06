<#
.SYNOPSIS
  AVD RemoteApp bootstrapper.
  Downloads the latest Launcher.ps1 from the Azure Function (/api/dl) and runs it.

.IMPORTANT
    DEPRECATED for the current PoC.
    Use the single-script launcher instead:
        powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\S1C\Launcher.ps1

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

$tempDir = Join-Path $env:TEMP "s1c-launcher"
if (-not (Test-Path $tempDir)) { New-Item -Path $tempDir -ItemType Directory -Force | Out-Null }
$logPath = Join-Path $tempDir "LauncherRunner.log"
function Write-Log([string]$Message) {
    $ts = (Get-Date).ToString('s')
    Add-Content -Path $logPath -Value "[$ts] $Message" -ErrorAction SilentlyContinue
}
Write-Log "LauncherRunner started"
Write-Log "PSVersion=$($PSVersionTable.PSVersion)"
try { Write-Log "whoami_upn=$(whoami /upn)" } catch {}

try {
    try { Start-Transcript -Path $logPath -Append | Out-Null } catch {}

    # Ensure TLS 1.2 for older Windows builds
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    } catch {
        # If this fails, continue and let the web request decide.
    }

    $cacheBust = [Guid]::NewGuid().ToString('N')
    $launcherUrl = "$FunctionBaseUrl/api/dl?nocache=$cacheBust"
    $launcherPath = Join-Path $tempDir "Launcher.ps1"

    Write-Host "[INFO] Downloading launcher from: $launcherUrl" -ForegroundColor Cyan
    Write-Log "Downloading launcher from: $launcherUrl"
    Invoke-WebRequest -Uri $launcherUrl -UseBasicParsing -OutFile $launcherPath -Headers @{
        'Cache-Control' = 'no-cache'
        'Pragma'        = 'no-cache'
    }

    Write-Log "Downloaded to: $launcherPath"

    # Unblock (harmless if not needed)
    try { Unblock-File -Path $launcherPath -ErrorAction SilentlyContinue } catch {}

    Write-Host "[INFO] Running launcher..." -ForegroundColor Cyan
    Write-Log "Starting launcher"

    $psArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $launcherPath
    )

    if ($OverrideUser) {
        $psArgs += @("-OverrideUser", $OverrideUser)
    }

    $p = Start-Process -FilePath "powershell.exe" -ArgumentList $psArgs -Wait -PassThru
    Write-Log "Launcher exitCode=$($p.ExitCode)"
    exit $p.ExitCode
}
catch {
    Write-Host "[ERROR] LauncherRunner failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Log "ERROR: $($_.Exception.Message)"
    exit 1
}
finally {
    try { Stop-Transcript | Out-Null } catch {}
}
