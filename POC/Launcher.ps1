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
    [switch]$ShowPassword
)

$ErrorActionPreference = "Stop"

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

# 1) Identify user
if ($OverrideUser) {
    $CurrentUserId = $OverrideUser
    Write-Host "[INFO] Using overridden userId: $CurrentUserId" -ForegroundColor Yellow
} else {
    $CurrentUserId = ""
    try { $CurrentUserId = (whoami /upn) } catch {}
    $CurrentUserId = ($CurrentUserId | Out-String).Trim()
    if (-not $CurrentUserId) { $CurrentUserId = $env:USERNAME }
    Write-Host "[INFO] Detected userId: $CurrentUserId" -ForegroundColor Cyan
}

# 2) Fetch pending request
$EncodedUserId = [Uri]::EscapeDataString($CurrentUserId)
$FetchUrl = "$ApiBaseUrl/fetch_connection?userId=$EncodedUserId"
Write-Host "[INFO] Fetching connection: $FetchUrl" -ForegroundColor DarkGray

try {
    $Response = Invoke-RestMethod -Uri $FetchUrl -Method Get -ErrorAction Stop
} catch {
    # Typical PoC case: 404 when no pending item exists.
    if ($_.Exception.Response -and $_.Exception.Response.StatusCode -eq 404) {
        Write-Host "[INFO] No pending connection request for userId '$CurrentUserId'." -ForegroundColor Gray
        exit 0
    }
    Write-Host "[ERROR] Failed calling broker API: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

if (-not $Response) {
    Write-Host "[INFO] No response body from broker." -ForegroundColor Gray
    exit 0
}

$TargetIp = [string]$Response.targetIp
$Username = [string]$Response.username
$Password = ""
if ($null -ne $Response.password) { $Password = [string]$Response.password }

Write-Host "[SUCCESS] Connection request found." -ForegroundColor Green

# 3) Write to env vars (SmartConsole reads from env)
Set-Env -Name $EnvUserVar -Value $Username
Set-Env -Name $EnvIpVar -Value $TargetIp
Set-Env -Name $EnvPassVar -Value $Password

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
    Write-Host "[ERROR] SmartConsole not found at: $SmartConsolePath" -ForegroundColor Red
    exit 1
}

Write-Host "[ACTION] Launching SmartConsole (no args)..." -ForegroundColor Green
$Process = Start-Process -FilePath $SmartConsolePath -PassThru
Write-Host "[INFO] SmartConsole PID: $($Process.Id)" -ForegroundColor DarkGray

# Keep RemoteApp alive until SmartConsole exits
Wait-Process -Id $Process.Id
Write-Host "[INFO] SmartConsole exited." -ForegroundColor Gray
exit 0
