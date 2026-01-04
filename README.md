# Check Point Farm & Smart Console Access Migration (AWS to Azure)

This repository contains the Proof of Concept (PoC) and documentation for migrating the Check Point "Farm" environment and Smart Console access from AWS AppStream to Azure Virtual Desktop (AVD).

## Project Overview

The goal is to migrate the existing AWS-based infrastructure to Azure, replacing the "Push" model used by AWS AppStream with a "Pull" model suitable for Azure Virtual Desktop.

*   **Source:** AWS (AppStream 2.0, EC2)
*   **Destination:** Azure (AVD, Azure Functions, Cosmos DB)
*   **Key Challenge:** AVD does not support passing sensitive context (credentials) via the URL like AppStream does.
*   **Solution:** A "Connection Request Queue" pattern using Azure Functions and Cosmos DB.

## Repository Structure

*   **[MIGRATION_PLAN.md](MIGRATION_PLAN.md)**: Detailed architectural analysis, migration strategy, and technical specifications.
*   **[POC/](POC/)**: Proof of Concept implementation code.
    *   **[POC/AzureFunction/](POC/AzureFunction/)**: Azure Functions (Python) acting as the broker API.
    *   **[POC/LocalPortal/](POC/LocalPortal/)**: A local simulator for the Infinity Portal to test the flow.
    *   **[POC/Launcher.ps1](POC/Launcher.ps1)**: PowerShell script simulating the client-side launcher in AVD.
*   **[aws screnshots/](aws%20screnshots/)**: Reference images of the current AWS environment.

## Getting Started

1.  Review the **[Migration Plan](MIGRATION_PLAN.md)** to understand the architecture.
2.  Navigate to the **[POC](POC/)** folder to explore the code and run the local simulation.

## Key Technologies

*   **Azure Virtual Desktop (AVD)**
*   **Azure Functions (Python)**
*   **Azure Cosmos DB**
*   **PowerShell**
*   **Python (Flask for simulation)**

## Contributing

Please refer to the migration plan for architectural decisions and the POC README for running the code locally.
