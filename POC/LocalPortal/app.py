from flask import Flask, render_template, request, redirect, url_for, flash, session
import uuid
import datetime
import requests
import json
import os
from functools import wraps
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
from urllib.parse import urlencode
import urllib.parse

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'supersecretkey')  # Needed for flash messages

# --- AUTH (Keycloak OIDC) ---
KEYCLOAK_ISSUER_URL = os.getenv("KEYCLOAK_ISSUER_URL", "").strip().rstrip("/")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "").strip()
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "").strip()
KEYCLOAK_REDIRECT_URI = os.getenv("KEYCLOAK_REDIRECT_URI", "").strip()
KEYCLOAK_POST_LOGOUT_REDIRECT_URI = os.getenv("KEYCLOAK_POST_LOGOUT_REDIRECT_URI", "").strip()

oauth = OAuth(app)

if KEYCLOAK_ISSUER_URL and KEYCLOAK_CLIENT_ID:
    oauth.register(
        name="keycloak",
        client_id=KEYCLOAK_CLIENT_ID,
        client_secret=KEYCLOAK_CLIENT_SECRET or None,
        server_metadata_url=f"{KEYCLOAK_ISSUER_URL}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid profile email"},
    )


def _derive_user_id_from_claims(claims: dict) -> str:
    return (
        claims.get("upn")
        or claims.get("email")
        or claims.get("preferred_username")
        or claims.get("sub")
        or ""
    )


def _portal_user_key_from_claims(claims: dict) -> str:
    # We want to match the "key" in our JSON map.
    # If the user is "cp1", preferred_username might be "cp1" or "cp1@gmail.com".
    # For this POC, let's just return the 'preferred_username'.
    return claims.get("preferred_username", "") or claims.get("sub", "")


def _load_portal_to_avd_user_map() -> dict:
    # Example value:
    #   {"demo1": "cp1@mydemodomain.org", "demo2": "cp2@mydemodomain.org"}
    raw = os.getenv("PORTAL_TO_AVD_USER_MAP_JSON", "").strip()
    if not raw:
        return {}
    try:
        mapping = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(mapping, dict):
        return {}

    normalized = {}
    for k, v in mapping.items():
        if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
            normalized[k.strip()] = v.strip()
    return normalized


def _get_mapped_avd_user() -> str | None:
    portal_user = session.get("user", {})
    portal_to_avd = _load_portal_to_avd_user_map()
    portal_key = portal_user.get("portalUser", "")
    if not portal_key:
        return None
    return portal_to_avd.get(portal_key)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)

    return wrapper

# --- CONFIGURATION ---
# The URL of your deployed Azure Function
AZURE_FUNCTION_URL = os.getenv(
    "AZURE_FUNCTION_URL",
    "https://s1c-function-11729.azurewebsites.net/api/queue_connection",
)

# Optional: if set, after successfully queueing a request the portal will redirect the browser to this URL.
# This enables a PoC demo of: click Connect -> AVD Web client opens.
AVD_LAUNCH_URL = os.getenv("AVD_LAUNCH_URL", "").strip()

# Optional (preferred for this PoC): launch a specific RemoteApp via the Windows 365/AVD web client.
# This matches URLs like:
#   https://windows.cloud.microsoft/webclient/avd/<workspaceObjectId>/<remoteAppObjectId>?tenant=<tenantGuid>
# Set both IDs to enable.
AVD_DIRECT_REMOTEAPP_BASE_URL = os.getenv(
    "AVD_DIRECT_REMOTEAPP_BASE_URL",
    "https://windows.cloud.microsoft/webclient/avd",
).strip().rstrip("/")
AVD_WORKSPACE_OBJECT_ID = os.getenv("AVD_WORKSPACE_OBJECT_ID", "").strip()
AVD_REMOTEAPP_OBJECT_ID = os.getenv("AVD_REMOTEAPP_OBJECT_ID", "").strip()

