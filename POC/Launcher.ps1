<#
.SYNOPSIS
    Single-script PoC Launcher for AVD RemoteApp.

.DESCRIPTION
    1) Detects the current userId (UPN preferred).
    2) Fetches a pending connection request from the broker API.
    3) Writes username/server/password into Windows environment variables.
    4) Displays the values *from the environment variables*.
    5) Launches SmartConsole with NO credential injection and NO password args.

    IMPORTANT: Do not add any UI automation / input injection here.
    SmartConsole is expected to read the required values from environment variables.

.PARAMETER OverrideUser
    Optional userId override for testing.

.PARAMETER ApiBaseUrl
    Broker API base URL (default points to the deployed Azure Function).

.PARAMETER SmartConsolePath
    Path to SmartConsole.exe.

.PARAMETER EnvUserVar
.PARAMETER EnvIpVar
.PARAMETER EnvPassVar
    Environment variable names SmartConsole reads.

.PARAMETER PersistUserEnv
    Also persists env vars at the *User* scope (affects new processes/sessions).

.PARAMETER ShowPassword
    Prints the password value to the console. Default is masked.
#>

[CmdletBinding()]
param(
    [string]$OverrideUser = "",
    [string]$ApiBaseUrl = "https://s1c-function-11729.azurewebsites.net/api",
    [string]$SmartConsolePath = "C:\Program Files (x86)\CheckPoint\SmartConsole\R82\PROGRAM\SmartConsole.exe",
    [string]$EnvUserVar = "S1C_USERNAME",
    [string]$EnvIpVar = "S1C_TARGET_IP",
    [string]$EnvPassVar = "S1C_PASSWORD",
    [string]$EnvAppStreamCtxVar = "APPSTREAM_SESSION_CONTEXT",
    [switch]$PersistUserEnv,
    [switch]$PersistMachineEnv,
    # Default: persist only APPSTREAM_SESSION_CONTEXT at Machine scope (System env vars)
    # so it shows up in the Windows "System variables" UI. Requires admin.
    [bool]$PersistContextMachineEnv = $true,
    # If the launcher is not running elevated, it cannot write Machine env vars directly.
    # This optional fallback uses a pre-created Scheduled Task that runs as SYSTEM.
    [bool]$UseScheduledTaskForMachineEnv = $true,
    [string]$MachineEnvTaskName = "S1C-SetMachineEnv",
    [string]$MachineEnvRequestPath = "",
    [switch]$ShowPassword,
    [int]$PollSeconds = 60,
    [int]$PollIntervalSeconds = 3,
    [int]$HoldSeconds = 10,
    [switch]$ShowDialog
)

$ScriptVersion = "2026-01-06"  # bump when Launcher behavior changes

$ErrorActionPreference = "Stop"

$logDir = Join-Path $env:TEMP "s1c-launcher"
if (-not (Test-Path $logDir)) { New-Item -Path $logDir -ItemType Directory -Force | Out-Null }
$logPath = Join-Path $logDir "Launcher.log"
function Write-Log([string]$Message) {
    $ts = (Get-Date).ToString('s')
    $line = "[$ts] $Message"
    try { Add-Content -Path $logPath -Value $line -ErrorAction SilentlyContinue } catch {}
}

if ([string]::IsNullOrWhiteSpace($MachineEnvRequestPath)) {
    $MachineEnvRequestPath = Join-Path $env:ProgramData "S1C\machine-env-request.json"
}
function Hold-Open([string]$Text) {
    if ($ShowDialog) {
        try {
            Add-Type -AssemblyName PresentationFramework -ErrorAction SilentlyContinue | Out-Null
            [System.Windows.MessageBox]::Show($Text, "S1C Launcher") | Out-Null
            return
        } catch {
            # ignore and fall back to sleep
        }
    }
    if ($HoldSeconds -gt 0) {
        Start-Sleep -Seconds $HoldSeconds
    }
}

function Try-GetHttpStatusCode($Exception) {
    try {
        $resp = $Exception.Response
        if ($resp -and $resp.StatusCode) {
            # PS7: HttpResponseMessage
            if ($resp.StatusCode.value__) { return [int]$resp.StatusCode.value__ }
            return [int]$resp.StatusCode
        }
    } catch {}
    try {
        # Windows PowerShell WebException
        if ($Exception.Exception -and $Exception.Exception.Response -and $Exception.Exception.Response.StatusCode) {
            return [int]$Exception.Exception.Response.StatusCode
        }
    } catch {}
    return $null
}

