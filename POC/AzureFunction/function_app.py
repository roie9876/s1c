import azure.functions as func
import logging
import json
import os
import uuid
from azure.cosmos import CosmosClient, PartitionKey

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# --- COSMOS DB CONFIGURATION ---
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

    # Prepare the document
    item = {
        'id': str(uuid.uuid4()),
        'userId': user_id,
        'targetIp': req_body.get('targetIp'),
        'username': req_body.get('username'),
        'password': req_body.get('password'), # In real app, this should be encrypted!
        'status': 'PENDING',
        'ttl': 60 # Auto-expire after 60 seconds
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
        
        # Query for PENDING requests for this user
        # We take the first one found
        query = "SELECT * FROM c WHERE c.userId = @userId AND c.status = 'PENDING'"
        parameters = [{"name": "@userId", "value": user_id}]
        
        items = list(container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=False # Partition Key is userId, so this is efficient
        ))

        if not items:
            return func.HttpResponse("No pending connection found", status_code=404)

        # Get the first item
        item = items[0]
        
        # CONSUME the item (Delete it so it can't be reused)
        # Alternatively, we could update status to 'CONSUMED'
        container.delete_item(item=item['id'], partition_key=user_id)

        # Return the payload
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
    """
    Serves the Launcher.ps1 script directly.
    Allows AVD VMs to download the script without clipboard/drive mapping.
    Short route: /api/dl
    """
    logging.info('Serving Launcher.ps1')
    
    # The script content (Embedded for simplicity in PoC)
    script_content = r'''<#
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
    # [PoC Shortcut] Defaulting to the hardcoded Portal user so you don't have to type it every time
    [string]$OverrideUser = "roie@mssp.com"
)

# --- CONFIGURATION ---
# Pointing to the Azure Function (Production)
$ApiBaseUrl = "https://s1c-function-11729.azurewebsites.net/api"

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
        $SmartConsoleDir = "C:\Program Files (x86)\CheckPoint\SmartConsole\R82\PROGRAM"
        
        if (Test-Path $SmartConsolePath) {
            Write-Host "[DEBUG] Launching from: $SmartConsoleDir" -ForegroundColor Cyan
            
            # Method 9: XML Parameter File (The "Golden" Method)
            # SmartConsole supports passing an XML file with credentials, which avoids all CLI escaping issues.
            
            Write-Host "[ACTION] Creating Login Parameter File..." -ForegroundColor Green
            
            $LoginXmlPath = "$env:TEMP\SmartConsoleLogin_$($PID).xml"
            
            # Construct the XML content
            # We use CDATA for the password to handle special characters safely
            # We also include the XML declaration
            
            $XmlContent = @"
<?xml version="1.0" encoding="utf-8"?>
<RemoteLaunchParemeters xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <Username>$Username</Username>
    <Password>$SafePassword</Password>
    <ServerIP>$TargetIp</ServerIP>
    <DomainName></DomainName>
    <ReadOnly>False</ReadOnly>
    <CloudDemoMode>False</CloudDemoMode>
</RemoteLaunchParemeters>
"@
            
            # Use Set-Content to include BOM (Reverting to what worked for opening the app)
            Set-Content -Path $LoginXmlPath -Value $XmlContent -Encoding UTF8
            Write-Host "[INFO] Login XML created at: $LoginXmlPath" -ForegroundColor Gray
            
            Write-Host "[ACTION] Launching SmartConsole with XML..." -ForegroundColor Green
            
            try {
                # Launch SmartConsole pointing to the XML file
                # We use Start-Process to ensure it detaches properly
                $Process = Start-Process -FilePath $SmartConsolePath -ArgumentList "-p `"$LoginXmlPath`"" -WorkingDirectory $SmartConsoleDir -PassThru
                
                if ($Process) {
                    Write-Host "[SUCCESS] SmartConsole launched (PID: $($Process.Id))." -ForegroundColor Green
                    
                    # Wait a few seconds to ensure it reads the file
                    Start-Sleep -Seconds 5
                    
                    # Optional: Clean up the XML file (Security Best Practice)
                    # In a real deployment, you might want to wait longer or use a scheduled task to delete it.
                    # For now, we'll leave it or delete it if the process is stable.
                    if (-not $Process.HasExited) {
                        # Remove-Item -Path $LoginXmlPath -Force
                        Write-Host "[INFO] XML file preserved for debugging. (Ideally delete this in production)" -ForegroundColor Gray
                    } else {
                        Write-Host "[ERROR] Process exited immediately." -ForegroundColor Red
                    }
                }
            } catch {
                Write-Host "[ERROR] Failed to start process: $_" -ForegroundColor Red
            }
            
        } else {
            Write-Host "[ERROR] SmartConsole not found at: $SmartConsolePath" -ForegroundColor Red
        }
        
        # Keep window open
        Read-Host "Press Enter to exit..."
        
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
'''
    return func.HttpResponse(
        script_content,
        mimetype="text/plain",
        status_code=200
    )