# Optional: if set, pins the Azure AD / Entra tenant for AVD sign-in flows.
# IMPORTANT: use the tenant GUID (Directory ID), not the domain name.
ENTRA_TENANT_ID = os.getenv("ENTRA_TENANT_ID", "").strip()

# Optional: bootstrap URL to establish a Microsoft session in the browser.
# The AVD web client tends to start MSAL via /common and may ignore hints; bootstrapping helps.
ENTRA_BOOTSTRAP_BASE_URL = os.getenv(
    "ENTRA_BOOTSTRAP_BASE_URL",
    "https://myapplications.microsoft.com/",
).strip()

# Optional: a dedicated Entra "bootstrap" app registration (recommended for one-click).
# Create an Entra App Registration (single tenant) and add a redirect URI:
#   http://localhost:5001/entra/callback
# Then set ENTRA_BOOTSTRAP_CLIENT_ID to that app's Application (client) ID.
ENTRA_BOOTSTRAP_CLIENT_ID = os.getenv("ENTRA_BOOTSTRAP_CLIENT_ID", "").strip()
ENTRA_BOOTSTRAP_REDIRECT_URI = os.getenv(
    "ENTRA_BOOTSTRAP_REDIRECT_URI",
    "http://localhost:5001/entra/callback",
).strip()


def _build_avd_launch_url(*, tenant_id: str, login_hint: str | None) -> str:
    """Build the best AVD launch URL.

    If RemoteApp IDs are configured, returns the direct RemoteApp URL.
    Otherwise returns the generic AVD web client index URL.
    """
    safe_hint = None
    if login_hint and "@" in login_hint:
        # Keep this unescaped; urlencode() will apply escaping exactly once.
        safe_hint = login_hint

    if AVD_WORKSPACE_OBJECT_ID and AVD_REMOTEAPP_OBJECT_ID:
        # Windows 365 / AVD web client direct RemoteApp deep link
        base = f"{AVD_DIRECT_REMOTEAPP_BASE_URL}/{AVD_WORKSPACE_OBJECT_ID}/{AVD_REMOTEAPP_OBJECT_ID}"
        # The direct-link format uses `tenant=` (per observed URLs).
        qs = {"tenant": tenant_id}
        if safe_hint:
            qs["login_hint"] = safe_hint
        return f"{base}?{urlencode(qs)}"

    # Fallback: generic AVD web client index
    qs = {"tenantId": tenant_id}
    if safe_hint:
        qs["login_hint"] = safe_hint
    return f"https://client.wvd.microsoft.com/arm/webclient/index.html?{urlencode(qs)}"


@app.route("/entra/bootstrap")
@login_required
def entra_bootstrap():
    """Start an Entra sign-in to establish Microsoft session cookies, then return and forward to AVD."""
    # We need an AVD URL to forward to after bootstrap.
    next_url = (request.args.get("next") or "").strip()
    if not next_url:
        return "Missing next URL", 400

    if not ENTRA_TENANT_ID:
        return "ENTRA_TENANT_ID is not configured", 500
    if not ENTRA_BOOTSTRAP_CLIENT_ID:
        return "ENTRA_BOOTSTRAP_CLIENT_ID is not configured", 500

    # Use mapped AVD user as login_hint when available.
    mapped_avd_user = _get_mapped_avd_user()
    portal_user = session.get("user", {})
    portal_to_avd = _load_portal_to_avd_user_map()
    portal_key = portal_user.get("portalUser")
    user_id = portal_to_avd.get(portal_key) or portal_user.get("userId")
    hint_user = mapped_avd_user or user_id

    state = uuid.uuid4().hex
    session["entra_bootstrap_state"] = state
    session["entra_bootstrap_next"] = next_url

    params = {
        "client_id": ENTRA_BOOTSTRAP_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": ENTRA_BOOTSTRAP_REDIRECT_URI,
        "response_mode": "query",
        "scope": "openid profile",
        "state": state,
    }
    if hint_user and "@" in hint_user:
        params["login_hint"] = hint_user
        params["domain_hint"] = hint_user.split("@", 1)[1]

    authorize_url = f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}/oauth2/v2.0/authorize?{urlencode(params)}"
    print(f"[PORTAL DEBUG] Entra bootstrap authorize: {authorize_url}")
    return redirect(authorize_url)