function Mask-Secret([string]$Value) {
    if (-not $Value) { return "" }
    if ($Value.Length -le 4) { return "****" }
    return ($Value.Substring(0,2) + "***" + $Value.Substring($Value.Length-2, 2))
}

function Test-IsAdmin {
    try {
        $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
        return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch {
        return $false
    }
}

function Broadcast-EnvChange {
    try {
        Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class NativeMethods {
  [DllImport("user32.dll", SetLastError=true, CharSet=CharSet.Auto)]
  public static extern IntPtr SendMessageTimeout(IntPtr hWnd, int Msg, IntPtr wParam, string lParam, int fuFlags, int uTimeout, out IntPtr lpdwResult);
}
"@ -ErrorAction SilentlyContinue | Out-Null
        $HWND_BROADCAST = [IntPtr]0xFFFF
        $WM_SETTINGCHANGE = 0x001A
        $SMTO_ABORTIFHUNG = 0x0002
        $result = [IntPtr]::Zero
        [NativeMethods]::SendMessageTimeout($HWND_BROADCAST, $WM_SETTINGCHANGE, [IntPtr]::Zero, "Environment", $SMTO_ABORTIFHUNG, 2000, [ref]$result) | Out-Null
    } catch {
        # ignore
    }
}

function Try-SetMachineEnvViaScheduledTask([string]$Name, [string]$Value) {
    if (-not $UseScheduledTaskForMachineEnv) { return $false }
    if ([string]::IsNullOrWhiteSpace($MachineEnvTaskName)) { return $false }
    if ([string]::IsNullOrWhiteSpace($MachineEnvRequestPath)) { return $false }

    try {
        $dir = Split-Path -Parent $MachineEnvRequestPath
        if (-not (Test-Path $dir)) { New-Item -Path $dir -ItemType Directory -Force | Out-Null }

        if ([string]::IsNullOrWhiteSpace($Value)) { return $false }
        $payload = @{ name = $Name; value = $Value } | ConvertTo-Json -Compress
        try {
            Set-Content -Path $MachineEnvRequestPath -Value $payload -Encoding UTF8 -Force
        } catch {
            $err = $_.Exception.Message
            Write-Log ("WARN: Failed to write MachineEnvRequestPath '" + $MachineEnvRequestPath + "': " + $err)
            return $false
        }

        # Prefer a minute-based SYSTEM task (no need to trigger it from this user context).
        # If schtasks /Run works, we use it to apply faster; otherwise, the next scheduled run will apply.
        $runOut = & schtasks.exe /Run /TN $MachineEnvTaskName 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Log ("INFO: Wrote machine env request file; schtasks /Run not permitted or failed for '" + $MachineEnvTaskName + "': " + ($runOut | Out-String).Trim())
        }
        Start-Sleep -Milliseconds 300
        return $true
    } catch {
        try { Write-Log ("WARN: Scheduled-task Machine env fallback threw: " + $_.Exception.Message) } catch {}
        return $false
    }
}

$IsAdmin = Test-IsAdmin
$WarnedMachineEnv = $false