@app.route(route="wdac", auth_level=func.AuthLevel.ANONYMOUS)
def download_wdac(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Downloading WDAC Update Script.')
    
    script_content = r'''# Script to whitelist Check Point SmartConsole in WDAC
# Run as Administrator

$ErrorActionPreference = "Stop"

$SmartConsolePath = "C:\Program Files (x86)\CheckPoint\SmartConsole\R82\PROGRAM"
$TempDir = "C:\Temp\WDAC_SmartConsole"
$PolicyXml = "$TempDir\SmartConsoleAllow.xml"
$PolicyBin = "$TempDir\SmartConsoleAllow.cip"

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
# We use -UserPEs to include user-mode executables
# -Level Publisher trusts the certificate (Check Point Software Technologies Ltd.)
New-CIPolicy -Level Publisher -Fallback Hash -UserPEs -ScanPath $SmartConsolePath -FilePath $PolicyXml

Write-Host "[2/4] Converting policy to binary..." -ForegroundColor Cyan
ConvertFrom-CIPolicy -XmlFilePath $PolicyXml -BinaryFilePath $PolicyBin

Write-Host "[3/4] Attempting to apply policy..." -ForegroundColor Cyan

# 4. Apply Policy
if (Get-Command CiTool -ErrorAction SilentlyContinue) {
    Write-Host "      Using CiTool to update policy..."
    CiTool --update-policy $PolicyBin
    Write-Host "[SUCCESS] Policy updated successfully via CiTool." -ForegroundColor Green
}
else {
    Write-Host "[WARNING] CiTool not found. You must manually copy the policy." -ForegroundColor Yellow
    
    # Extract GUID from XML to name the file correctly for the Active folder
    [xml]$xml = Get-Content $PolicyXml
    $PolicyID = $xml.SiPolicy.PolicyID
    $DestPath = "C:\Windows\System32\CodeIntegrity\CiPolicies\Active\{$PolicyID}.cip"
    
    Write-Host "      Policy ID: $PolicyID"
    Write-Host "      Destination: $DestPath"
    
    try {
        if (-not (Test-Path "C:\Windows\System32\CodeIntegrity\CiPolicies\Active")) {
             New-Item -Path "C:\Windows\System32\CodeIntegrity\CiPolicies\Active" -ItemType Directory -Force | Out-Null
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
    return func.HttpResponse(
        script_content,
        mimetype="text/plain",
        status_code=200
    )

@app.route(route="wdac_bat", auth_level=func.AuthLevel.ANONYMOUS)
def download_wdac_bat(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Downloading WDAC Batch Wrapper.')
    
    script_content = r'''@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "Update-WDAC.ps1"
pause
'''
    return func.HttpResponse(
        script_content,
        mimetype="text/plain",
        status_code=200
    )