@app.route("/entra/callback")
def entra_callback():
    """After Entra sign-in, forward the user to the AVD web client."""
    expected_state = session.pop("entra_bootstrap_state", None)
    next_url = session.pop("entra_bootstrap_next", None)
    state = (request.args.get("state") or "").strip()

    if not expected_state or state != expected_state:
        return "Invalid state", 400

    # We don't need to redeem the code for this PoC; the purpose is to establish the browser session.
    if not next_url:
        return redirect(url_for("index"))

    return redirect(next_url)

# --- LOCAL LOG (To show history in UI) ---
# Structure: { "userId": [ { request_obj }, ... ] }
REQUEST_HISTORY = {}

# --- MOCK DATA (Simulating Infinity Portal Customers) ---
CUSTOMERS = [
    {"id": "cust_1", "name": "Acme Corp (Firewall A)", "ip": "10.0.1.5", "user": "admin"},
    {"id": "cust_2", "name": "Globex Inc (Firewall B)", "ip": "192.168.10.20", "user": "admin"},
    {"id": "cust_3", "name": "Soylent Corp (Firewall C)", "ip": "172.16.0.5", "user": "readonly"},
    {
        "id": "cust_4",
        "name": "Real Test (Azure VM) - cp1",
        "ip": "20.240.218.22",
        "user": "cp1",
        "avdUserId": "cp1@mydemodomain.org",
        "password": os.getenv("CP1_PASSWORD")
    },
    {
        "id": "cust_5",
        "name": "Real Test (Azure VM) - Admin",
        "ip": "20.240.218.22",
        "user": "admin",
        "avdUserId": "cp2@mydemodomain.org",
        "password": os.getenv("ADMIN_PASSWORD")
    }
]

@app.route('/')
@login_required
def index():
    """Renders the Portal Dashboard."""
    mapped_avd_user = _get_mapped_avd_user()
    appstream_ctx = session.get("appstream_session_context", "")

    # If a portal user is mapped to a specific AVD UPN, only show that user's entries.
    # This simulates: demo1 can only request cp1 session; demo2 can only request cp2 session.
    if mapped_avd_user:
        visible_customers = [c for c in CUSTOMERS if c.get("avdUserId") == mapped_avd_user]
    else:
        visible_customers = CUSTOMERS

    return render_template(
        'index.html',
        customers=visible_customers,
        history=REQUEST_HISTORY,
        current_user=session.get("user"),
        mapped_avd_user=mapped_avd_user,
        appstream_session_context=appstream_ctx,
    )


@app.route('/set_context', methods=['POST'])
@login_required
def set_context():
    # Value typed by the portal user; pushed to AVD via broker+launcher.
    value = (request.form.get('APPSTREAM_SESSION_CONTEXT') or '').strip()
    if not value:
        flash("APPSTREAM_SESSION_CONTEXT is required.", "error")
        return redirect(url_for('index'))

    # Keep it in the Flask session for this logged-in portal user.
    session['appstream_session_context'] = value
    flash("APPSTREAM_SESSION_CONTEXT saved.", "success")
    return redirect(url_for('index'))


@app.route('/login')
def login():
    if not (KEYCLOAK_ISSUER_URL and KEYCLOAK_CLIENT_ID and KEYCLOAK_REDIRECT_URI):
        return (
            "Keycloak OIDC is not configured. Set KEYCLOAK_ISSUER_URL, KEYCLOAK_CLIENT_ID, KEYCLOAK_REDIRECT_URI.",
            500,
        )

    keycloak = oauth.create_client("keycloak")
    # Force showing the login screen so switching users works even when a Keycloak SSO session exists.
    return keycloak.authorize_redirect(KEYCLOAK_REDIRECT_URI, prompt="login", max_age="0")


