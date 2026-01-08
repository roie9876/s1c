# SSO Federation Runbook (Keycloak ↔ Entra ID ↔ AVD Web)

**Date:** 2026-01-07

## Goal
Enable a working PoC of:
- Users authenticate to the Local Infinity Portal simulator via **Keycloak**.
- Azure AD (Entra ID) is configured to federate the custom domain **mydemodomain.org** to **Keycloak**.
- Clicking **Connect** in the portal queues credentials to the broker and then launches **AVD Web Client (Smart Console)** with SSO (no typing username).

This repo’s architectural goal is the “Pull model”:
- Infinity Portal queues credentials/context.
- AVD session runs a launcher that pulls the request.

## What is working now
1. **Keycloak OIDC** login for the local portal works.
2. **Entra domain federation** for `mydemodomain.org` pointing to Keycloak works.
3. **User linking** between Keycloak users and Entra users works (via `onPremisesImmutableId`).
4. **One-click Connect** now performs a tenant-specific Entra bootstrap flow and then forwards into AVD Web Client.
   - First-time prompts can still appear (“Do you trust …”, “Stay signed in?”), but after acceptance the experience becomes close to seamless.

## Repository components involved
- Local Portal (Flask): [POC/LocalPortal/app.py](POC/LocalPortal/app.py)
- Local Portal UI templates:
  - [POC/LocalPortal/templates/index.html](POC/LocalPortal/templates/index.html)
  - [POC/LocalPortal/templates/avd_launch.html](POC/LocalPortal/templates/avd_launch.html)
- Local Portal configuration: [POC/LocalPortal/.env](POC/LocalPortal/.env)
- Broker (Azure Function): [POC/AzureFunction/function_app.py](POC/AzureFunction/function_app.py)
- Launcher (AVD): [POC/Launcher.ps1](POC/Launcher.ps1)

## Identity design (high level)
- **Keycloak** is the identity provider for the Portal (OIDC).
- **Entra ID** federates the custom domain `mydemodomain.org` to Keycloak.
- **AVD Web Client** uses Entra for authentication, but the web client initiates its own MSAL flow and often starts at the `.../common/...` endpoint.

Key constraint discovered during debugging:
- The AVD web client does not reliably honor `login_hint` / `tenantId` passed on the URL. It starts its own sign-in via MSAL and may fall back to `login.microsoftonline.com/common`, which triggers a username prompt.

Therefore the working strategy is:
- Establish an Entra session first in the browser (tenant-specific), then navigate to AVD web client.

## Configuration

### 1) Entra tenant
- Tenant ID (Directory ID): `<YOUR_ENTRA_TENANT_ID_GUID>`

### 2) Keycloak (realm: `s1c`)
Portal OIDC uses Keycloak as configured in [POC/LocalPortal/.env](POC/LocalPortal/.env):
- `KEYCLOAK_ISSUER_URL=https://idp.example.com/realms/s1c`
- `KEYCLOAK_CLIENT_ID=localportal`
- `KEYCLOAK_REDIRECT_URI=http://localhost:5001/auth/callback`

### 3) Entra ↔ Keycloak federation for domain `mydemodomain.org`
We configured the Entra custom domain as **Federated**, pointing to Keycloak endpoints.

Note: the exact commands depend on the federation method you used (MSOL/Graph/PowerShell). Keep the authoritative script/config in your internal setup scripts.

### 4) User linking (critical)
We manually linked Entra users (e.g., `cp1`, `cp2`) to Keycloak users by setting the Entra user’s `onPremisesImmutableId` to match what Entra expects for the federated identity.

This was done using `az rest` PATCH requests (redacted).

Verification:
- Manual sign-in to Microsoft using `cp1@mydemodomain.org` routes to Keycloak and succeeds.

### 5) Local Portal runtime configuration
In [POC/LocalPortal/.env](POC/LocalPortal/.env):
- Optional fallback: `AVD_LAUNCH_URL=https://client.wvd.microsoft.com/arm/webclient/index.html`
- Preferred: direct launch of a specific RemoteApp
   - `AVD_WORKSPACE_OBJECT_ID=<WORKSPACE_OBJECT_ID>`
   - `AVD_REMOTEAPP_OBJECT_ID=<REMOTEAPP_OBJECT_ID>`
   - Optional: `AVD_DIRECT_REMOTEAPP_BASE_URL=https://windows.cloud.microsoft/webclient/avd`
