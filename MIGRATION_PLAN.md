# Migration Project: Check Point Farm & Smart Console Access (AWS to Azure)

## 1. Project Overview
This document outlines the architecture and migration strategy for moving the Check Point "Farm" environment and the Smart Console access mechanism from Amazon Web Services (AWS) to Microsoft Azure. 

**Scope:**
*   **Source:** AWS (Current "Farm" and VDI access).
*   **Destination:** Azure.
*   **Out of Scope:** Check Point Infinity Portal (will remain in AWS).

## 2. Current Architecture (AWS)

### Components
1.  **Infinity Portal (AWS)**
    *   **Role:** User registration, authentication, and account management.
    *   **Function:** Acts as the entry point. Users select the specific Check Point Management Server they wish to manage.
    *   **Data:** Stores mapping of User -> Management Server (IP, Credentials).

2.  **The Farm (AWS)**
    *   **Infrastructure:** Amazon EC2 Instances.
    *   **Role:** Hosts Check Point Management Servers.
    *   **Tenancy:** 
        *   Single-tenant for normal customers.
        *   Multi-tenant/Multiple servers for MSP/MSSP customers.

3.  **Access Layer (AWS AppStream / Workspaces)**
    *   **Infrastructure:** AWS VDI Service (AppStream 2.0 or Workspaces).
    *   **OS:** Windows.
    *   **Software:** 
        *   Check Point Smart Console.
        *   Custom Decryption/Helper App.
    *   **Flow:** Delivers the Smart Console application UI to the user's browser or client.

### Current Workflow
1.  **User Action:** User logs into Infinity Portal and selects a Management Server to connect to.
2.  **Payload Generation:** Infinity Portal retrieves the target Management Server details (IP, Username, Password).
3.  **Encryption:** These details are encrypted.
4.  **Handoff:** The encrypted payload is passed to the AWS VDI service (AppStream).
5.  **Session Start:** A Windows session starts.
6.  **Decryption:** The custom helper app inside the Windows session receives the encrypted payload, decrypts it to clear text.
7.  **Auto-Login:** The helper app launches Smart Console and injects the credentials/IP.
8.  **Result:** User sees the Smart Console connected to their specific Management Server without typing credentials.

---

## 3. Proposed Architecture (Azure)

### Service Mapping

| Component | AWS Service (Current) | Azure Service (Target) | Notes |
| :--- | :--- | :--- | :--- |
| **Management Servers** | Amazon EC2 | **Azure Virtual Machines** | Host the Check Point Management Servers (Gaia OS). |
| **VDI / App Streaming** | AWS AppStream / Workspaces | **Azure Virtual Desktop (AVD)** | Supports RemoteApp (streaming just the app) or Full Desktop. |
| **Identity/Auth** | Custom / AWS IAM | **Entra ID (Azure AD)** | Potential to integrate for RBAC, though Infinity Portal handles primary auth. |
| **Network** | AWS VPC | **Azure VNet** | |

### Detailed Azure Workflow

1.  **The Farm (Azure VMs)**
    *   Deploy Check Point Management Servers as Azure VMs.
    *   Use **Azure Scale Sets** if dynamic scaling of the farm is required, or managed Availability Sets for persistence.
    *   **Storage:** Managed Disks (Premium SSD recommended for database performance).

2.  **Access Layer (Azure Virtual Desktop - AVD)**
    *   **Host Pool:** Create a Windows 10/11 Multi-session host pool to serve Smart Console.
    *   **RemoteApp:** Publish "Check Point Smart Console" as a RemoteApp (instead of full desktop) for a seamless experience similar to AppStream.
    *   **Custom Wrapper:** The "Helper App" will need to be deployed on these AVD hosts.

3.  **Connectivity (AWS <-> Azure)**
    *   Since Infinity Portal stays in AWS, we need a secure channel to trigger the Azure session.
    *   **Option A (VPN/ExpressRoute):** Site-to-Site VPN between AWS VPC and Azure VNet to allow direct communication if needed.
    *   **Option B (Public API):** Infinity Portal calls an Azure Function or Logic App via HTTPS to request a session.

## 4. Key Challenges & Solutions

### Challenge 1: Passing Encrypted Credentials to Azure AVD
**The Issue:** AWS AppStream has specific mechanisms to pass context. We need an equivalent in Azure to pass the `User, Pass, IP` payload from the web browser (Infinity Portal) to the AVD session.

**Proposed Solution:**
*   **AVD URI Scheme / RDP Properties:** 
    *   Azure Virtual Desktop supports launching resources via URI.
    *   However, passing sensitive arguments (passwords) directly in a URI is insecure.
*   **Intermediate Store (Token Pattern):**
    1.  Infinity Portal generates a one-time **Session Token**.
    2.  Infinity Portal saves the encrypted credentials in a temporary secure store (e.g., **Azure Key Vault** or a secured **Redis Cache** in Azure) keyed by this Token.
    3.  Infinity Portal launches the AVD Web Client (or desktop client) passing only the `Session Token` as a command-line argument to the RemoteApp.
    4.  **Inside AVD:** The Helper App starts, reads the `Session Token` from the command line arguments.
    5.  The Helper App calls an internal API (or Key Vault) to retrieve the actual `User, Pass, IP` using the token.
    6.  Helper App decrypts/uses info to launch Smart Console.

### Challenge 2: Latency
**The Issue:** The Management Server is in Azure, the Smart Console (AVD) is in Azure, but the User is remote.
**Solution:** 
*   Ensure AVD Host Pool and Management VM Farm are in the **same Azure Region** (e.g., East US) to minimize console-to-server latency.
*   Use **AVD RDP Shortpath** to optimize the UDP connection from the user's home/office to the Azure VDI.

### Challenge 3: Automation & Orchestration
**The Issue:** Creating new Management Servers for new customers automatically.
**Solution:**
*   Use **Terraform** or **Bicep** to define the Management Server VM template.
*   Trigger deployment via **Azure Functions** when a new customer signs up in Infinity Portal.

