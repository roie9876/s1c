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

### 2.1 AWS Environment Artifacts & User Experience
**Observed URL Structure (AppStream):**
The connection process involves a URL transition:

**Phase 1: Reservation (`#/reserve`)**
Initial request to reserve a session instance.
```
https://63a5b2f67a09659106a68182d383d8645f3ccda0e1cf7b76689df1d7.appstream2.us-east-1.aws.amazon.com/#/reserve
?app=SmartConsole
&reference=fleet%2FSmartConsoleR82-TF
&context=o9tGeBss6rykoTPx%2BaPyuJyQJGRdX1MmhvgRbTObQ4%2FLzqLqPMoLjE%2B7%2Fkk6YuZ7cVwT%2BDFgoqTLFXGThZ5yRqjyi%2BSqUVJnY6GNkHGRt5fHoCYxPVp962Z0dyD8w2S0xRF9d4AZ%2Ba%2Bs2779sScYJk4ipQ5AeJyGdTxHEnx176VrcJlkag6rpm97SSezrFwdpqs%2BNBBVZxaOh5c31SoTTGmojvGYvMquRcpdyL5Yb1k%3D
```

**Phase 2: Streaming (`#/streaming`)**
Once reserved, the URL changes to the active streaming session.
```
https://63a5b2f67a09659106a68182d383d8645f3ccda0e1cf7b76689df1d7.appstream2.us-east-1.aws.amazon.com/#/streaming
?reference=fleet%2FSmartConsoleR82-TF
&app=SmartConsole
&context=o9tGeBss6rykoTPx%2BaPyuJyQJGRdX1MmhvgRbTObQ4%2FLzqLqPMoLjE%2B7%2Fkk6YuZ7cVwT%2BDFgoqTLFXGThZ5yRqjyi%2BSqUVJnY6GNkHGRt5fHoCYxPVp962Z0dyD8w2S0xRF9d4AZ%2Ba%2Bs2779sScYJk4ipQ5AeJyGdTxHEnx176UCrnimIe9Xzlk7aqFB8rlc2JYYHZE2uK18NoFYBg88xhpTrhyfMOc6JSo6zODaGH4%3D
```
*   **Domain:** `appstream2.us-east-1.aws.amazon.com` (Confirming AWS AppStream 2.0).
*   **Fleet:** `SmartConsoleR82-TF` (Indicates the image/fleet name).
*   **Context:** The large encrypted string containing the session credentials.

**Visual State (Screenshots):**
> *Note: Screenshots are referenced here. Please upload the image files to the repository to view them.*

1.  **Infinity Portal Dashboard:** Shows the "Smart-1 Cloud" service with an "Open" button.
    ![Infinity Portal Dashboard](./aws%20screnshots/s1c-image1.png)

2.  **Service Page:** Displays "Open Web SmartConsole" and "Open Streamed SmartConsole".
    *   Also shows "SmartConsole connection token" (e.g., `roie9876-dejucj4n/c4b83f3f...`).
    ![Service Page](./aws%20screnshots/s1c-image2.png)

3.  **AppStream Loading:** Browser redirects to the AWS AppStream URL, showing the "SmartConsole R82" splash screen and "Connecting to Smart-1 Cloud" with the user identifier.
    ![AppStream Loading](./aws%20screnshots/s1c-image3.png)

4.  **Smart Console UI:** The full Windows application running inside the browser window.
    ![Smart Console UI](./aws%20screnshots/s1c-image4.png)

### 2.2 Technical Analysis of AWS AppStream Flow
Based on the observed URL transitions, the AWS solution functions as follows:

1.  **The "Push" Mechanism:**
    *   The presence of the `&context=` parameter confirms that the sensitive session data (User, Password, Target IP) is **pushed** from the client browser to the AppStream instance via the URL.
    *   The string is Base64 encoded (ending in `%3D` -> `=`) and encrypted.

2.  **Session Lifecycle (Reserve -> Stream):**
    *   **Step 1: Reservation (`#/reserve`):** The browser requests a session. The `context` here likely acts as a "Reservation Ticket" containing the user's intent.
    *   **Step 2: Streaming (`#/streaming`):** Once the instance is ready, the URL updates. The `context` string **changes** at this stage. This suggests a token rotation or a handshake where the "Reservation Ticket" is exchanged for a "Session Ticket".

3.  **Implications for Azure:**
    *   This "Context-in-URL" pattern is specific to AWS AppStream's capability to pass custom parameters to the instance.
    *   **Azure Virtual Desktop (AVD) Web Client does NOT support this.** We cannot pass a `&context=` parameter in the AVD URL.
    *   **Conclusion:** We must abandon the "Push" model and implement the **"Pull" model** (described in Section 4), where the application fetches its configuration from the backend after launch.

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