@app.route('/auth/callback')
def auth_callback():
    keycloak = oauth.create_client("keycloak")
    token = keycloak.authorize_access_token()

    # Keep id_token so we can properly log out of Keycloak (end_session_endpoint expects id_token_hint).
    session["id_token"] = token.get("id_token")

    claims = token.get("userinfo")
    if not claims:
        try:
            claims = keycloak.parse_id_token(token)
        except Exception:
            claims = {}

    user_id = _derive_user_id_from_claims(claims)
    if not user_id:
        return "Unable to derive user identity from Keycloak claims", 500

    portal_user_key = _portal_user_key_from_claims(claims)
    if not portal_user_key:
        return "Unable to derive portal user identity from Keycloak claims", 500

    session["user"] = {
        "userId": user_id,
        "portalUser": portal_user_key,
        "name": claims.get("name") or claims.get("preferred_username") or user_id,
    }

    flash(f"Signed in as {session['user']['name']}", "success")
    return redirect(url_for("index"))


@app.route('/logout')
def logout():
    id_token_hint = session.pop("id_token", None)
    session.pop("user", None)

    # Optional: also redirect to Keycloak end_session endpoint if available.
    if KEYCLOAK_ISSUER_URL and KEYCLOAK_POST_LOGOUT_REDIRECT_URI:
        keycloak = oauth.create_client("keycloak")
        end_session_endpoint = None
        try:
            end_session_endpoint = keycloak.server_metadata.get("end_session_endpoint")
        except Exception:
            end_session_endpoint = None

        if end_session_endpoint:
            # Keycloak versions differ in how they validate logout redirects. Many deployments validate
            # `redirect_uri` against the client's normal redirect URI list (while `post_logout_redirect_uri`
            # requires a separate allowlist). For PoC, prefer `redirect_uri` to reduce configuration friction.
            params = {"client_id": KEYCLOAK_CLIENT_ID}
            if id_token_hint:
                params["id_token_hint"] = id_token_hint
            if KEYCLOAK_POST_LOGOUT_REDIRECT_URI:
                params["redirect_uri"] = KEYCLOAK_POST_LOGOUT_REDIRECT_URI

            return redirect(f"{end_session_endpoint}?{urlencode(params)}")

    return redirect(url_for("login"))

