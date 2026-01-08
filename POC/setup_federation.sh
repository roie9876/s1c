#!/bin/bash

# Configuration
DOMAIN="mydemodomain.org"
REALM="s1c"
KEYCLOAK_URL="https://idp.mydemodomain.org/realms/$REALM/protocol/saml"
ISSUER_URI="https://idp.mydemodomain.org/realms/$REALM"

# Your Certificate (Captured from your previous edit)
SIGNING_CERT="MIIClTCCAX0CBgGbl0Kw5TANBgkqhkiG9w0BAQsFADAOMQwwCgYDVQQDDANzMWMwHhcNMjYwMTA3MDY1OTQ4WhcNMzYwMTA3MDcwMTI4WjAOMQwwCgYDVQQDDANzMWMwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQDUa61ZJbvdNhsU36Xdjhsk7jU8JO/5ftCfpSvPicMUr1NdArgyeYEL67WW4hy+/BimwSExXPIv/r7hvleRakGKAiqIfSL3WqnYOMqr/12wnLcZLeoNpKeSgBdWFUGimHedjpWpwH9BudA7bjyhEifFg/KFOWB3hTDK3uQie80mGfk+Xoy+lYp9N/HOhZfeY4JgFOUjrg/VF8oEBnGo9+b1xXJUpcE1LyvRQSeT5CmCxLVo6PxeTv+jbPrkV50dRSPF5SAraRtPH8NXySBxg3lfx1oHjCAicSh77VUXvpdNEr92AZ69bc8X99mfZ7Hk0ZZPa9yWkhpN7dCv0fhLPclLAgMBAAEwDQYJKoZIhvcNAQELBQADggEBAFDV7NCXLSb8tblhku/vxyBQ/xF2JRtEkQu0oOSMnmjXmyY4lh6gDcEYsGlgr7Tze663D/KcZiHzgTXuktypyf5sSOYho0mKbuksy++nOviwgzxQL3hQtOJgDfoAG2anJeiJqtQh7AnAqCR/AIkLAmYfALvAbZnAefnlnmUWXAdsinACSEVjPXJNewfbVqZ9oDa4kNy+66LzjPMy+1mRoD9B4pf6KnGrnOR/FUzS5fYEO7XZrIsIkTUirQ6zawINJ4DsSshPg5Ox93Wnv5wwx3pdJIEZG+1LZaYr1XvLBH7ZJTHX9h9d58DtMMWSotoKUxuxU2BUXDGAmMPgNlDm/iE="

# Clean the certificate string using python to be absolutely sure
# The helper script is inside the POC folder.
if [ -f "clean_cert_helper.py" ]; then
    CLEAN_CERT=$(python3 clean_cert_helper.py)
elif [ -f "POC/clean_cert_helper.py" ]; then
    CLEAN_CERT=$(python3 POC/clean_cert_helper.py)
else
    # Fallback if I cant find file (assuming run from root)
    CLEAN_CERT=$(python3 POC/clean_cert_helper.py) 
fi

# Debug: Print first and last few chars to verify
echo "Certificate Debug: ${CLEAN_CERT:0:10} ... ${CLEAN_CERT: -10}"

echo "Configuring Federation for $DOMAIN to use Keycloak realm $REALM..."

# Create a temporary JSON file to avoid shell escaping issues
JSON_FILE="federation_payload.json"
cat <<EOF > "$JSON_FILE"
{
  "@odata.type": "#microsoft.graph.internalDomainFederation",
  "issuerUri": "$ISSUER_URI",
  "passiveSignInUri": "$KEYCLOAK_URL",
  "preferredAuthenticationProtocol": "saml",
  "signingCertificate": "$CLEAN_CERT",
  "activeSignInUri": "$KEYCLOAK_URL",
  "signOutUri": "$KEYCLOAK_URL",
  "displayName": "Keycloak-Federation",
  "isSignedAuthenticationRequestRequired": false,
  "federatedIdpMfaBehavior": "acceptIfMfaDoneByFederatedIdp"
}
EOF

echo "Sending request to Microsoft Graph via az rest..."
# Used @file syntax which is safer for large/complex JSON
az rest --method POST \
  --uri "https://graph.microsoft.com/v1.0/domains/$DOMAIN/federationConfiguration" \
  --body @"$JSON_FILE" \
  --headers "Content-Type=application/json"

RESULT=$?
# rm "$JSON_FILE" # Keep file for debugging if it fails again

if [ $RESULT -eq 0 ]; then
    echo ""
    echo "SUCCESS: Domain $DOMAIN is now federated to Keycloak ($REALM)."
else
    echo ""
    echo "FAILED. Check 'federation_payload.json' to see what was sent."
fi