### Challenge 1: Passing Encrypted Credentials (The "Seamless Pull" Model)

**The Issue:** 
The current AWS AppStream flow is seamless: the user clicks "Connect" and the app opens.
The "Dynamic RDP File" method (Challenge 1 above) requires the user to download and open a file, which is a degraded user experience.
Furthermore, the AVD Web Client (HTML5) does **not** support passing dynamic arguments in the URL.

**Proposed Solution: The "Context Store" Pattern (Pull Model)**
Instead of *pushing* the credentials to the app via the connection string, the app will *pull* them from a secure backend based on the user's identity.

**The Workflow:**
1.  **User Action:** User clicks "Connect" in the Infinity Portal.
2.  **Context Staging:** 
    *   Infinity Portal generates a "Connection Context" (Target IP, User, Pass).
    *   It saves this context to a secure database (e.g., Azure Redis / Cosmos DB) keyed by the **User's Email/UPN**.
    *   *Key:* `user@company.com` -> *Value:* `{ "target_ip": "1.2.3.4", "creds": "..." }`
3.  **Deep Link Launch:** 
    *   Infinity Portal redirects the user's browser to the **AVD Web Client Deep Link**:
    *   `https://windows.cloud.microsoft/webclient/avd/<WorkspaceID>/<ResourceID>`
4.  **Seamless Sign-On:** 
    *   Since the user is already authenticated with Azure AD (Entra ID), the AVD Web Client logs them in automatically (SSO).
5.  **App Start:** 
    *   The "Helper App" starts on the Azure VM.
6.  **Identity Check:** 
    *   The Helper App checks "Who am I?" (e.g., `whoami /upn`).
    *   It retrieves the logged-in user's email (e.g., `user@company.com`).
7.  **Context Retrieval (The Pull):** 
    *   The Helper App calls the Infinity Portal API (or the secure DB directly): "I am `user@company.com`, what is my connection target?"
    *   The API returns the encrypted payload.
8.  **Connection:** 
    *   Helper App decrypts the payload and launches Smart Console.

**Benefits:**
*   **Zero Clicks:** User clicks once in the portal, and the app opens. No file downloads.
*   **Secure:** Credentials are never passed through the client-side browser URL or RDP file.
*   **Standard:** Uses standard AVD Web Client features without hacks.

**Requirements:**
*   **Identity Sync:** The user email in Infinity Portal must match the Azure AD UPN used for AVD.
*   **API Access:** The Azure VM needs network access to the Infinity Portal API (or the Context Store).

## 5. User Experience Validation (Based on Smart-1 Cloud)

**Current Experience (AWS):**
*   **Interface:** The user sees the Smart Console UI directly inside their web browser (as shown in your screenshot).
*   **URL Structure:** `https://portal.checkpoint.com/dashboard/security-management#/mgmt/<MANAGEMENT_ID>/policy`
*   **Mechanism:** This confirms the use of **AppStream 2.0 Web Client** (or similar HTML5 VDI client) which embeds the Windows application into the browser.

**Target Experience (Azure):**
*   **Goal:** Replicate this exact "App-in-Browser" feel.
*   **Technology:** **Azure Virtual Desktop (AVD) Web Client**.
*   **Flow:**
    1.  User navigates to the Portal URL.
    2.  Portal renders the AVD Web Client iframe or redirects to the AVD Web Client URL.
    3.  **Deep Linking:** The URL `.../mgmt/<MANAGEMENT_ID>` will be the trigger.
    4.  **Context Lookup:** The `<MANAGEMENT_ID>` (e.g., `ifmRJurBAnvXSDfVUwXyv8`) is the key used by the Helper App to fetch the correct IP/Credentials from the backend.

## 6. Account Context & Entry Point Analysis

**New Discovery:**
*   **Unique Login URL:** `https://portal.checkpoint.com/signin/cp/<SHORT_ID>` (e.g., `c4b83f3f`)
*   **Account ID:** Full GUID (e.g., `c4b83f3f-b864-4c83-ad62-5df7deb98146`)

**Architectural Significance:**
This URL acts as the **Tenant Resolver**.
1.  **Entry:** User hits the Unique Login URL.
2.  **Resolution:** Infinity Portal resolves `<SHORT_ID>` to the full **Account ID**.
3.  **Routing:** The Portal knows which "Farm" (AWS or Azure) this account belongs to.
4.  **Migration Strategy:**
    *   This URL remains hosted in AWS (Infinity Portal).
    *   **Routing Logic Update:** The Infinity Portal's backend logic must be updated to check a flag: `is_migrated_to_azure`.
    *   **If False (AWS):** Continue existing flow (AppStream).
    *   **If True (Azure):** Redirect user to the **AVD Web Client** URL instead of the AppStream URL.

