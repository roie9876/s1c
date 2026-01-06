#!/usr/bin/env bash
set -euo pipefail

# Deploy Keycloak to Azure Container Apps (PoC)
# - Uses Keycloak "start-dev" for simplicity
# - Creates an HTTPS public endpoint via Container Apps ingress
# - Stores admin password as a Container Apps secret
#
# Prereqs:
#   - Azure CLI: https://learn.microsoft.com/cli/azure/install-azure-cli
#   - Logged in: az login
#
# Notes:
#   - This is PoC/dev mode. For durability/production, use Postgres and run Keycloak in production mode.

: "${AZURE_LOCATION:=eastus2}"
: "${RESOURCE_GROUP:=s1c-poc-rg}"
: "${CONTAINERAPPS_ENV:=s1c-keycloak-env}"
: "${KEYCLOAK_APP:=s1c-keycloak}"
: "${KEYCLOAK_IMAGE:=quay.io/keycloak/keycloak:latest}"
: "${KEYCLOAK_ADMIN_USER:=admin}"

if [[ -z "${KEYCLOAK_ADMIN_PASSWORD:-}" ]]; then
  echo "ERROR: KEYCLOAK_ADMIN_PASSWORD env var must be set" >&2
  echo "Example: export KEYCLOAK_ADMIN_PASSWORD='ChangeMe123!'" >&2
  exit 1
fi

if ! command -v az >/dev/null 2>&1; then
  echo "ERROR: az CLI not found. Install Azure CLI first." >&2
  exit 1
fi

echo "[1/6] Ensuring resource group '${RESOURCE_GROUP}' in '${AZURE_LOCATION}'..."
az group create --name "$RESOURCE_GROUP" --location "$AZURE_LOCATION" 1>/dev/null

echo "[2/6] Ensuring Container Apps extension..."
az extension add --name containerapp --upgrade 1>/dev/null

echo "[3/6] Ensuring Container Apps environment '${CONTAINERAPPS_ENV}'..."
# Container Apps env requires a Log Analytics workspace; the CLI can create one for you.
# If this fails in your environment, create a workspace manually and pass --logs-workspace-id/--logs-workspace-key.
az containerapp env create \
  --name "$CONTAINERAPPS_ENV" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$AZURE_LOCATION" \
  1>/dev/null

echo "[4/6] Creating/updating Keycloak container app '${KEYCLOAK_APP}'..."
# Create first (idempotency varies by CLI version; if it already exists, we'll update settings after).
if ! az containerapp show --name "$KEYCLOAK_APP" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
  az containerapp create \
    --name "$KEYCLOAK_APP" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$CONTAINERAPPS_ENV" \
    --image "$KEYCLOAK_IMAGE" \
    --ingress external \
    --target-port 8080 \
    --transport auto \
    --min-replicas 1 \
    --max-replicas 1 \
    --cpu 1.0 \
    --memory 2.0Gi \
    --secrets "kc-admin-password=$KEYCLOAK_ADMIN_PASSWORD" \
    --env-vars \
      "KC_BOOTSTRAP_ADMIN_USERNAME=$KEYCLOAK_ADMIN_USER" \
      "KC_BOOTSTRAP_ADMIN_PASSWORD=secretref:kc-admin-password" \
      "KC_HEALTH_ENABLED=true" \
      "KC_HOSTNAME_STRICT=false" \
      "KC_PROXY_HEADERS=xforwarded" \
    --args start-dev \
    1>/dev/null
else
  # Ensure secret + env vars are up-to-date
  az containerapp secret set \
    --name "$KEYCLOAK_APP" \
    --resource-group "$RESOURCE_GROUP" \
    --secrets "kc-admin-password=$KEYCLOAK_ADMIN_PASSWORD" \
    1>/dev/null

  az containerapp update \
    --name "$KEYCLOAK_APP" \
    --resource-group "$RESOURCE_GROUP" \
    --image "$KEYCLOAK_IMAGE" \
    --set-env-vars \
      "KC_BOOTSTRAP_ADMIN_USERNAME=$KEYCLOAK_ADMIN_USER" \
      "KC_BOOTSTRAP_ADMIN_PASSWORD=secretref:kc-admin-password" \
      "KC_HEALTH_ENABLED=true" \
      "KC_HOSTNAME_STRICT=false" \
      "KC_PROXY_HEADERS=xforwarded" \
    --args start-dev \
    1>/dev/null
fi

echo "[5/6] Fetching FQDN..."
FQDN=$(az containerapp show --name "$KEYCLOAK_APP" --resource-group "$RESOURCE_GROUP" --query "properties.configuration.ingress.fqdn" -o tsv)
if [[ -z "$FQDN" ]]; then
  echo "ERROR: Could not determine Keycloak FQDN" >&2
  exit 1
fi

KEYCLOAK_URL="https://${FQDN}"

echo "[6/6] Done. Keycloak URL:" 

echo "$KEYCLOAK_URL"

echo "Next steps:" 
echo "- Open: $KEYCLOAK_URL" 
echo "- Admin console: $KEYCLOAK_URL/admin" 
echo "- Login with: $KEYCLOAK_ADMIN_USER / (your KEYCLOAK_ADMIN_PASSWORD)" 