@app.route('/connect/<customer_id>', methods=['POST'])
@login_required
def connect(customer_id):
    """
    Simulates the user clicking 'Connect'.
    Sends a POST request to the REAL Azure Function.
    """
    # 1. Find Customer
    customer = next((c for c in CUSTOMERS if c['id'] == customer_id), None)
    if not customer:
        return "Customer not found", 404

    mapped_avd_user = _get_mapped_avd_user()
    if mapped_avd_user and customer.get("avdUserId") != mapped_avd_user:
        flash("You are not allowed to connect as that AVD user.", "error")
        return redirect(url_for('index'))

    # Prefer value posted from the Connect form (lets user type and click Connect without a separate Save).
    posted_ctx = (request.form.get("APPSTREAM_SESSION_CONTEXT") or "").strip()
    if posted_ctx:
        session["appstream_session_context"] = posted_ctx

    appstream_ctx = (session.get("appstream_session_context") or "").strip()
    if not appstream_ctx:
        flash("Please set APPSTREAM_SESSION_CONTEXT before connecting.", "error")
        return redirect(url_for('index'))

    # 2. Identify user for the Broker queue
    # This must match the AVD session's `whoami /upn` for the launcher to pick it up.
    portal_user = session.get("user", {})
    portal_user_key = portal_user.get("portalUser")
    if not portal_user_key:
        flash("Not signed in (missing user identity)", "error")
        return redirect(url_for("login"))

    portal_to_avd = _load_portal_to_avd_user_map()
    user_id = portal_to_avd.get(portal_user_key) or portal_user.get("userId")

    # 3. Prepare Payload for Azure Function
    payload = {
        "userId": user_id,
        "targetIp": customer['ip'],
        "username": customer['user'],
        "password": customer.get('password', "SecretPassword123!"), # Use specific password if available, else default
        "targetName": customer['name'],
        # New dynamic value (entered by portal user) to be pushed to AVD.
        "appstreamSessionContext": appstream_ctx,
    }

    # 4. Call Azure Function
    try:
        print(f"[PORTAL] Sending request to Azure: {AZURE_FUNCTION_URL}")
        response = requests.post(AZURE_FUNCTION_URL, json=payload)
        
        if response.status_code in [200, 201]:
            flash(f"Successfully queued connection for {customer['name']}", "success")
            status = f"SENT ({response.status_code} OK)"
        else:
            flash(f"Error from Azure: {response.text}", "error")
            status = f"ERROR ({response.status_code})"
            
    except Exception as e:
        flash(f"Failed to connect to Azure: {str(e)}", "error")
        status = "FAILED"

    # 5. Log to Local History (for UI display only)
    if user_id not in REQUEST_HISTORY:
        REQUEST_HISTORY[user_id] = []
    
    log_entry = {
        "targetName": customer['name'],
        "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
        "status": status
    }
    # Prepend to list
    REQUEST_HISTORY[user_id].insert(0, log_entry)

    if status.startswith("SENT") and (AVD_LAUNCH_URL or (AVD_WORKSPACE_OBJECT_ID and AVD_REMOTEAPP_OBJECT_ID)):
        # Append login_hint to help Microsoft auto-select the federated user
        target_url = AVD_LAUNCH_URL
        # Ensure we use the MAPPED user (e.g. cp1@mydemodomain.org) not the portal user ID (cp1)
        hint_user = mapped_avd_user or user_id
        
        if hint_user and "@" in hint_user:
            # Extract domain
            parts = hint_user.split("@")
            domain_part = parts[1] if len(parts) > 1 else ""

            # Prefer tenant GUID if configured; else fall back to a best-effort.
            tenant_id = ENTRA_TENANT_ID or domain_part
            avd_url = _build_avd_launch_url(tenant_id=tenant_id, login_hint=hint_user)

            # Preferred: one-click flow via Entra bootstrap app (top-level navigation + callback).
            # This avoids racing two tabs that both prompt for login.
            if ENTRA_TENANT_ID and ENTRA_BOOTSTRAP_CLIENT_ID:
                print(
                    f"[PORTAL DEBUG] Redirecting to Entra bootstrap (tenantId={tenant_id}) then AVD={avd_url}"
                )
                return redirect(url_for("entra_bootstrap", next=avd_url))

            # Fallback: helper page (works, but may require user to click through).
            safe_hint = urllib.parse.quote(hint_user)
            bootstrap_url = (
                f"{ENTRA_BOOTSTRAP_BASE_URL}?tenantId={tenant_id}"
                f"&login_hint={safe_hint}"
            )

            print(
                f"[PORTAL DEBUG] Launch helper fallback (tenantId={tenant_id}) bootstrap={bootstrap_url} avd={avd_url}"
            )

            return render_template(
                "avd_launch.html",
                bootstrap_url=bootstrap_url,
                avd_url=avd_url,
                upn=hint_user,
                auto_open=False,
            )

        return redirect(target_url)

    return redirect(url_for('index'))

@app.route('/reset', methods=['POST'])
@login_required
def reset():
    global REQUEST_HISTORY
    REQUEST_HISTORY = {}
    return redirect(url_for('index'))

if __name__ == '__main__':
    print("Starting Local Portal on http://127.0.0.1:5001")
    app.run(debug=True, host='0.0.0.0', port=5001)
