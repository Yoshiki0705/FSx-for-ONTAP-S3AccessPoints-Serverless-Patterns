# Demo Guide: Amazon Quick Desktop × AgentCore MCP Gateway × FSx for ONTAP

> ⚠️ **This demo uses a PoC configuration (no-auth Gateway).** Do not connect to volumes containing sensitive data. Production requires CUSTOM_JWT authentication + VPC protection.
>
> **Data residency note**: File content is transferred cross-region between Lambda (us-east-1) → S3 AP (ap-northeast-1).

> **Verification date**: 2026-07-19/20
> **Environment**: ap-northeast-1 (Quick + AgentCore Gateway + Lambda + S3 AP) — **same-region deployment verified 2026-07-22**
> **Status**: ✅ E2E verified

## Overview

Verified that natural language queries from Amazon Quick Desktop can browse, read, and search EDA simulation logs on FSx for ONTAP in real time via AgentCore MCP Gateway.

### Architecture

```
Amazon Quick Desktop (MCP Client)
    ↓ stdio (mcp-remote → HTTP Streamable)
AgentCore MCP Gateway (NONE auth, PoC)
    ↓ Lambda Invoke
MCP Tools Lambda (list_files / read_file / search_files)
    ↓ S3 API (ListObjectsV2 / GetObject)
FSx for ONTAP S3 Access Point
    ↓
FSx for ONTAP Volume (/eda_demo — 50 simulation logs)
```

---

## Setup Steps

### Prerequisites

- Amazon Quick Desktop v0.1000.1495+
- Node.js 22+ (`npx` available)
- AgentCore MCP Gateway deployed (see below)
- Data uploaded to FSx for ONTAP S3 AP

### Step 1: Sign in to Quick Desktop

1. Launch Quick Desktop → Region: **Asia Pacific (Tokyo)**
2. Select **"Continue with 📧" (Email)**
3. Enter your QuickSight registration email
4. Click email verification link → "Allow access" in browser
5. Automatically returns to Desktop

> **Tip**: Use Email-based sign-in, not "Continue with SSO" → IAM user. Email is the simplest path.

<!-- Screenshot: quick-desktop-signin-email.png -->

### Step 2: Create MCP config file

```json
{
  "mcpServers": {
    "EDA Log Analyzer": {
      "command": "npx",
      "args": ["-y", "mcp-remote@latest", "https://<gateway-id>.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"],
      "env": {},
      "disabled": false
    }
  }
}
```

Save the file (e.g., `~/.config/mcp-agentcore.json`)

### Step 3: Add MCP server via Import

1. Settings → Capabilities → Connectors tab
2. **+ Create** → MCP server
3. Select the **Import** tab
4. Enter the JSON file path in Config file path
5. **Load file** → "Kiro / Claude Code — 1 server found" appears
6. **Import 1 server**
7. Confirmation dialog "Allow MCP server?" → **Add server**

<!-- Screenshot: quick-desktop-import-config.png -->
<!-- Screenshot: quick-desktop-import-detected.png -->
<!-- Screenshot: quick-desktop-allow-server.png -->

### Step 4: Verify connection

Settings → Capabilities → Connectors → MCP SERVERS should show:

> **EDA Log Analyzer** — 3 tools · 3 write · **Connected**

<!-- Screenshot: quick-desktop-mcp-connected.png -->

---

## Demo Queries

### Query 1: File listing

```
List the files in eda-regression/simulation/
```

Quick's response:
- Asks "Should I use the EDA Log Analyzer MCP tool to check files on FSx?"
- After approval, MCP tool `list_files` is invoked
- **50 simulation logs** (JOB_00001_sim.log through JOB_00050_sim.log) displayed in table format
- Quick auto-analyzes: "Larger files (400–475B) may contain errors or additional information"

<!-- Screenshot: quick-desktop-tool-approval.png -->
<!-- Screenshot: quick-desktop-list-files-result.png -->

### Query 2: Investigate a failed job (recommended demo)

```
Read JOB_00005's simulation log and tell me if it passed or failed
```

Quick's response:
- Reads JOB_00005_sim.log via `read_file` tool
- **Result: FAIL** — immediately identified
- Displays formatted log output (Cadence Xcelium simulator)
- AI analysis:
  - "UVM_FATAL occurred once — `serdes_tx_scoreboard` `COMPARE_FAIL`"
  - "Expected and Actual appear to be the same value (0x000020ba) — possible scoreboard timing/sampling issue"
  - "UVM_ERROR count is 9 — additional issues present"

