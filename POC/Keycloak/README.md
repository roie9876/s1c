# Keycloak (SAML IdP) on Azure Container Apps (PoC)

Goal: run a PoC SAML Identity Provider (Keycloak) with a stable HTTPS URL so you can federate Entra to it and demonstrate **AVD Web “no second login prompt”** via SSO.

## Why this exists
- AVD Web authentication is Entra-based.
- To avoid a second prompt when launching AVD from the “Infinity Portal” PoC, both the Portal and Entra should rely on the **same upstream IdP session**.
- In this PoC, Keycloak is the upstream SAML IdP.

## Deploy Keycloak

Prereqs:
- Azure CLI installed and authenticated: `az login`

Run:

```bash
export KEYCLOAK_ADMIN_PASSWORD='ChangeMe123!'
./POC/Keycloak/deploy_containerapp.sh
```

The script prints a `https://...azurecontainerapps.io` URL.

Notes:
- This deployment uses Keycloak `start-dev` (dev-mode). It’s fine for PoC demos.
- If you need persistence and resilience, switch Keycloak to Postgres + production mode.

## Configure federation to Entra (high level)

You said you want Keycloak users to exist as **guests** in your Entra tenant.

High-level steps (exact clicks vary by tenant features):
1. In Entra, configure an **external identity / federation** method that trusts your Keycloak instance as a SAML IdP.
2. Ensure users can authenticate via that IdP and appear in your tenant as guests.
3. Assign those guest users to the AVD application group.

## Demo: “Connect → AVD Web → no second prompt”

To make the SSO demo work reliably:
- Use **AVD Web Client**
- Use the **same browser session** for the Portal and the AVD tab

Recommended demo sequence:
1. Open Keycloak, sign in once (establish Keycloak session).
2. Open the Portal PoC.
3. Click **Connect**.
4. Portal opens AVD Web Client URL.
5. Entra redirects to Keycloak, which reuses the existing session → you should not have to type credentials again.

## Portal PoC integration

The Portal can optionally redirect to AVD Web after queuing a request.

- Set `AVD_LAUNCH_URL` for the Portal (for example, AVD Web Client URL you use in your tenant).
- When set, clicking **Connect** will redirect the browser to that URL after successfully queuing the connection.

