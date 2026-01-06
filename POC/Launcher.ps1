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
    [switch]$PersistUserEnv,
    [switch]$ShowPassword,
    [int]$PollSeconds = 60,
    [int]$PollIntervalSeconds = 3,
    [int]$HoldSeconds = 10,
    [switch]$ShowDialog
)

$ErrorActionPreference = "Stop"

$logDir = Join-Path $env:TEMP "s1c-launcher"
if (-not (Test-Path $logDir)) { New-Item -Path $logDir -ItemType Directory -Force | Out-Null }
$logPath = Join-Path $logDir "Launcher.log"
function Write-Log([string]$Message) {
    $ts = (Get-Date).ToString('s')
    $line = "[$ts] $Message"
    try { Add-Content -Path $logPath -Value $line -ErrorAction SilentlyContinue } catch {}
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

function Set-Env([string]$Name, [string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Name)) { return }
    Set-Item -Path ("Env:" + $Name) -Value $Value
    if ($PersistUserEnv) {
        try {
            [Environment]::SetEnvironmentVariable($Name, $Value, "User")
        } catch {
            Write-Host "[WARN] Failed to persist env var '$Name' at User scope: $($_.Exception.Message)" -ForegroundColor Yellow
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
    Write-Host "[INFO] Log file: $logPath" -ForegroundColor DarkGray
    try { Write-Log ("whoami_upn=" + (whoami /upn)) } catch {}
    Write-Log ("PSVersion=" + $PSVersionTable.PSVersion)

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

    Write-Host "[SUCCESS] Connection request found." -ForegroundColor Green
    Write-Log "Connection request found"

    # 3) Write to env vars (SmartConsole reads from env)
    Set-Env -Name $EnvUserVar -Value $Username
    Set-Env -Name $EnvIpVar -Value $TargetIp
    Set-Env -Name $EnvPassVar -Value $Password
    Write-Log ("Set env vars: " + $EnvUserVar + "," + $EnvIpVar + "," + $EnvPassVar)

    # 4) Display values FROM env vars
    $EnvUser = Get-Env -Name $EnvUserVar
    $EnvIp = Get-Env -Name $EnvIpVar
    $EnvPass = Get-Env -Name $EnvPassVar

    Write-Host "[INFO] Environment variables set:" -ForegroundColor Cyan
    Write-Host "  $EnvUserVar=$EnvUser"
    Write-Host "  $EnvIpVar=$EnvIp"
    if ($ShowPassword) {
        Write-Host "  $EnvPassVar=$EnvPass" -ForegroundColor Yellow
    } else {
        Write-Host "  $EnvPassVar=$(Mask-Secret $EnvPass) (masked)" -ForegroundColor DarkGray
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
