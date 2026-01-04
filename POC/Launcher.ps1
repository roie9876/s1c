<#
.SYNOPSIS
    PoC Launcher for Smart Console Migration.
    Polls the Azure Backend for pending connection requests and launches the application.

.DESCRIPTION
    This script simulates the "Helper App" that will run inside the Azure Virtual Desktop session.
    1. Identifies the current user (UPN).
    2. Calls the Azure Function API to check for pending connection requests.
    3. If a request is found, it launches the target application (Notepad for PoC) with the retrieved context.

.PARAMETER OverrideUser
    Optional. Manually specify a user ID for testing purposes (e.g., "roie@mssp.com").
    If not provided, the script attempts to detect the logged-in user's UPN.

.EXAMPLE
    .\Launcher.ps1 -OverrideUser "roie@mssp.com"
#>

param (
    [string]$OverrideUser = ""
)

# --- CONFIGURATION ---
# Pointing to the Azure Function (Production)
$ApiBaseUrl = "https://s1c-function-11729.azurewebsites.net/api"
# $ApiBaseUrl = "http://localhost:5000/api" 

# --- MAIN LOGIC ---

# 1. Identify User
if ($OverrideUser) {
    $CurrentUserId = $OverrideUser
    Write-Host "[INFO] Using overridden user ID: $CurrentUserId" -ForegroundColor Yellow
} else {
    # Try to get UPN (works on domain joined machines)
    $CurrentUserId = whoami /upn
    
    if (-not $CurrentUserId) {
        # Fallback for non-domain machines
        $CurrentUserId = $env:USERNAME
    }
    Write-Host "[INFO] Detected User ID: $CurrentUserId" -ForegroundColor Cyan
}

# 2. Poll Backend
$FetchUrl = "$ApiBaseUrl/fetch_connection?userId=$CurrentUserId"
Write-Host "[INFO] Polling API: $FetchUrl"

try {
    $Response = Invoke-RestMethod -Uri $FetchUrl -Method Get -ErrorAction Stop
    
    if ($Response) {
        Write-Host "[SUCCESS] Connection Request Found!" -ForegroundColor Green
        
        $TargetIp = $Response.targetIp
        $Username = $Response.username
        $Password = $Response.password # In real scenario, decrypt this
        
        Write-Host "    Target: $TargetIp"
        Write-Host "    User:   $Username"
        
        # 3. Launch Application
        # Simulating SmartConsole.exe with Notepad
        # We pass the context as arguments to prove we have them
        
        Write-Host "[ACTION] Launching Application..." -ForegroundColor Green
        
        # $Args = "Target=$TargetIp User=$Username"
        # Start-Process "notepad.exe" -ArgumentList $Args
        
        # Real Implementation:
        # Adjust the path below to match your specific SmartConsole version (e.g., R81.10, R81.20)
        $SmartConsolePath = "C:\Program Files (x86)\CheckPoint\SmartConsole\R82\PROGRAM\SmartConsole.exe"
        
        if (Test-Path $SmartConsolePath) {
            Start-Process $SmartConsolePath -ArgumentList "-p $Password -u $Username -s $TargetIp"
        } else {
            Write-Host "[ERROR] SmartConsole not found at: $SmartConsolePath" -ForegroundColor Red
        }
        
    }
}
catch {
    if ($_.Exception.Response.StatusCode -eq "NotFound") {
        Write-Host "[INFO] No pending connection requests found for user $CurrentUserId." -ForegroundColor Gray
    }
    else {
        Write-Host "[ERROR] Failed to contact API: $($_.Exception.Message)" -ForegroundColor Red
    }
}
