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

**User mapping (PoC):** the portal simulator can queue requests under a specific AVD Entra UPN using the `avdUserId` field in `CUSTOMERS`.

Optional (for demo): You can set `AVD_LAUNCH_URL` for the portal so clicking **Connect** redirects the browser to AVD Web.

### 2. Azure Function (`/AzureFunction`) - *Optional for Local Test*
Contains the Python code for the real Azure deployment.
*   **Deploy:** Use VS Code Azure Functions extension or `func azure functionapp publish <APP_NAME>`.
*   **Local Run:** `func start`

### 3. AVD RemoteApp Launcher (Single Script: `Launcher.ps1`)

This is the intended PoC entry point for Azure Virtual Desktop.

- Publish a RemoteApp for:
    - `C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe`
    - Command line: `-NoProfile -ExecutionPolicy Bypass -File C:\\S1C\\Launcher.ps1`

Behavior:
- Fetches the pending request from `GET /api/fetch_connection?userId=<userId>`
- Writes connection info into environment variables (defaults):
    - `S1C_USERNAME`, `S1C_TARGET_IP`, `S1C_PASSWORD`
- Prints the values back *from the environment*
- Starts SmartConsole with **no args** (no UI injection)

### Legacy / Deprecated scripts

This PoC is intentionally kept to a single launcher script. Older runner/python experiments were removed.

## SSO / Federation PoC (Keycloak)

If you want to mimic “Infinity Portal uses some SAML IdP” and then federate Entra to that IdP (to reduce/avoid a second login prompt in AVD Web), see:

- [POC/Keycloak/README.md](POC/Keycloak/README.md)

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