- `ENTRA_TENANT_ID=<YOUR_ENTRA_TENANT_ID_GUID>`
- `PORTAL_TO_AVD_USER_MAP_JSON={"cp1":"cp1@yourdomain.example","cp2":"cp2@yourdomain.example"}`

#### Entra bootstrap app (required for true one-click)
To avoid racing multiple tabs and reduce username prompts, the Portal can use a dedicated Entra app registration to bootstrap session cookies.

Create an App Registration in Entra:
1. Entra ID → App registrations → New registration
   - Single tenant
   - Name: `localportal-bootstrap` (any name)
2. Authentication → Add platform → **Web**
   - Redirect URI: `http://localhost:5001/entra/callback`

Then set in [POC/LocalPortal/.env](POC/LocalPortal/.env):
- `ENTRA_BOOTSTRAP_CLIENT_ID=<app client id>`
- Optional: `ENTRA_BOOTSTRAP_REDIRECT_URI=http://localhost:5001/entra/callback`

No client secret is required for this PoC (authorization code is not redeemed; the purpose is establishing a browser session).

Implementation detail (current portal behavior):
- The portal attempts a silent bootstrap first (`prompt=none`) to reduce the chance of the Microsoft “Pick an account” screen.
- If Entra returns `login_required` / `interaction_required` / `consent_required`, the portal automatically retries interactively.

## End-to-end test flow

### 1) Start the local portal
From the repo root:
- `cd POC/LocalPortal`
- `pip install -r requirements.txt`
- `python3 app.py`

Open:
- `http://localhost:5001`

### 2) Login to the portal
- Click Login
- Authenticate via Keycloak

### 3) Set `APPSTREAM_SESSION_CONTEXT`
- Enter a value
- Click Save

### 4) Click Connect
On success:
- Portal queues the request to the Azure Function broker.
- Portal then starts Entra bootstrap and forwards to AVD web client.

Expected first-time prompts (may appear):
- “Do you trust mydemodomain.org?”
- “Stay signed in?”

### 5) Verify Smart Console launch
- You should land in the AVD Web Client and be able to open Smart Console without typing username.

## What we tried (and why it failed)
This section records the explored strategies to avoid losing time in future debugging.

- Direct AVD URL + `login_hint`: AVD web client initiated MSAL and ignored/dropped hints.
- Tenant-specific OAuth to AVD app: still ended up with username prompt after round-trip.
- Windows365 portal: the portal started its own MSAL flow and did not reliably preserve `login_hint`.
- My Apps dashboard: successfully established session, but didn’t land directly in Smart Console.
- My Apps deep link: sometimes hit cookie/third-party restrictions depending on browser settings.
- WS-Fed smart links: resulted in `AADSTS700011` / application identifier mismatch for the AVD web client.

Final approach:
- Use a dedicated Entra “bootstrap” app + callback (tenant-specific) and then forward to AVD Web Client.

## Troubleshooting

### AVD still asks for username
- Confirm you have `ENTRA_TENANT_ID` set to the tenant GUID.
- Confirm `ENTRA_BOOTSTRAP_CLIENT_ID` is set (otherwise you will fall back to manual steps).
- Confirm the Entra bootstrap app has redirect URI `http://localhost:5001/entra/callback`.

### Cookie-related errors
- Avoid third-party-cookie dependent flows (My Apps deep-link can trigger this).
- Prefer the tenant-specific top-level redirect through `login.microsoftonline.com/{tenantId}/...`.

### “Trust” / “Stay signed in?” prompts
These are Entra/browser interstitials.
- They often reduce after the first acceptance in the same browser profile.
- To reduce “Stay signed in?” globally typically requires tenant-level configuration (KMSI prompt setting).

### Microsoft “Pick an account” still appears
This is usually caused by multiple Microsoft accounts being signed into the same browser profile.
Mitigation for demos:
- Use a fresh browser profile with only the target PoC user signed in.
- Or sign out of other Microsoft accounts / clear Microsoft login cookies for that profile.

## Notes / Security
- Do not commit secrets in `.env` in real environments.
- Avoid logging credentials or tokens.

