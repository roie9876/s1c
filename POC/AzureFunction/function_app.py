import azure.functions as func
import logging
import json
import os
import uuid
from azure.cosmos import CosmosClient

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Cosmos DB configuration
ENDPOINT = os.environ.get("COSMOS_ENDPOINT")
KEY = os.environ.get("COSMOS_KEY")
DATABASE_NAME = os.environ.get("COSMOS_DATABASE")
CONTAINER_NAME = os.environ.get("COSMOS_CONTAINER")

def get_container():
    client = CosmosClient(ENDPOINT, KEY)
    database = client.get_database_client(DATABASE_NAME)
    return database.get_container_client(CONTAINER_NAME)


@app.route(route="queue_connection", methods=["POST"])
def queue_connection(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Processing queue_connection request.')

    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON", status_code=400)

    user_id = req_body.get('userId')
    if not user_id:
        return func.HttpResponse("Missing 'userId'", status_code=400)

    item = {
        'id': str(uuid.uuid4()),
        'userId': user_id,
        'targetIp': req_body.get('targetIp'),
        'username': req_body.get('username'),
        'password': req_body.get('password'),
        'status': 'PENDING',
        'ttl': 60
    }

    try:
        container = get_container()
        container.create_item(body=item)
        return func.HttpResponse(
            json.dumps({"message": "Request queued", "id": item['id']}),
            mimetype="application/json",
            status_code=201
        )
    except Exception as e:
        logging.error(f"Error writing to Cosmos DB: {str(e)}")
        return func.HttpResponse(f"Internal Server Error: {str(e)}", status_code=500)


@app.route(route="fetch_connection", methods=["GET"])
def fetch_connection(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Processing fetch_connection request.')

    user_id = req.params.get('userId')
    if not user_id:
        return func.HttpResponse("Missing 'userId' query parameter", status_code=400)

    try:
        container = get_container()
        query = "SELECT * FROM c WHERE c.userId = @userId AND c.status = 'PENDING'"
        parameters = [{"name": "@userId", "value": user_id}]

        items = list(container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=False
        ))

        if not items:
            return func.HttpResponse("No pending connection found", status_code=404)

        item = items[0]
        container.delete_item(item=item['id'], partition_key=user_id)

        response_payload = {
            "targetIp": item.get('targetIp'),
            "username": item.get('username'),
            "password": item.get('password')
        }

        return func.HttpResponse(
            json.dumps(response_payload),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logging.error(f"Error accessing Cosmos DB: {str(e)}")
        return func.HttpResponse(f"Internal Server Error: {str(e)}", status_code=500)


@app.route(route="dl", methods=["GET"])
def download_launcher(req: func.HttpRequest) -> func.HttpResponse:
    """Serves the Launcher.ps1 script (manual password; username/server prefilled)."""
    logging.info('Serving Launcher.ps1 (manual password mode)')

    script_content = r'''<#!
.SYNOPSIS
    Launcher for SmartConsole: fetch request, then open UI with username/server prefilled; user types password.
#>

param (
    [string]$OverrideUser = ""
)

$ApiBaseUrl = "https://s1c-function-11729.azurewebsites.net/api"
$SmartConsolePath = "C:\\Program Files (x86)\\CheckPoint\\SmartConsole\\R82\\PROGRAM\\SmartConsole.exe"
$SmartConsoleDir = "C:\\Program Files (x86)\\CheckPoint\\SmartConsole\\R82\\PROGRAM"

$TempDir = Join-Path $env:TEMP "s1c-launcher"
if (-not (Test-Path $TempDir)) { New-Item -Path $TempDir -ItemType Directory -Force | Out-Null }
$LogPath = Join-Path $TempDir "Launcher.log"
function Write-Log([string]$Message) {
    $ts = (Get-Date).ToString("s")
    Add-Content -Path $LogPath -Value "[$ts] $Message" -ErrorAction SilentlyContinue
}
Write-Log "Launcher started"

# Diagnostics: helps compare cp1 vs cp2 (terminal host, session host VM, etc.)
try {
    $isWt = $false
    if ($env:WT_SESSION -and $env:WT_SESSION.Trim().Length -gt 0) { $isWt = $true }
    $psv = $null
    try { $psv = $PSVersionTable.PSVersion.ToString() } catch {}
    Write-Log "Diag host=$env:COMPUTERNAME session=$env:SESSIONNAME user=$env:USERNAME wt=$isWt ps=$psv"
} catch {}

# SendKeys is most reliable from an STA PowerShell process.
try {
    $apt = [System.Threading.Thread]::CurrentThread.ApartmentState
    Write-Log "ApartmentState=$apt"
    if ($apt -ne 'STA') {
        Write-Host "[INFO] Relaunching in STA mode for UI automation..." -ForegroundColor Cyan
        Write-Log "Relaunching in STA mode"
        $argsList = @('-NoProfile','-STA','-ExecutionPolicy','Bypass','-File', $PSCommandPath)
        if ($OverrideUser -and $OverrideUser.Trim().Length -gt 0) {
            $argsList += @('-OverrideUser', $OverrideUser)
        }
        $p2 = Start-Process -FilePath 'powershell.exe' -ArgumentList $argsList -Wait -PassThru
        exit $p2.ExitCode
    }
} catch {
    # If detection fails, continue.
    Write-Log "ApartmentState detection failed: $($_.Exception.Message)"
}

# Identify user
if ($OverrideUser -and $OverrideUser.Trim().Length -gt 0) {
    $CurrentUserId = $OverrideUser
    Write-Host "[INFO] Using overridden user ID: $CurrentUserId" -ForegroundColor Yellow
    Write-Log "Using overridden userId: $CurrentUserId"
} else {
    $CurrentUserId = whoami /upn
    if (-not $CurrentUserId) { $CurrentUserId = $env:USERNAME }
    Write-Host "[INFO] Detected User ID: $CurrentUserId" -ForegroundColor Cyan
    Write-Log "Detected userId: $CurrentUserId"
}

$FetchUrl = "$ApiBaseUrl/fetch_connection?userId=$CurrentUserId"
Write-Host "[INFO] Polling API: $FetchUrl"
Write-Log "Polling API: $FetchUrl"

try {
    $Response = Invoke-RestMethod -Uri $FetchUrl -Method Get -ErrorAction Stop
    if (-not $Response) { throw "Empty response" }

    $TargetIp = $Response.targetIp
    $Username = $Response.username
    Write-Host "[SUCCESS] Connection Request Found!" -ForegroundColor Green
    Write-Host "    Target: $TargetIp"
    Write-Host "    User:   $Username"
    Write-Log "Connection found. targetIp=$TargetIp username=$Username"

    if (-not (Test-Path $SmartConsolePath)) {
        Write-Host "[ERROR] SmartConsole not found at: $SmartConsolePath" -ForegroundColor Red
        Write-Log "SmartConsole not found at: $SmartConsolePath"
        Start-Sleep -Seconds 10
        exit 1
    }

    Write-Host "[ACTION] Launching SmartConsole (user will type password)..." -ForegroundColor Green
    $Process = Start-Process -FilePath $SmartConsolePath -WorkingDirectory $SmartConsoleDir -PassThru
    if (-not $Process) { throw "Failed to start SmartConsole" }
    Write-Log "Started SmartConsole. pid=$($Process.Id)"

    # Wait for main window handle (up to 30s)
    $handle = 0
    for ($i = 0; $i -lt 60; $i++) {
        $p = Get-Process -Id $Process.Id -ErrorAction SilentlyContinue
        if ($p -and $p.MainWindowHandle -ne 0) { $handle = $p.MainWindowHandle; break }
        Start-Sleep -Milliseconds 500
    }

    if ($handle -eq 0) {
        Write-Host "[WARN] Could not find SmartConsole window handle; skipping auto-fill." -ForegroundColor Yellow
        Write-Log "Could not find SmartConsole window handle; skipping auto-fill"
        Write-Host "[INFO] Waiting for SmartConsole to exit..." -ForegroundColor Cyan
        Wait-Process -Id $Process.Id -ErrorAction SilentlyContinue
        exit 0
    }

    # Bring window to foreground
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32Foreground {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}
"@
    # Extra activation attempts help in RemoteApp sessions.
    try {
        Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32Show {
    [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
}
"@
        [Win32Show]::ShowWindowAsync($handle, 9) | Out-Null  # SW_RESTORE
    } catch {}
    [Win32Foreground]::SetForegroundWindow($handle) | Out-Null
    Start-Sleep -Milliseconds 750

    # Prefill username and server; leave password blank.
    # Prefer UI Automation (more reliable in AVD RemoteApp) and fall back to SendKeys.
    $didInject = $false
    try {
        Add-Type -AssemblyName UIAutomationClient
        Add-Type -AssemblyName UIAutomationTypes

        Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public static class Win32Windows {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
}
"@

        function Get-VisibleWindowHandlesForPid([int]$Pid) {
            $handles = New-Object System.Collections.Generic.List[System.IntPtr]
            [Win32Windows]::EnumWindows({
                param([IntPtr]$hWnd, [IntPtr]$lParam)
                $outPid = 0
                [Win32Windows]::GetWindowThreadProcessId($hWnd, [ref]$outPid) | Out-Null
                if ($outPid -eq [uint32]$Pid -and [Win32Windows]::IsWindowVisible($hWnd)) {
                    $handles.Add($hWnd)
                }
                return $true
            }, [IntPtr]::Zero) | Out-Null
            return $handles
        }

        Add-Type -AssemblyName System.Windows.Forms

        function Set-ElementValue([System.Windows.Automation.AutomationElement]$El, [string]$Value, [string]$Label) {
            if (-not $El) { return $false }
            # Prefer ValuePattern; fall back to clipboard paste into focused control.
            try {
                $vp = $El.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
                if ($vp) {
                    $vp.SetValue($Value)
                    # Best-effort readback
                    try { Write-Log "$Label set via ValuePattern (len=$($Value.Length))" } catch {}
                    return $true
                }
            } catch {
                Write-Log "$Label ValuePattern failed: $($_.Exception.Message)"
            }
            try {
                $El.SetFocus()
                [System.Windows.Forms.Clipboard]::SetText($Value)
                [System.Windows.Forms.SendKeys]::SendWait('^v')
                Start-Sleep -Milliseconds 100
                try { Write-Log "$Label set via clipboard paste (len=$($Value.Length))" } catch {}
                return $true
            } catch {
                Write-Log "$Label paste failed: $($_.Exception.Message)"
            }
            return $false
        }

        function Try-InjectWithUIA([int]$Pid, [string]$User, [string]$Server) {
            $condEdit = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)
            $condCombo = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::ComboBox)

            $handles = Get-VisibleWindowHandlesForPid -Pid $Pid
            if (-not $handles -or $handles.Count -lt 1) { return $false }

            foreach ($h in $handles) {
                $win = [System.Windows.Automation.AutomationElement]::FromHandle($h)
                if (-not $win) { continue }

                $winName = ''
                try { $winName = $win.Current.Name } catch {}

                # Collect edits (we will infer Username/Server by on-screen position).
                $edits = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condEdit)
                if (-not $edits -or $edits.Count -lt 1) { continue }

                $nonPwd = @()
                foreach ($e in $edits) {
                    $isPwd = $false
                    try { $isPwd = [bool]$e.GetCurrentPropertyValue([System.Windows.Automation.AutomationElement]::IsPasswordProperty) } catch {}
                    if ($isPwd) { continue }

                    # Skip invisible/disabled
                    try {
                        if (-not $e.Current.IsEnabled) { continue }
                        if ($e.Current.IsOffscreen) { continue }
                    } catch {}

                    $top = 0; $left = 0
                    try {
                        $rect = $e.Current.BoundingRectangle
                        $top = [double]$rect.Top
                        $left = [double]$rect.Left
                    } catch {}
                    $nonPwd += [PSCustomObject]@{ El = $e; Top = $top; Left = $left }
                }

                if (-not $nonPwd -or $nonPwd.Count -lt 1) { continue }
                $sorted = $nonPwd | Sort-Object Top, Left

                $userEdit = $sorted[0].El
                $serverEdit = $null
                if ($sorted.Count -ge 2) {
                    $serverEdit = $sorted[$sorted.Count - 1].El
                }

                Write-Log "UIA window='$winName' edits=$($edits.Count) nonPwd=$($sorted.Count)"

                $didUser = Set-ElementValue -El $userEdit -Value $User -Label 'Username'
                $didServer = $false

                # Server field is often a ComboBox; try it, but also fall back to the bottom-most non-password Edit.
                $combo = $null
                try { $combo = $win.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condCombo) } catch {}
                if ($combo) {
                    # Some combos don't support ValuePattern; try inner Edit too.
                    $didServer = (Set-ElementValue -El $combo -Value $Server -Label 'Server(Combo)')
                    if (-not $didServer) {
                        try {
                            $innerEdit = $combo.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condEdit)
                            if ($innerEdit) { $didServer = (Set-ElementValue -El $innerEdit -Value $Server -Label 'Server(ComboEdit)') }
                        } catch {}
                    }
                }
                if (-not $didServer -and $serverEdit) {
                    $didServer = (Set-ElementValue -El $serverEdit -Value $Server -Label 'Server(Edit)')
                }

                # Only declare success if we actually set both fields.
                if ($didUser -and $didServer) {
                    return $true
                }
            }

            return $false
        }

        # Wait up to 30s for login UI to be ready (splash screens can appear first).
        for ($t = 0; $t -lt 60; $t++) {
            if (Try-InjectWithUIA -Pid $Process.Id -User $Username -Server $TargetIp) {
                $didInject = $true
                Write-Log "Injected fields via UIAutomation"
                break
            }
            Start-Sleep -Milliseconds 500
        }
    } catch {
        Write-Log "UIAutomation injection failed: $($_.Exception.Message)"
    }

    if (-not $didInject) {
        Add-Type -AssemblyName System.Windows.Forms
        # Some SmartConsole builds have slightly different tab order; retry with a couple variants.
        $keyVariants = @(
            "$Username{TAB}{TAB}$TargetIp",
            "$Username{TAB}$TargetIp"
        )
        foreach ($k in $keyVariants) {
            try {
                Write-Log "Falling back to SendKeys variant: $k"
                [System.Windows.Forms.SendKeys]::SendWait($k)
                Start-Sleep -Milliseconds 300
                $didInject = $true
                Write-Log "Injected fields via SendKeys"
                break
            } catch {
                Write-Log "SendKeys failed: $($_.Exception.Message)"
            }
        }
    }

    if ($didInject) {
        Write-Host "[INFO] Prefilled username/server; please type password and click Login." -ForegroundColor Cyan
    } else {
        Write-Host "[WARN] Could not auto-fill fields. Please enter username/server manually." -ForegroundColor Yellow
    }

    # IMPORTANT for AVD RemoteApp: keep the published process alive so the session doesn't end.
    Write-Host "[INFO] Waiting for SmartConsole to exit..." -ForegroundColor Cyan
    Wait-Process -Id $Process.Id -ErrorAction SilentlyContinue
}
catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    Write-Log "ERROR: $($_.Exception.Message)"
    Start-Sleep -Seconds 10
}
'''
    return func.HttpResponse(
        script_content,
        mimetype="text/plain",
        status_code=200,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.route(route="wdac", auth_level=func.AuthLevel.ANONYMOUS)
def download_wdac(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Downloading WDAC Update Script.')
    script_content = r'''# Script to whitelist Check Point SmartConsole in WDAC
# Run as Administrator

$ErrorActionPreference = "Stop"

$SmartConsolePath = "C:\\Program Files (x86)\\CheckPoint\\SmartConsole\\R82\\PROGRAM"
$TempDir = "C:\\Temp\\WDAC_SmartConsole"
$PolicyXml = "$TempDir\\SmartConsoleAllow.xml"
$PolicyBin = "$TempDir\\SmartConsoleAllow.cip"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "   WDAC Policy Updater for SmartConsole   " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Check Prerequisites
if (-not (Test-Path $SmartConsolePath)) {
    Write-Error "SmartConsole directory not found at: $SmartConsolePath"
    exit 1
}

if (-not (Get-Command New-CIPolicy -ErrorAction SilentlyContinue)) {
    Write-Error "ConfigCI module not found. Ensure you are running on Windows Enterprise/Pro and have the feature enabled."
    exit 1
}

# 2. Create Temp Directory
if (-not (Test-Path $TempDir)) {
    New-Item -Path $TempDir -ItemType Directory -Force | Out-Null
}

Write-Host "[1/4] Scanning SmartConsole directory for signatures..." -ForegroundColor Cyan
Write-Host "      Path: $SmartConsolePath"
Write-Host "      This may take a minute..."

# 3. Create Policy (Publisher Level)
New-CIPolicy -Level Publisher -Fallback Hash -UserPEs -ScanPath $SmartConsolePath -FilePath $PolicyXml

Write-Host "[2/4] Converting policy to binary..." -ForegroundColor Cyan
ConvertFrom-CIPolicy -XmlFilePath $PolicyXml -BinaryFilePath $PolicyBin

Write-Host "[3/4] Attempting to apply policy..." -ForegroundColor Cyan

if (Get-Command CiTool -ErrorAction SilentlyContinue) {
    Write-Host "      Using CiTool to update policy..."
    CiTool --update-policy $PolicyBin
    Write-Host "[SUCCESS] Policy updated successfully via CiTool." -ForegroundColor Green
}
else {
    Write-Host "[WARNING] CiTool not found. You must manually copy the policy." -ForegroundColor Yellow
    [xml]$xml = Get-Content $PolicyXml
    $PolicyID = $xml.SiPolicy.PolicyID
    $DestPath = "C:\\Windows\\System32\\CodeIntegrity\\CiPolicies\\Active\\{$PolicyID}.cip"
    Write-Host "      Policy ID: $PolicyID"
    Write-Host "      Destination: $DestPath"
    try {
        if (-not (Test-Path "C:\\Windows\\System32\\CodeIntegrity\\CiPolicies\\Active")) {
             New-Item -Path "C:\\Windows\\System32\\CodeIntegrity\\CiPolicies\\Active" -ItemType Directory -Force | Out-Null
        }
        Copy-Item -Path $PolicyBin -Destination $DestPath -Force
        Write-Host "[SUCCESS] Policy copied to Active folder. A reboot may be required." -ForegroundColor Green
    }
    catch {
        Write-Error "Failed to copy policy file. Ensure you are running as Administrator."
    }
}

Write-Host "`nDone. Please try running the SmartConsole Launcher again." -ForegroundColor Green
'''
    return func.HttpResponse(script_content, mimetype="text/plain", status_code=200)


@app.route(route="wdac_bat", auth_level=func.AuthLevel.ANONYMOUS)
def download_wdac_bat(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Downloading WDAC Batch Wrapper.')
    script_content = r'''@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "Update-WDAC.ps1"
pause
'''
    return func.HttpResponse(script_content, mimetype="text/plain", status_code=200)

