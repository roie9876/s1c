# Smart Console Migration - Proof of Concept (PoC)

This folder contains the artifacts required to validate the "Pull" model (Queue Pattern) for the Check Point Smart Console migration to Azure.

## Architecture
1.  **Azure Cosmos DB:** Stores pending connection requests.
2.  **Azure Function (Python):** Acts as the broker API.
    *   `POST /api/queue_connection`: Simulates the Infinity Portal creating a request.
    *   `GET /api/fetch_connection`: Called by the Launcher to retrieve credentials.
    *   `GET /api/dl`: Serves the latest launcher PowerShell script.
3.  **PowerShell Launcher:** Runs on the client (AVD), polls the API, and launches the application.

**Current PoC behavior:** SmartConsole is launched and the login UI is pre-filled (username + server/IP). The user types the password manually.

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

### 2. Azure Function (`/AzureFunction`) - *Optional for Local Test*
Contains the Python code for the real Azure deployment.
*   **Deploy:** Use VS Code Azure Functions extension or `func azure functionapp publish <APP_NAME>`.
*   **Local Run:** `func start`

### 3. AVD RemoteApp Bootstrapper (`LauncherRunner.ps1`)

This is the intended PoC entry point for Azure Virtual Desktop.

- Publish a RemoteApp for:
    - `C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe`
    - Command line (current VM image): `-NoProfile -ExecutionPolicy Bypass -Command "& 'C:\\sc1\\LuancherRunner.ps1'"`

- Alternative (recommended if the PowerShell window has keyboard/input issues):
    - `C:\\Windows\\System32\\cmd.exe`
    - Command line: `/c C:\\S1C\\LauncherRunner.cmd`
- The runner downloads the latest launcher from `GET /api/dl` into `%TEMP%\\s1c-launcher\\Launcher.ps1` and runs it.

Logs on the session host:

- `%TEMP%\\s1c-launcher\\LauncherRunner.log`
- `%TEMP%\\s1c-launcher\\Launcher.log`

### 4. Legacy Launcher (`Launcher.ps1`)

`POC/Launcher.ps1` contains older experiments (auto-login attempts). It is not the current PoC path.

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
    *   In AVD, launch the published RemoteApp (PowerShell) which runs `C:\\S1C\\LauncherRunner.ps1`.
    *   The runner will download the latest launcher from the Azure Function and start SmartConsole.

4.  **Observe Results:**
    *   **PowerShell/Logs:** Should show `[SUCCESS] Connection Request Found!`.
    *   **SmartConsole:** Opens and pre-fills username + server/IP; user types password manually.
    *   **Troubleshooting:** If RemoteApp opens then closes immediately, check:
        *   `C:\\S1C\\LauncherRunner.ps1` exists on the session host.
        *   `%TEMP%\\s1c-launcher\\LauncherRunner.log` and `%TEMP%\\s1c-launcher\\Launcher.log`.
