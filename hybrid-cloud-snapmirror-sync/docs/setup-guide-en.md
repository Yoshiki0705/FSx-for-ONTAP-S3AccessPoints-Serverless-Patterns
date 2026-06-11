# Setup Guide

[日本語](setup-guide-ja.md) | [English](setup-guide-en.md)

## Prerequisites

### Hardware / Software

- PC for running the Sync Server (Windows/Mac/Linux)
  - Docker Desktop installed (**recommended**), **or**
  - Python 3.10–3.13 installed (3.14+ not supported)
- On-premises NetApp ONTAP (9.8 or later)
- FSx for NetApp ONTAP on AWS
- SnapMirror relationship established between both systems

### Network

- HTTPS (443) connectivity from the Sync Server to the ONTAP management LIF
- HTTP (8080) connectivity from client devices to the Sync Server
- Assumes usage within the same network (e.g., event venue WiFi)

---

## Using an Existing FSx Environment

The CloudFormation template (`infra/template.yaml`) creates a new VPC + FSx. If you already have FSx for ONTAP running, template deployment is **not required**.

Retrieve the necessary information from your existing environment:

```bash
# Check FSx file system management endpoint
aws fsx describe-file-systems \
  --query 'FileSystems[*].[FileSystemId,DNSName]' \
  --output table \
  --region ap-northeast-1

# Get SnapMirror relationship UUID via REST API
curl -k -u fsxadmin:<password> \
  https://<FSx_Management_Endpoint>/api/snapmirror/relationships \
  | python3 -m json.tool
```

Set the retrieved information in `.env`:
```ini
ONTAP_HOST=management.fs-xxxxxxxxxx.fsx.ap-northeast-1.amazonaws.com
SNAPMIRROR_UUID=<retrieved UUID>
```

→ For Steps 1–3 below, just verify, then proceed to Step 4.

---

## Step 1: Verify SnapMirror Relationship

### Via ONTAP CLI

```bash
# List SnapMirror relationships
snapmirror show

# Expected output:
# Source Path:      svm_src:vol_demo
# Destination Path: svm_dst:vol_demo
# State:            Snapmirrored
# Status:           Idle
```

### Get UUID via ONTAP REST API

```bash
# Execute against the FSx for ONTAP management endpoint
# (requires VPN access)
curl -k -u fsxadmin:<password> \
  https://management.fs-xxxxxxxxxx.fsx.ap-northeast-1.amazonaws.com/api/snapmirror/relationships \
  | python3 -m json.tool
```

Response example:
```json
{
  "records": [
    {
      "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "source": {
        "path": "svm_src:vol_demo",
        "svm": {"name": "svm_src"}
      },
      "destination": {
        "path": "svm_dst:vol_demo",
        "svm": {"name": "svm_dst"}
      },
      "state": "snapmirrored",
      "healthy": true
    }
  ]
}
```

Note the `uuid` value above.

---

## Step 2: Prepare Configuration File

```bash
# Navigate to the project directory
cd snapmirror-one-click-sync

# Create configuration file
cp .env.example .env
```

Edit `.env`:

```ini
# ⚠️ Important: Specify the FSx for ONTAP (Destination) management endpoint
# SnapMirror relationships are owned by the Destination cluster
ONTAP_HOST=management.fs-xxxxxxxxxxxxxxxxx.fsx.ap-northeast-1.amazonaws.com

# FSx ONTAP admin user
ONTAP_USER=fsxadmin
ONTAP_PASSWORD=YourSecurePassword

# Set to false for self-signed certificates
ONTAP_VERIFY_SSL=false

# UUID from Step 1
SNAPMIRROR_UUID=a1b2c3d4-e5f6-7890-abcd-ef1234567890

# API authentication token (optional — recommended)
AUTH_TOKEN=demo-secret-token-2026

# Server settings (normally no changes needed)
SERVER_HOST=0.0.0.0
SERVER_PORT=8080
LOG_LEVEL=INFO
```

**Security**: Restrict configuration file permissions:
```bash
chmod 600 .env
```

---

## Step 3: Start the Server

