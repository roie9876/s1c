# PoC Tracking & Handoff Document

This document tracks the state of the Check Point Farm Migration PoC. Use this to resume work in future Copilot sessions.

## Project Context
*   **Goal:** Migrate from AWS AppStream to Azure Virtual Desktop (AVD) using a "Pull" model for credential handling.
*   **Architecture:**
    *   **Portal (Source):** Pushes connection context (IP, User, Pass) to Azure Backend.
    *   **Azure Backend:** Azure Functions + Cosmos DB (stores context with 60s TTL).
    *   **Launcher (Client):** PowerShell script on AVD that polls the backend and launches the app.

## Current Infrastructure State (As of Jan 5, 2026)
*   **Subscription:** Pay-As-You-Go
*   **Region:** East US 2 (`eastus2`)
*   **Resource Group:** `s1c-poc-rg`
*   **Azure Function:** `s1c-function-11729`
    *   URL: `https://s1c-function-11729.azurewebsites.net/api`
*   **Cosmos DB:** `s1c-cosmos-11729`
    *   Database: `s1c-db`
    *   Container: `connections`

## Component Status

| Component | Status | Notes |
| :--- | :--- | :--- |
| **Azure Function** | ✅ Deployed | Python v2 model. Endpoints: `/queue_connection`, `/fetch_connection`, `/dl` (serves Launcher). |
| **Cosmos DB** | ✅ Active | TTL enabled (60s). Partition Key: `/userId`. |
| **Launcher (single script)** | ✅ Updated | `C:\S1C\Launcher.ps1` fetches a pending request, sets env vars (`S1C_USERNAME`/`S1C_TARGET_IP`/`S1C_PASSWORD`), prints them, and launches SmartConsole with **no args** (no UI injection). Keeps RemoteApp alive by waiting for SmartConsole to exit. |
| **Local Portal** | ✅ Fixed | Flask App running on port **5001**. Includes PoC user mapping via `avdUserId`. |
| **AVD Environment** | ✅ Verified | Clipboard fixed. **End-to-End Test Passed:** Launcher retrieved context and started app. |

## Recent Actions
1.  Provisioned Azure Resources in `eastus2`.
2.  Deployed Azure Function code.
3.  Updated `Launcher.ps1` to use the live Azure Function URL.
4.  Updated `LocalPortal/app.py` to send real POST requests to Azure.
5.  Updated `LocalPortal/templates/index.html` with a proper UI (Flash messages, History).
6.  Changed Local Portal port to **5001** to avoid 403 errors.
7.  Updated `LocalPortal/app.py` to handle HTTP 201 responses from Azure.
8.  Added `/dl` endpoint to Azure Function for easy script download.
9.  **Verified End-to-End Flow:** Portal -> Azure -> AVD -> Launcher -> App Launch.
10. **Updated Launcher:** Switched to `SmartConsole.exe` (R82 path).
11. **Recovered & Redeployed Function App:** Restored clean `function_app.py` and confirmed `/api/dl` returns the script (HTTP 200).
12. **Changed Login Flow:** Auto-login was dropped; password is typed manually in SmartConsole.
13. **RemoteApp Bootstrapper:** Publish `powershell.exe` RemoteApp to run `C:\sc1\LuancherRunner.ps1` which downloads `/api/dl`.
14. **Anti-caching fixes:** `/api/dl` adds `Cache-Control: no-store` and runner uses `?nocache=<guid>`.
15. **RemoteApp stability fix:** Launcher now waits for SmartConsole process to exit (prevents RemoteApp session from ending immediately).
16. **Persistent logs added:** See “Troubleshooting & Logs” below.

## RemoteApp Configuration (Known-Good)

Create an AVD RemoteApp (Application Group → Applications → Add) with:

- **Application source:** File path
- **Application path:** `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`
- **Require command line:** Yes
- **Command line:** `-NoProfile -ExecutionPolicy Bypass -File "C:\S1C\Launcher.ps1"`
- **Icon path (optional):** `C:\Program Files (x86)\CheckPoint\SmartConsole\R82\PROGRAM\SmartConsole.exe` (Icon index 0)

Notes:
- Ensure `C:\S1C\Launcher.ps1` exists on the session host image.
- For troubleshooting, temporarily add: `-NoExit` and `Read-Host` to keep the window open.
- The published app must remain alive; the launcher waits for SmartConsole to exit.

## Troubleshooting & Logs

Common causes of “PowerShell opens then closes”:

1. Wrong file path/typo in RemoteApp command line (PowerShell exits immediately).
2. `C:\S1C\Launcher.ps1` missing on the session host.
3. SmartConsole missing at the configured path.
4. No pending request for the detected userId.

## Immediate Next Steps
1.  **AVD RemoteApp Launch:** Publish a RemoteApp that runs the Launcher automatically (no manual download/run).
2.  **Identity Alignment:** Confirm the `userId` used by the portal equals the AVD user's Entra UPN.
    *   For PoC: use the same email address (Infinity Portal “working email”) as the Entra UPN.
    *   If they differ: add a mapping step (Portal stores “AVD UPN” alongside the Portal email and queues requests using the AVD UPN).
3.  **Security Tightening:** Remove password from the queued payload (since password is manual now) and add auth to the Function endpoints.
4.  **Launcher Robustness:** Improve retries/backoff and add clearer user messaging when no request is pending.
5.  **Profile persistence:** Plan FSLogix profile containers so SmartConsole state persists for pooled host pools.

## Environment Variables / Secrets
*   **Function App:** Managed Identity / Key based auth (currently anonymous/function level for PoC).
*   **Local Portal:** No secrets required (public endpoint for PoC).