**Updated User Journey:**
1.  User clicks `https://portal.checkpoint.com/signin/cp/c4b83f3f`
2.  Infinity Portal authenticates user.
3.  Portal checks DB: "Where is Account `c4b83f3f` hosted?" -> **Answer: Azure**.
4.  Portal generates "Connection Context" (User/Pass/IP) and saves to Secure DB.
5.  Portal redirects browser to: `https://windows.cloud.microsoft/webclient/...`
6.  AVD Session starts -> Helper App pulls context -> Smart Console launches.

## 7. Deep Dive: The "Connection Token" & AppStream URL Analysis

**New Discovery:**
*   **Connection Token Format:** `ServiceIdentifier/AccountID/PortalDomain`
    *   Example: `roie9876-dejucj4n/c4b83f3f-b864-4c83-ad62-5df7deb98146/portal.checkpoint.com`
*   **AppStream URL Structure:**
    *   `https://...appstream2.us-east-1.aws.amazon.com/#/streaming`
    *   `?reference=fleet%2FSmartConsoleR82-TF` (Identifies the Fleet/Image)
    *   `&app=SmartConsole` (Identifies the Application)
    *   `&context=...` (A massive encrypted string!)

**Analysis of the AWS "Context" Parameter:**
The `&context=` parameter in the URL is exactly what we suspected. It contains the encrypted payload (User, Pass, IP, Token) that the AppStream instance receives.
*   **AWS Mechanism:** AppStream passes this `context` string to the instance. A script on the instance reads it, decrypts it, and logs the user in.

**Azure Equivalent Strategy (Refined):**
Since AVD Web Client **does not** support a `&context=` parameter in the URL (as confirmed in Challenge 1), we **cannot** simply copy-paste this URL structure.

**The "Pull" Model is Mandatory:**
1.  **Infinity Portal** will generate the same "Connection Token" (`roie9876...`).
2.  Instead of putting it in the URL, it saves it to the **Backend Database** linked to the User's Identity.
3.  **Redirect:** Portal redirects user to `https://windows.cloud.microsoft/webclient/...` (No context string).
4.  **Execution:**
    *   AVD Session starts.
    *   Helper App runs `whoami` -> gets `user@company.com`.
    *   Helper App calls Backend: "Get my Connection Token".
    *   Backend returns: `roie9876-dejucj4n/c4b83f3f...`
    *   Helper App parses this token to find the Management Server IP and credentials.
    *   Helper App launches Smart Console.

## 10. Context Store Technology Selection (Key Vault vs. Redis)

**Option A: Azure Key Vault**
*   **Mechanism:**
    *   Portal writes a Secret: `Name: Session-Roie`, `Value: {EncryptedContext}`.
    *   AVD reads Secret `Session-Roie`.
*   **Pros:** Highly secure, built-in encryption.
*   **Cons (Scale):** Key Vault has **throttling limits** (e.g., 2,000 requests/10 seconds). If 5,000 users log in at 9:00 AM, it will fail. It is designed for *static* secrets, not high-frequency dynamic data.

**Option B: Azure Redis Cache (Recommended)**
*   **Mechanism:**
    *   Portal writes Key: `Session:Roie`, Value: `{EncryptedContext}`, TTL: 60s.
    *   AVD reads Key.
*   **Pros:**
    *   **Speed:** Sub-millisecond latency.
    *   **Scale:** Handles millions of requests per second.
    *   **TTL:** Built-in "Time To Live" automatically deletes old sessions (perfect for our "Active Launch" logic).
*   **Security:** Can be secured with Private Endpoints and Access Keys.

**Decision:**
For the **Proof of Concept (PoC)**, Key Vault is fine and easy to set up.
For **Production**, we **must use Redis** (or Cosmos DB) to handle the scale of thousands of concurrent users.

## 8. Handling Multi-Tenancy (MSSP Scenario)

**The Challenge:**
A single user (e.g., `roie@mssp.com`) might have access to **multiple** Management Servers (Customer A, Customer B, Customer C).
If the Helper App just asks "Give me the context for `roie@mssp.com`", the backend won't know *which* specific server the user intends to connect to right now.

**The Solution: The "Active Session" State**
Since we cannot pass the "Target ID" in the URL, we must rely on the **Time-Based Active Session State** in the backend.

**The Workflow:**
1.  **Selection (Infinity Portal):**
    *   User `roie@mssp.com` is on the Infinity Portal.
    *   He sees a list of 50 customers.
    *   He clicks "Connect" on **Customer A**.

2.  **Staging (Backend):**
    *   The Infinity Portal Backend sets a **Short-Lived State** (e.g., 60 seconds TTL) in the database:
    *   *Key:* `ActiveLaunch:roie@mssp.com`
    *   *Value:* `{ Target: "Customer A", Token: "..." }`

