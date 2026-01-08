# Smart Console Migration - Proof of Concept (PoC)

This folder contains the artifacts required to validate the "Pull" model (Queue Pattern) for the Check Point Smart Console migration to Azure.

## Architecture
1.  **Azure Cosmos DB:** Stores pending connection requests.
2.  **Azure Function (Python):** Acts as the broker API.
    *   `POST /api/queue_connection`: Simulates the Infinity Portal creating a request.
    *   `GET /api/fetch_connection`: Called by the Launcher to retrieve credentials.
3.  **PowerShell Launcher:** Runs on the client (AVD), polls the API, and launches the application.

**Current PoC behavior:** The launcher sets connection details into Windows environment variables and launches SmartConsole **without injecting anything into the UI**.

## Prerequisites
1.  **Azure Cosmos DB Account (NoSQL API):**
    *   Create a Database named: `S1C_Migration`
    *   Create a Container named: `ConnectionRequests`
    *   **Partition Key:** `/userId`
    *   **TTL (Time to Live):** Turn **On** (no default required, we set it per item, or set default to 60 seconds).

2.  **Azure Function App:**
    *   Runtime: Python 3.10+
    *   Environment Variables (Application Settings):
        *   `COSMOS_ENDPOINT`: Your Cosmos DB URI.
        *   `COSMOS_KEY`: Your Cosmos DB Primary Key.
        *   `COSMOS_DATABASE`: `S1C_Migration`
        *   `COSMOS_CONTAINER`: `ConnectionRequests`

## Components

### 1. Local Portal Simulator (`/LocalPortal`)
A Python Flask web application that simulates both the Infinity Portal UI and the Azure Backend API.
*   **Features:**
    *   Web Dashboard to view "Customers" and click "Connect".
    *   Live view of the "Connection Queue" (Pending vs Consumed).
    *   API endpoints for the Launcher.
*   **Run:**
    ```bash
    cd POC/LocalPortal
    pip install -r requirements.txt
    python3 app.py
    ```
    Then open `http://localhost:5001` in your browser.

**Portal authentication (PoC):** the portal requires Keycloak OIDC login.

**User mapping (PoC):** requests are queued under the logged-in user identity (derived from Keycloak claims like `email` / `upn`). For the end-to-end flow to work, this value must match the AVD session user returned by `whoami /upn`.

Configuration is loaded from `POC/LocalPortal/.env`.

Public repo hygiene:
- Commit the sample file `POC/LocalPortal/.env.example`.
- Do **not** commit your real `POC/LocalPortal/.env`.

Optional (preferred for this PoC): configure direct launch for a specific RemoteApp by setting:
- `AVD_DIRECT_REMOTEAPP_BASE_URL` (default: `https://windows.cloud.microsoft/webclient/avd`)
- `AVD_WORKSPACE_OBJECT_ID`
- `AVD_REMOTEAPP_OBJECT_ID`

#### AVD Web SSO behavior (important)

In practice, the AVD Web Client (`client.wvd.microsoft.com`) initiates sign-in via MSAL against the `login.microsoftonline.com/common` endpoint.
This can cause a username prompt even when passing `tenantId`/`login_hint` on the AVD URL.

**Working approach in this PoC:** after a successful queue request, the portal first performs an Entra “bootstrap” redirect (tenant-specific) to establish Microsoft session cookies, then forwards into the AVD web client.

Implementation note:
- The portal attempts a **silent bootstrap first** (`prompt=none`) to reduce the chance of seeing a Microsoft account picker.
- If Entra responds that user interaction is required, the portal automatically retries with an interactive bootstrap.

Configure these environment variables in `POC/LocalPortal/.env`:
- `ENTRA_TENANT_ID` (tenant GUID / Directory ID)
- `ENTRA_BOOTSTRAP_CLIENT_ID` (App Registration client ID for the bootstrap redirect)
- Optional: `ENTRA_BOOTSTRAP_REDIRECT_URI` (default: `http://localhost:5001/entra/callback`)

### 2. Azure Function (`/AzureFunction`) - *Optional for Local Test*
Contains the Python code for the real Azure deployment.
*   **Deploy:** Use VS Code Azure Functions extension or `func azure functionapp publish <APP_NAME>`.
*   **Local Run:** `func start`

### 3. AVD RemoteApp Launcher (Single Script: `Launcher.ps1`)

This is the intended PoC entry point for Azure Virtual Desktop.

- Publish a RemoteApp for:
    - `C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe`
- Command line example (current PoC): `-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\\SC1\\Launcher.ps1" -HoldSeconds 0`

Behavior:
- Fetches the pending request from `GET /api/fetch_connection?userId=<userId>`
- Writes connection info into environment variables (defaults):
    - `S1C_USERNAME`, `S1C_TARGET_IP`, `S1C_PASSWORD`
- Also writes the portal-provided session context into:
    - `APPSTREAM_SESSION_CONTEXT`
- Prints the values back *from the environment*
- Starts SmartConsole with **no args** (no UI injection)

Notes:
- `APPSTREAM_SESSION_CONTEXT` is entered in the Portal UI (per logged-in portal user session) and is passed through the broker payload.
- Credentials are set for the current process (so SmartConsole inherits them). You can also persist credentials to *User* scope using `-PersistUserEnv`.
- `APPSTREAM_SESSION_CONTEXT` is set for the current process (so SmartConsole inherits it).
- By default, `APPSTREAM_SESSION_CONTEXT` is also persisted **per-user** (HKCU) so each concurrent user can have a different value.
- By default, `APPSTREAM_SESSION_CONTEXT` is **not** persisted to *Machine/System* env vars, to avoid multiple concurrent users overwriting each other on the same AVD session host.
- If you explicitly want a host-wide System variable (shared by all users), run with `-PersistContextMachineEnv:$true` (requires admin rights, or a SYSTEM scheduled task).

