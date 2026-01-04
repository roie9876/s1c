# PoC Tracking & Handoff Document

This document tracks the state of the Check Point Farm Migration PoC. Use this to resume work in future Copilot sessions.

## Project Context
*   **Goal:** Migrate from AWS AppStream to Azure Virtual Desktop (AVD) using a "Pull" model for credential handling.
*   **Architecture:**
    *   **Portal (Source):** Pushes connection context (IP, User, Pass) to Azure Backend.
    *   **Azure Backend:** Azure Functions + Cosmos DB (stores context with 60s TTL).
    *   **Launcher (Client):** PowerShell script on AVD that polls the backend and launches the app.

## Current Infrastructure State (As of Jan 4, 2026)
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
| **Azure Function** | ✅ Deployed | Python v2 model. Endpoints: `/queue_connection`, `/fetch_connection`. |
| **Cosmos DB** | ✅ Active | TTL enabled (60s). Partition Key: `/userId`. |
| **Launcher.ps1** | ⚠️ Ready to Test | Updated with Prod URL. Needs validation in actual AVD or simulated env. |
| **Local Portal** | ✅ Fixed | Flask App. **Issue:** Port 5000/8080 conflict. Moving to port 5001. |
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

## Immediate Next Steps
1.  **Verify SmartConsole Launch:** Download the updated script in AVD and run it.
2.  **Security Hardening:** Implement authentication for the Azure Function (currently Anonymous).
    *   **AVD:** Copy `Launcher.ps1` to VM and run it.
    *   **Verify:** Notepad opens with the correct IP/User.
    *   Run Launcher (Local PowerShell).
    *   Verify "Connect" click -> Cosmos DB entry -> Launcher retrieval.
3.  **Refinement:** Add better error handling to `Launcher.ps1` if the backend is down.

## Environment Variables / Secrets
*   **Function App:** Managed Identity / Key based auth (currently anonymous/function level for PoC).
*   **Local Portal:** No secrets required (public endpoint for PoC).
