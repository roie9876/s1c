from flask import Flask, render_template, request, redirect, url_for, flash
import uuid
import datetime
import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Needed for flash messages

# --- CONFIGURATION ---
# The URL of your deployed Azure Function
AZURE_FUNCTION_URL = "https://s1c-function-11729.azurewebsites.net/api/queue_connection"

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
        "avdUserId": "cp1@roie9876gmail.onmicrosoft.com",
        "password": os.getenv("CP1_PASSWORD")
    },
    {
        "id": "cust_5",
        "name": "Real Test (Azure VM) - Admin",
        "ip": "20.240.218.22",
        "user": "admin",
        "avdUserId": "cp2@roie9876gmail.onmicrosoft.com",
        "password": os.getenv("ADMIN_PASSWORD")
    }
]

@app.route('/')
def index():
    """Renders the Portal Dashboard."""
    return render_template('index.html', customers=CUSTOMERS, history=REQUEST_HISTORY)

@app.route('/connect/<customer_id>', methods=['POST'])
def connect(customer_id):
    """
    Simulates the user clicking 'Connect'.
    Sends a POST request to the REAL Azure Function.
    """
    # 1. Find Customer
    customer = next((c for c in CUSTOMERS if c['id'] == customer_id), None)
    if not customer:
        return "Customer not found", 404

    # 2. Identify AVD User (PoC mapping)
    # In production, the portal would queue requests under the user's Entra UPN.
    user_id = customer.get('avdUserId') or "roie@mssp.com"

    # 3. Prepare Payload for Azure Function
    payload = {
        "userId": user_id,
        "targetIp": customer['ip'],
        "username": customer['user'],
        "password": customer.get('password', "SecretPassword123!"), # Use specific password if available, else default
        "targetName": customer['name']
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

    return redirect(url_for('index'))

@app.route('/reset', methods=['POST'])
def reset():
    global REQUEST_HISTORY
    REQUEST_HISTORY = {}
    return redirect(url_for('index'))

if __name__ == '__main__':
    print("Starting Local Portal on http://127.0.0.1:5001")
    app.run(debug=True, host='0.0.0.0', port=5001)