3.  **Launch (AVD):**
    *   Portal immediately redirects Roie to AVD.
    *   AVD Session starts.

4.  **Retrieval (Helper App):**
    *   Helper App calls Backend: "What is the **active launch request** for `roie@mssp.com`?"
    *   Backend checks the `ActiveLaunch` key.
    *   Backend returns: "Customer A".
    *   Backend **deletes** the key (to prevent replay or confusion).

5.  **Result:**
    *   Smart Console opens for Customer A.

## 11. Context Lifecycle & Concurrency Handling

**The "Temporary" Nature of the Context:**
The context stored in the backend (Key Vault/Redis) is **transient**. It exists only to bridge the gap between the user's click in the Portal and the application launch in Azure.

**Lifecycle Steps:**
1.  **Creation:** Triggered by the "Connect" click.
2.  **Expiration (TTL):** Set to **60 seconds**. If the user closes the browser or the network fails, the key self-destructs to prevent stale data.
3.  **Consumption & Deletion:**
    *   The Helper App reads the key.
    *   **CRITICAL:** The Helper App immediately **deletes** the key after reading.
    *   **Reason:** Prevents "Replay Attacks" (malicious actors trying to reuse the session) and ensures hygiene.

**Concurrency Scenario (The "Double Click" Problem):**
*   **Scenario:** User Roie clicks "Connect Customer A", then 2 seconds later clicks "Connect Customer B".
*   **Behavior:**
    *   Click 1 sets Key = `Customer A`.
    *   Click 2 **overwrites** Key = `Customer B`.
    *   **Result:** Both AVD sessions (if they both launch) will read `Customer B`.
*   **Verdict:** This "Last Write Wins" behavior is acceptable for this use case. It prevents the user from accidentally connecting to the wrong (old) target.

**Multiple Simultaneous Sessions:**
*   If Roie connects to Customer A (Session 1 starts, Key deleted).
*   Then 1 minute later, Roie connects to Customer B (Session 2 starts, New Key created/deleted).
*   **Result:** Both sessions run in parallel without conflict because the first key was already gone.

**Edge Case: Multiple Tabs?**
*   If Roie clicks "Connect Customer A" and then immediately clicks "Connect Customer B" in another tab *before* the first session starts, the `ActiveLaunch` key might be overwritten.
*   **Mitigation:** This is a rare race condition. The "Launch" process is usually blocking or modal. The short TTL (Time To Live) ensures that old clicks don't linger.

## 9. Identity Migration (The "Entra ID" Requirement)

**The Gap:**
*   **Current State (AWS):** Users authenticate against a custom Identity Provider (IdP) or local DB in Infinity Portal. Their identity is passed to AWS AppStream via the encrypted context.
*   **Target State (Azure):** Azure Virtual Desktop (AVD) **requires** users to exist in **Microsoft Entra ID (Azure AD)** to log in. You cannot use AVD without Entra ID.

**The Migration Task:**
We must synchronize the Infinity Portal users into a dedicated Entra ID tenant.

**Strategy: "Shadow Accounts" (B2B or B2C)**
Since Infinity Portal owns the "Real" identity, the Azure identities are just "Shadows" used for access.

**Option A: Entra ID External Identities (B2B)**
1.  **Trigger:** When a user is migrated to Azure (or on first login).
2.  **Action:** Infinity Portal uses the Microsoft Graph API to **invite** the user (`roie@gmail.com`) to the Azure Tenant as a **Guest User**.
3.  **Flow:**
    *   User clicks "Connect".
    *   If not in Entra ID -> Create Guest User via API.
    *   Redirect to AVD.
    *   User accepts the "Microsoft Permission" prompt once.
    *   Session starts.

**Option B: Dedicated "Cloud-Only" Users**
1.  **Trigger:** Migration.
2.  **Action:** Create a cloud-only user `roie_gmail_com@checkpoint-farm.onmicrosoft.com` in the Azure Tenant.
3.  **Password:** Generate a random complex password.
4.  **SSO:** This is harder because the user doesn't know this password. We would need to implement a custom **SAML/OIDC Federation** where Infinity Portal acts as the IdP for Entra ID.

**Recommended Approach: Custom SAML Federation**
*   **Configure Entra ID** to trust **Infinity Portal** as an Identity Provider.
*   **Flow:**
    1.  User goes to AVD URL.
    2.  Azure redirects user to Infinity Portal for login.
    3.  Infinity Portal says "Yes, this is Roie" and sends a token back to Azure.
    4.  Azure logs Roie in.
*   **Benefit:** Seamless SSO. No new passwords. No "Guest" invites.

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