### Method A: Docker (Recommended)

```bash
# Build & start
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

### Method B: Direct Execution

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt

# Start
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

### Method C: Start with HTTPS (Optional)

```bash
# Generate self-signed certificate
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 30 -nodes \
  -subj "/CN=sync-demo"

# Start with HTTPS
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8443 \
  --ssl-keyfile ../key.pem --ssl-certfile ../cert.pem
```

Access via browser at `https://<IP>:8443` (accept self-signed certificate warning).

---

## Step 4: Verify Operation

### Access via Browser

```
http://<Sync Server IP address>:8080
```

### Health Check

```bash
curl http://localhost:8080/api/health
```

Expected response:
```json
{
  "status": "ok",
  "ontap_host": "management.fs-x...",
  "snapmirror_uuid_configured": true,
  "snapmirror_healthy": true,
  "snapmirror_state": "idle",
  "demo_mode": false
}
```

### Status Check

```bash
curl http://localhost:8080/api/status
```

### Manual Trigger Test

```bash
curl -X POST http://localhost:8080/api/sync
```

---

## Step 5: Access from Client Devices

1. Connect the client device (smartphone, etc.) to the same network
2. Access `http://<Sync Server IP>:8080` in a browser
3. Verify the large sync button is displayed
4. Press the button and confirm SnapMirror transfer starts

### Smartphone Tips

- Add a shortcut to the home screen for app-like access
  - iOS: Safari → Share → Add to Home Screen
  - Android: Chrome → Menu → Add to Home Screen

### Stabilizing IP Address (For Event Venues)

At event venues, DHCP may change the IP address. Countermeasures:

**Method A: mDNS (Bonjour)** — Enabled by default on macOS
```
http://<computer-name>.local:8080
```

**Method B: Set a static IP**
```bash
# macOS: System Settings → Network → Wi-Fi → Details → TCP/IP → Configure IPv4: Manually
# Linux:
sudo ip addr add 192.168.1.200/24 dev wlan0
```

**Method C: Generate a QR code** (scan with smartphone at demo start)
```bash
# With qrencode installed
qrencode -t UTF8 "http://$(hostname).local:8080"

# With Python
pip install qrcode
python3 -c "import qrcode; qrcode.make('http://192.168.1.200:8080').save('sync-qr.png')"
```

---

## Troubleshooting

### Connection Error Displayed

1. Verify the ONTAP management LIF IP address is correct
2. Confirm ping from Sync Server to ONTAP
3. Verify ONTAP REST API is enabled:
   ```bash
   # ONTAP CLI
   system services web show
   ```

### SnapMirror UUID Not Found

1. Confirm SnapMirror relationship is properly established:
   ```bash
   # ONTAP CLI
   snapmirror show -fields relationship-id
   ```

2. Check directly via REST API:
   ```bash
   curl -k -u admin:password https://<ONTAP_IP>/api/snapmirror/relationships
   ```

### Sync Times Out

- Large data changes require more time for initial sync
- Adjust `max_polls` and `poll_interval` in `backend/app/sync_manager.py`
- Typical demo size (a few MB) completes in seconds to tens of seconds

### Button Stuck on "Syncing"

```bash
# Reset state
curl -X POST http://localhost:8080/api/reset
```

---

## ONTAP User Permissions Setup (Required)

For security, create a dedicated user for SnapMirror operations:

```bash
# SSH into FSx ONTAP CLI
ssh fsxadmin@<FSx_Management_IP>

# Create SnapMirror operations role (minimum privileges)
security login role create -role snapmirror_trigger -cmddirname "snapmirror update" -access all
security login role create -role snapmirror_trigger -cmddirname "snapmirror show" -access readonly

# Create user for REST API access
security login create -user-or-group-name sync_user -application http -authentication-method password -role snapmirror_trigger
security login create -user-or-group-name sync_user -application ontapi -authentication-method password -role snapmirror_trigger
```

Set `ONTAP_USER=sync_user` in `.env`.

> ⚠️ Using `fsxadmin` directly is possible, but a dedicated user is strongly recommended
> to limit the blast radius in case credentials are compromised.
