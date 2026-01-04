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
            
            # Method 4: Start-Process with Single String Arguments (Best for Legacy Apps)
            # We construct the argument string manually to ensure quotes are preserved exactly as expected.
            $ArgString = "-p `"$Password`" -u `"$Username`" -s `"$TargetIp`""
            
            Write-Host "[DEBUG] Arguments: $ArgString" -ForegroundColor Cyan
            Write-Host "[ACTION] Launching SmartConsole..." -ForegroundColor Green
            
            try {
                Push-Location $SmartConsoleDir
                
                # Use Start-Process with a single string argument list
                $Process = Start-Process -FilePath ".\SmartConsole.exe" -ArgumentList $ArgString -PassThru
                
                # Wait to see if it crashes
                Start-Sleep -Seconds 5
                
                if ($Process.HasExited) {
                    Write-Host "[ERROR] Process exited immediately (Code: $($Process.ExitCode))." -ForegroundColor Red
                    Write-Host "Troubleshooting:" -ForegroundColor Yellow
                    Write-Host "1. Copy and run this command in CMD to test:" -ForegroundColor White
                    Write-Host "   `"$SmartConsolePath`" $ArgString" -ForegroundColor White
                } else {
                    Write-Host "[SUCCESS] SmartConsole is running (PID: $($Process.Id))." -ForegroundColor Green
                }
                
                Pop-Location
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