function Set-Env([string]$Name, [string]$Value, [switch]$MachineOnly) {
    if ([string]::IsNullOrWhiteSpace($Name)) { return }
    Set-Item -Path ("Env:" + $Name) -Value $Value
    if ($PersistUserEnv -and -not $MachineOnly) {
        try {
            [Environment]::SetEnvironmentVariable($Name, $Value, "User")
        } catch {
            Write-Host "[WARN] Failed to persist env var '$Name' at User scope: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }

    $shouldPersistMachine = $PersistMachineEnv -or ($PersistContextMachineEnv -and $Name -eq $EnvAppStreamCtxVar) -or $MachineOnly
    if ($shouldPersistMachine) {
        if (-not $IsAdmin) {
            # Try scheduled-task fallback (SYSTEM) if configured.
            $usedTask = $false
            if ($Name -eq $EnvAppStreamCtxVar -or $MachineOnly) {
                $usedTask = Try-SetMachineEnvViaScheduledTask -Name $Name -Value $Value
            }
            if ($usedTask) {
                $msg = "Used Scheduled Task '$MachineEnvTaskName' to set Machine env var '$Name'."
                Write-Host "[INFO] $msg" -ForegroundColor DarkGray
                Write-Log $msg
            }
            if (-not $usedTask) {
                if (-not $WarnedMachineEnv) {
                    $warn = "Cannot persist Machine/System env vars without admin rights. '$EnvAppStreamCtxVar' will be process-only (and User-only if -PersistUserEnv is used). To enable system persistence without admin, create the Scheduled Task '$MachineEnvTaskName' to run as SYSTEM."
                    Write-Host "[WARN] $warn" -ForegroundColor Yellow
                    Write-Log ("WARN: " + $warn)
                    $WarnedMachineEnv = $true
                }
            }
            return
        }
        try {
            [Environment]::SetEnvironmentVariable($Name, $Value, "Machine")
            Broadcast-EnvChange
        } catch {
            Write-Host "[WARN] Failed to persist env var '$Name' at Machine scope (requires admin): $($_.Exception.Message)" -ForegroundColor Yellow
            Write-Log ("WARN: Failed to persist Machine env var '" + $Name + "': " + $($_.Exception.Message))
        }
    }
}

function Get-Env([string]$Name) {
    if ([string]::IsNullOrWhiteSpace($Name)) { return "" }
    try {
        return (Get-Item -Path ("Env:" + $Name) -ErrorAction Stop).Value
    } catch {
        return ""
    }
}

try {
    Write-Log "Launcher started"
    $scriptPath = $PSCommandPath
    if (-not $scriptPath) { try { $scriptPath = $MyInvocation.MyCommand.Path } catch {} }
    if (-not $scriptPath) { $scriptPath = "(unknown)" }

    Write-Host "[INFO] Launcher version: $ScriptVersion" -ForegroundColor DarkGray
    Write-Host "[INFO] Launcher path: $scriptPath" -ForegroundColor DarkGray
    Write-Log ("LauncherVersion=" + $ScriptVersion)
    Write-Log ("LauncherPath=" + $scriptPath)

    Write-Host "[INFO] Log file: $logPath" -ForegroundColor DarkGray
    try { Write-Log ("whoami_upn=" + (whoami /upn)) } catch {}
    Write-Log ("PSVersion=" + $PSVersionTable.PSVersion)

    Write-Log ("PersistContextMachineEnv=" + $PersistContextMachineEnv)
    Write-Log ("UseScheduledTaskForMachineEnv=" + $UseScheduledTaskForMachineEnv)
    Write-Log ("MachineEnvTaskName=" + $MachineEnvTaskName)
    Write-Log ("MachineEnvRequestPath=" + $MachineEnvRequestPath)

    # 1) Identify user
    if ($OverrideUser) {
        $CurrentUserId = $OverrideUser
        Write-Host "[INFO] Using overridden userId: $CurrentUserId" -ForegroundColor Yellow
        Write-Log "Using overridden userId"
    } else {
        $CurrentUserId = ""
        try { $CurrentUserId = (whoami /upn) } catch {}
        $CurrentUserId = ($CurrentUserId | Out-String).Trim()
        if (-not $CurrentUserId) { $CurrentUserId = $env:USERNAME }
        Write-Host "[INFO] Detected userId: $CurrentUserId" -ForegroundColor Cyan
        Write-Log ("Detected userId=" + $CurrentUserId)
    }

    # 2) Fetch pending request (optionally poll on 404)
    $EncodedUserId = [Uri]::EscapeDataString($CurrentUserId)
    $FetchUrl = "$ApiBaseUrl/fetch_connection?userId=$EncodedUserId"
    Write-Host "[INFO] Fetching connection..." -ForegroundColor DarkGray
    Write-Log ("FetchUrl=" + $FetchUrl)

    $Response = $null
    $pollUntil = $null
    if ($PollSeconds -gt 0) {
        $pollUntil = (Get-Date).AddSeconds($PollSeconds)
        if ($PollIntervalSeconds -le 0) { $PollIntervalSeconds = 3 }
    }

    while ($true) {
        try {
            $Response = Invoke-RestMethod -Uri $FetchUrl -Method Get -ErrorAction Stop
            break
        } catch {
            $status = Try-GetHttpStatusCode $_
            if ($status -eq 404) {
                if ($pollUntil -and (Get-Date) -lt $pollUntil) {
                    Write-Host "[INFO] No pending request yet. Waiting..." -ForegroundColor Gray
                    Write-Log "No pending request yet; polling"
                    Start-Sleep -Seconds $PollIntervalSeconds
                    continue
                }

                $msg = "No pending connection request for userId '$CurrentUserId'."
                Write-Host "[INFO] $msg" -ForegroundColor Gray
                Write-Log $msg
                Hold-Open ("$msg`n`nLog: $logPath")
                exit 0
            }

            $msg = "Failed calling broker API. status=$status err=$($_.Exception.Message)"
            Write-Host "[ERROR] $msg" -ForegroundColor Red
            Write-Log $msg
            Hold-Open ("$msg`n`nLog: $logPath")
            exit 1
        }
    }

    if (-not $Response) {
        $msg = "No response body from broker."
        Write-Host "[INFO] $msg" -ForegroundColor Gray
        Write-Log $msg
        Hold-Open ("$msg`n`nLog: $logPath")
        exit 0
    }

    $TargetIp = [string]$Response.targetIp
    $Username = [string]$Response.username
    $Password = ""
    if ($null -ne $Response.password) { $Password = [string]$Response.password }
    $AppStreamCtx = ""
    if ($null -ne $Response.appstreamSessionContext) { $AppStreamCtx = [string]$Response.appstreamSessionContext }

    Write-Host "[SUCCESS] Connection request found." -ForegroundColor Green
    Write-Log "Connection request found"

    # 3) Write to env vars (SmartConsole reads from env)
    # Credentials are set for the process only (and optionally User scope if -PersistUserEnv).
    Set-Env -Name $EnvUserVar -Value $Username
    Set-Env -Name $EnvIpVar -Value $TargetIp
    Set-Env -Name $EnvPassVar -Value $Password

    # Session context is persisted to Machine/System env by default (requires admin).
    Set-Env -Name $EnvAppStreamCtxVar -Value $AppStreamCtx -MachineOnly
    Write-Log ("Set env vars: " + $EnvUserVar + "," + $EnvIpVar + "," + $EnvPassVar + "," + $EnvAppStreamCtxVar)

    # 4) Display values FROM env vars
    $EnvUser = Get-Env -Name $EnvUserVar
    $EnvIp = Get-Env -Name $EnvIpVar
    $EnvPass = Get-Env -Name $EnvPassVar
    $EnvCtx = Get-Env -Name $EnvAppStreamCtxVar

    Write-Host "[INFO] Environment variables set:" -ForegroundColor Cyan
    Write-Host "  $EnvUserVar=$EnvUser"
    Write-Host "  $EnvIpVar=$EnvIp"
    if ($ShowPassword) {
        Write-Host "  $EnvPassVar=$EnvPass" -ForegroundColor Yellow
    } else {
        Write-Host "  $EnvPassVar=$(Mask-Secret $EnvPass) (masked)" -ForegroundColor DarkGray
    }

    # Context may be sensitive; keep it masked unless ShowPassword is set.
    if ($ShowPassword) {
        Write-Host "  $EnvAppStreamCtxVar=$EnvCtx" -ForegroundColor Yellow
    } else {
        Write-Host "  $EnvAppStreamCtxVar=$(Mask-Secret $EnvCtx) (masked)" -ForegroundColor DarkGray
    }

    # 5) Launch SmartConsole with NO args (no injection)
    if (-not (Test-Path $SmartConsolePath)) {
        $msg = "SmartConsole not found at: $SmartConsolePath"
        Write-Host "[ERROR] $msg" -ForegroundColor Red
        Write-Log $msg
        Hold-Open ("$msg`n`nLog: $logPath")
        exit 1
    }

    Write-Host "[ACTION] Launching SmartConsole (no args)..." -ForegroundColor Green
    Write-Log ("Launching SmartConsole: " + $SmartConsolePath)
    $Process = Start-Process -FilePath $SmartConsolePath -PassThru
    Write-Host "[INFO] SmartConsole PID: $($Process.Id)" -ForegroundColor DarkGray
    Write-Log ("SmartConsole pid=" + $Process.Id)

    # Keep RemoteApp alive until SmartConsole exits
    Wait-Process -Id $Process.Id
    Write-Host "[INFO] SmartConsole exited." -ForegroundColor Gray
    Write-Log "SmartConsole exited"
    exit 0
}
catch {
    $msg = "Unhandled exception: $($_.Exception.Message)"
    Write-Host "[ERROR] $msg" -ForegroundColor Red
    Write-Log $msg
    Hold-Open ("$msg`n`nLog: $logPath")
    exit 1
}