<!-- Screenshot: quick-desktop-read-file-approval.png -->
<!-- Screenshot: quick-desktop-read-file-result.png -->

### Query 3: Pattern search + analysis

```
Search for simulation logs with "JOB_0004" in the filename and show content previews
```

Quick's response:
- `search_files` tool searches for pattern `JOB_0004`
- **10 hits** (JOB_00040 through JOB_00049)
- Reads previews of each file and auto-organizes into a table:

| Job | Module | Sim Time | Result | Details |
|-----|--------|----------|--------|---------|
| JOB_00040 | watchdog_top | 16232 ns | ❌ FAIL | Timing violation (usb_clk, Slack: -2.92 ns) |
| JOB_00041 | clock_gen_top | 14357 ns | ✅ PASS | — |
| JOB_00042 | memory_ctrl_top | 8847 ns | ✅ PASS | — |
| JOB_00046 | clock_gen_top | 20485 ns | ❌ FAIL | ASSERTION_FAIL (UVM_ERROR: 1) |
| JOB_00048 | audio_codec_top | 29030 ns | ❌ FAIL | Timing violation (ddr_clk, Slack: -2.22 ns) |

- **Detailed failure analysis**:
  - JOB_00040: Path `watchdog/reg_q -> watchdog/mux_out`, Required: 1.50 ns / Actual: 3.29 ns / Slack: **-2.92 ns**
  - JOB_00046: `ASSERTION_FAIL` detected in `clock_gen_top`
  - JOB_00048: Path `audio_codec/reg_q -> audio_codec/mux_out`, Required: 1.50 ns / Actual: 1.43 ns / Slack: **-2.22 ns**
- Summary: **7 PASS / 3 FAIL out of 10**

<!-- Screenshot: quick-desktop-search-files-approval.png -->
<!-- Screenshot: quick-desktop-search-files-result-table.png -->
<!-- Screenshot: quick-desktop-search-files-result-detail.png -->

---

## Important Notes

### MCP server addition methods in Quick Desktop

| Method | Status | Notes |
|--------|--------|-------|
| **Import (recommended)** | ✅ Verified | Load from JSON file |
| Local (manual entry) | ⚠️ May not persist | v0.1000.1495 bug |
| Remote (direct HTTP) | ⚠️ May not persist | Same |

### Authentication method selection

| Gateway Auth | Quick Desktop Compatible | Notes |
|---|:---:|---|
| **NONE** | ✅ | PoC only. Direct connection via mcp-remote |
| CUSTOM_JWT (Cognito) | ❌ | 403 Forbidden (authorization policy investigation needed) |
| AWS_IAM | ❌ | Quick Desktop does not support SigV4 |

> **Production**: The no-auth Gateway is PoC-only. For production, use VPC-internal deployment + Security Group, or correctly configure CUSTOM_JWT authorization policy.

---

## Cleanup

```bash
# Delete AgentCore Gateway
aws bedrock-agentcore-control delete-gateway \
  --gateway-identifier <your-gateway-id> \
  --region us-east-1

# Delete Lambda
aws lambda delete-function \
  --function-name <your-stack-name>-tools \
  --region us-east-1

# Delete S3 AP (keeps the FSx for ONTAP volume)
aws fsx detach-and-delete-s3-access-point \
  --name <your-ap-name> \
  --region ap-northeast-1

# Delete Cognito User Pool
aws cognito-idp delete-user-pool \
  --user-pool-id <your-user-pool-id> \
  --region us-east-1
```

> **Tip**: If you used the deploy script, run `./scripts/deploy-agentcore-mcp.sh --cleanup --stack-name <your-stack-name>` for one-command deletion.

---

## Related Documents

| Document | Content |
|----------|---------|
| [Quick Desktop MCP Setup](quick-desktop-mcp-setup.md) | Detailed setup + IaC |
| [AgentCore MCP Tools Reference](agentcore-mcp-tools.md) | Lambda tool specifications |
| [Workshop EDA Integration Guide](../workshop-eda-integration.md) | Full workshop module mapping |
| [AWS Workshop (Module 09)](https://catalog.us-east-1.prod.workshops.aws/workshops/9cd82e0b-8348-456b-932a-818b9e5825a1/en-US/09-agentcore) | AgentCore Gateway hands-on |
