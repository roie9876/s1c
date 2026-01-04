# GitHub Copilot Instructions for Check Point Migration Project

This repository contains the code and documentation for migrating the Check Point Farm and Smart Console access from AWS to Azure.

## Project Context
*   **Goal:** Migrate from AWS AppStream to Azure Virtual Desktop (AVD).
*   **Core Problem:** AVD cannot accept sensitive context (credentials) in the URL like AWS AppStream.
*   **Solution:** We are implementing a "Pull" model where the client (AVD) fetches credentials from a backend queue (Azure Functions + Cosmos DB).

## Tech Stack
*   **Backend:** Azure Functions (Python v2 model), Azure Cosmos DB (NoSQL).
*   **Frontend/Simulation:** Python Flask (for the Local Portal simulator).
*   **Client:** PowerShell (running on Windows AVD session).
*   **Infrastructure:** Azure Bicep / Terraform (future).

## Coding Guidelines

### Azure Functions (Python)
*   Use the **Python v2 programming model** (decorators).
*   Use `azure-functions` and `azure-cosmos` libraries.
*   Ensure proper error handling and logging.
*   Cosmos DB interactions should use the `ContainerProxy` for operations.

### PowerShell (Launcher)
*   Scripts run in the user context on the AVD VM.
*   Use `Invoke-RestMethod` for API calls.
*   Handle potential errors when calling the backend (e.g., network issues, no pending request).
*   Security: Avoid logging sensitive credentials to the console.

### General
*   **Terminology:**
    *   "Infinity Portal": The existing web portal (AWS).
    *   "Launcher": The script/app running in AVD that fetches credentials.
    *   "Broker": The Azure Function + Cosmos DB backend.
*   **Migration Plan:** Always refer to `MIGRATION_PLAN.md` for architectural decisions.

## Specific Rules
*   When generating code for the Azure Function, assume the Cosmos DB container has a partition key of `/userId`.
*   When generating PowerShell code, assume it runs on Windows 10/11 Enterprise Multi-session.
*   The "Pull" model relies on a short-lived TTL (Time To Live) in Cosmos DB (e.g., 60 seconds).