If the launcher is not running as admin:
- The launcher cannot directly write Machine/System env vars.
- To still persist `APPSTREAM_SESSION_CONTEXT` as a System variable, install the SYSTEM Scheduled Task once (run on the AVD session host as Administrator):
    - `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\S1C\Install-S1CSetMachineEnvTask.ps1`
  The task runs as SYSTEM and applies the latest request file every minute.

## Updating the Azure Function (CLI)

When you change broker fields (for example adding `appstreamSessionContext`), you must redeploy the Function App.

From macOS:

1. Install prerequisites (one time):
    - Azure CLI: `brew install azure-cli`
    - Azure Functions Core Tools v4: `brew install azure-functions-core-tools@4`
2. Login:
    - `az login`
3. Publish:
    - `cd POC/AzureFunction`
    - `func azure functionapp publish <YOUR_FUNCTION_APP_NAME>`

Quick validation (after queueing a request):
- `curl "https://<your-function-app>.azurewebsites.net/api/fetch_connection?userId=<userIdUPNUrlEncoded>"`
- The JSON response should include `appstreamSessionContext`.

## Verifying APPSTREAM_SESSION_CONTEXT (Per-User vs System)

Recommended behavior for multi-user AVD hosts is **per-process** (always) and optionally **per-user** (with `-PersistUserEnv`).

1. Portal:
    - Login
    - Enter `APPSTREAM_SESSION_CONTEXT` (example: `1234`)
    - Click **Connect**

2. Broker:
    - Ensure the Azure Function is redeployed so `fetch_connection` returns `appstreamSessionContext`.

3. Verify as the same AVD user (cp1/cp2) in their session:
    - Process (what SmartConsole inherits):
        - `powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('APPSTREAM_SESSION_CONTEXT','Process')"`
    - User scope (default for context):
        - `powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('APPSTREAM_SESSION_CONTEXT','User')"`

4. Why localadmin doesn’t see it (and how to inspect anyway):
    - User-scoped env vars are stored under that user’s registry hive (HKCU). When you RDP as `localadmin`, HKCU is **localadmin’s** hive, not cp1’s.
    - If cp1 is currently logged on (so the hive is loaded), localadmin can inspect it via HKU + the user SID:
        - Find logged-on profiles/SIDs:
            - `powershell -NoProfile -Command "Get-CimInstance Win32_UserProfile | Select-Object LocalPath,SID"`
        - Then read the env var from HKU:
            - `reg query "HKU\<SID>\Environment" /v APPSTREAM_SESSION_CONTEXT`

Optional: System-wide (shared) persistence
- If you explicitly want a System variable (shared by all users), you can enable Machine persistence:
    - Run the launcher with `-PersistContextMachineEnv:$true`.
    - If the launcher is not running as admin, install the SYSTEM Scheduled Task once (run on the AVD session host as Administrator):
        - `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\S1C\Install-S1CSetMachineEnvTask.ps1`
      The task runs as SYSTEM and applies the latest request file every minute.

Troubleshooting tip:
- If the launcher log still shows the old warning about not having admin rights and never writes `C:\\ProgramData\\S1C\\machine-env-request.json`, you are likely running an older `C:\\SC1\\Launcher.ps1`.
- The updated launcher prints and logs `Launcher version:` and `Launcher path:` at startup so you can confirm you copied the right file.

### Legacy / Deprecated scripts

This PoC is intentionally kept to a single launcher script. Older runner/python experiments were removed.

## SSO / Federation PoC (Keycloak)

If you want to mimic “Infinity Portal uses some SAML IdP” and then federate Entra to that IdP (to reduce/avoid a second login prompt in AVD Web), see:

- [POC/Keycloak/README.md](POC/Keycloak/README.md)

Working end-to-end runbook (dated):
- [POC/SSO_FEDERATION_RUNBOOK.md](POC/SSO_FEDERATION_RUNBOOK.md)

## Testing the Flow (Local Portal Method)

1.  **Start the Portal:**
    *   Run `python3 POC/LocalPortal/app.py`.
    *   Open `http://localhost:5001`.
    *   You will see a list of customers (Acme, Globex, Soylent).

2.  **Queue a Request:**
    *   Click the **Connect** button for "Acme Corp".
    *   The page will refresh. Look at the "Backend Queue State" section.
    *   You should see a request with Status: **PENDING**.

3.  **Run the Launcher:**
    *   In AVD, launch the published RemoteApp (PowerShell) which runs `C:\\S1C\\Launcher.ps1`.
    *   The launcher will set environment variables and start SmartConsole.

4.  **Observe Results:**
    *   **PowerShell:** Should show `[SUCCESS] Connection request found.`.
    *   **SmartConsole:** Opens (no UI injection). Connection details are available via environment variables.
    *   **Troubleshooting:** If RemoteApp opens then closes immediately, verify the RemoteApp command line and that SmartConsole exists at the configured path.

### 4. Automation (Deprecated)

Legacy browser automation experiments were removed from this repo.
Use the portal’s SSO bootstrap helper flow described above.
