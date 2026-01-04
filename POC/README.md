# Smart Console Migration - Proof of Concept (PoC)

This folder contains the artifacts required to validate the "Pull" model (Queue Pattern) for the Check Point Smart Console migration to Azure.

## Architecture
1.  **Azure Cosmos DB:** Stores pending connection requests.
2.  **Azure Function (Python):** Acts as the broker API.
    *   `POST /api/queue_connection`: Simulates the Infinity Portal creating a request.
    *   `GET /api/fetch_connection`: Called by the Launcher to retrieve credentials.
3.  **PowerShell Launcher:** Runs on the client (AVD), polls the API, and launches the application.

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
    Then open `http://localhost:5000` in your browser.

### 2. Azure Function (`/AzureFunction`) - *Optional for Local Test*
Contains the Python code for the real Azure deployment.
*   **Deploy:** Use VS Code Azure Functions extension or `func azure functionapp publish <APP_NAME>`.
*   **Local Run:** `func start`

### 3. Launcher Script (`Launcher.ps1`)
The client-side script to be run on the AVD VM (or your local machine for testing).
*   **Configuration:** Edit the `$ApiUrl` variable in the script to point to your API (default is `http://localhost:5000/api`).
*   **Usage:** `.\Launcher.ps1`

## Testing the Flow (Local Portal Method)

1.  **Start the Portal:**
    *   Run `python3 POC/LocalPortal/app.py`.
    *   Open `http://localhost:5000`.
    *   You will see a list of customers (Acme, Globex, Soylent).

2.  **Queue a Request:**
    *   Click the **Connect** button for "Acme Corp".
    *   The page will refresh. Look at the "Backend Queue State" section.
    *   You should see a request with Status: **PENDING**.

3.  **Run the Launcher:**
    *   Open PowerShell.
    *   Run `.\POC\Launcher.ps1 -OverrideUser "roie@mssp.com"`.
    *   *Note:* We use `-OverrideUser` because the Local Portal hardcodes the user to `roie@mssp.com` for simplicity.

4.  **Observe Results:**
    *   **PowerShell:** Should say `[SUCCESS] Connection Request Found!` and launch Notepad.
    *   **Browser:** Refresh the page. The status in the Queue table should change to **CONSUMED** (Green).
