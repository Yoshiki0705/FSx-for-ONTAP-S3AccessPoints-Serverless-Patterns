# AgentCore MCP Gateway — Tool Definition Reference

> **Workshop**: [Deploy AgentCore Gateway (Module 09)](https://catalog.us-east-1.prod.workshops.aws/workshops/9cd82e0b-8348-456b-932a-818b9e5825a1/en-US/09-agentcore)
>
> **Related pattern**: [UC30 quick-agentic-workspace](../../solutions/genai/quick-agentic-workspace/README.md)

This document defines the MCP tool specifications (Lambda functions) exposed to Amazon Quick Suite via Amazon Bedrock AgentCore MCP Gateway. These tools enable Quick's agent to read EDA logs on FSx for ONTAP in real time and perform multi-step reasoning.

---

## Architecture

```
Amazon Quick Suite
    ↓ (MCP Protocol)
AgentCore MCP Gateway
    ↓ (Lambda Invoke)
MCP Tools Lambda (S3 AP operations)
    ↓ (S3 API)
FSx for ONTAP S3 Access Point
    ↓
FSx for ONTAP Volume (same data via NFS/SMB)
```

### Authentication flow

```
Quick Suite User → Cognito User Pool (OAuth 2.0) → AgentCore Gateway → Lambda
```

---

## MCP Tool Summary

| Tool name | Operation | Description |
|-----------|-----------|-------------|
| `list_files` | ListObjectsV2 | List files in a directory |
| `read_file` | GetObject | Read a specific file's content |
| `search_files` | ListObjectsV2 + filter | Search files by pattern match |

---

## Tool Definitions (MCP JSON Schema)

### 1. list_files

Browse directory structure and list files and subdirectories under the specified path.

```json
{
  "name": "list_files",
  "description": "List files and directories at the specified path on FSx for ONTAP via S3 Access Point",
  "inputSchema": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Directory path to list (e.g., 'eda-regression/simulation/' or '' for root)",
        "default": ""
      },
      "max_results": {
        "type": "integer",
        "description": "Maximum number of results to return",
        "default": 100,
        "minimum": 1,
        "maximum": 1000
      },
      "file_extension": {
        "type": "string",
        "description": "Filter by file extension (e.g., '.log', '.csv')",
        "default": ""
      }
    },
    "required": []
  }
}
```

**Lambda implementation**:

```python
import boto3

def list_files(event):
    """List files on FSx for ONTAP volume via S3 AP"""
    s3 = boto3.client("s3")
    ap_alias = os.environ["S3_AP_ALIAS"]
    prefix = event.get("path", "")
    max_results = event.get("max_results", 100)
    file_extension = event.get("file_extension", "")

    response = s3.list_objects_v2(
        Bucket=ap_alias,
        Prefix=prefix,
        MaxKeys=max_results,
    )

    files = []
    for obj in response.get("Contents", []):
        key = obj["Key"]
        if file_extension and not key.endswith(file_extension):
            continue
        files.append({
            "path": key,
            "size": obj["Size"],
            "last_modified": obj["LastModified"].isoformat(),
        })

    return {
        "files": files,
        "count": len(files),
        "truncated": response.get("IsTruncated", False),
    }
```

---

### 2. read_file

Read the content of a specified file. Targets text files (logs, CSV) so the agent can analyze content and answer user questions.

```json
{
  "name": "read_file",
  "description": "Read the content of a specific file from FSx for ONTAP via S3 Access Point",
  "inputSchema": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Full path to the file (e.g., 'eda-regression/simulation/JOB_00001_sim.log')"
      },
      "max_bytes": {
        "type": "integer",
        "description": "Maximum bytes to read (truncate large files)",
        "default": 65536,
        "minimum": 1,
        "maximum": 1048576
      },
      "encoding": {
        "type": "string",
        "description": "Text encoding",
        "default": "utf-8",
        "enum": ["utf-8", "ascii", "latin-1"]
      }
    },
    "required": ["path"]
  }
}
```

**Lambda implementation**:

```python
def read_file(event):
    """Read file content via S3 AP"""
    s3 = boto3.client("s3")
    ap_alias = os.environ["S3_AP_ALIAS"]
    path = event["path"]
    max_bytes = event.get("max_bytes", 65536)
    encoding = event.get("encoding", "utf-8")

    response = s3.get_object(
        Bucket=ap_alias,
        Key=path,
        Range=f"bytes=0-{max_bytes - 1}",
    )

    content = response["Body"].read().decode(encoding, errors="replace")
    content_length = response["ContentLength"]

    return {
        "path": path,
        "content": content,
        "size": content_length,
        "truncated": content_length > max_bytes,
        "content_type": response.get("ContentType", "text/plain"),
    }
```

---

### 3. search_files

Search for related files using pattern matching. Performs **file path-based** prefix search with regex filtering. Note: this is NOT full-text content search — to inspect file contents, enable `include_content_preview` or use `read_file` on matched results.

```json
{
  "name": "search_files",
  "description": "Search for files matching a pattern on FSx for ONTAP via S3 Access Point",
  "inputSchema": {
    "type": "object",
    "properties": {
      "pattern": {
        "type": "string",
        "description": "Search pattern — applied to file paths (e.g., 'UVM_FATAL', 'cpu_core', 'JOB_001')"
      },
      "path": {
        "type": "string",
        "description": "Directory to search within",
        "default": ""
      },
      "file_extension": {
        "type": "string",
        "description": "Filter by extension (e.g., '.log')",
        "default": ""
      },
      "max_results": {
        "type": "integer",
        "description": "Maximum matching files to return",
        "default": 20,
        "minimum": 1,
        "maximum": 100
      },
      "include_content_preview": {
        "type": "boolean",
        "description": "Include first 1KB of each matching file",
        "default": false
      }
    },
    "required": ["pattern"]
  }
}
```

**Lambda implementation**:

```python
import re

def search_files(event):
    """Search for files matching a pattern"""
    s3 = boto3.client("s3")
    ap_alias = os.environ["S3_AP_ALIAS"]
    pattern = event["pattern"]
    prefix = event.get("path", "")
    file_extension = event.get("file_extension", "")
    max_results = event.get("max_results", 20)
    include_preview = event.get("include_content_preview", False)

    # List all files under prefix
    paginator = s3.get_paginator("list_objects_v2")
    matches = []

    for page in paginator.paginate(Bucket=ap_alias, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if file_extension and not key.endswith(file_extension):
                continue
            if re.search(pattern, key, re.IGNORECASE):
                match = {
                    "path": key,
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                }
                if include_preview:
                    try:
                        resp = s3.get_object(
                            Bucket=ap_alias, Key=key, Range="bytes=0-1023"
                        )
                        match["preview"] = resp["Body"].read().decode(
                            "utf-8", errors="replace"
                        )
                    except Exception:
                        match["preview"] = "(read error)"
                matches.append(match)
                if len(matches) >= max_results:
                    break
        if len(matches) >= max_results:
            break

    return {
        "pattern": pattern,
        "matches": matches,
        "count": len(matches),
    }
```

---

## Lambda Function Configuration

### Environment variables

| Variable | Description | Example |
|----------|-------------|---------|
| `S3_AP_ALIAS` | FSx for ONTAP S3 AP Alias | `my-ap-xxxxx-ext-s3alias` |
| `AWS_REGION` | Region | `ap-northeast-1` |

### IAM Policy

```yaml
Policies:
  - Statement:
      - Sid: S3AccessPointRead
        Effect: Allow
        Action:
          - s3:GetObject
          - s3:ListBucket
          - s3:GetBucketLocation
        Resource:
          - !Sub "arn:aws:s3:::${S3AccessPointAlias}"
          - !Sub "arn:aws:s3:::${S3AccessPointAlias}/*"
          - !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3AccessPointName}"
          - !Sub "arn:aws:s3:${AWS::Region}:${AWS::AccountId}:accesspoint/${S3AccessPointName}/object/*"
```

### Lambda settings

| Item | Value |
|------|-------|
| Runtime | Python 3.12 |
| Architecture | arm64 |
| Memory | 256 MB |
| Timeout | 30 sec |
| VPC | Not required (Internet-origin S3 AP) |

---

## AgentCore MCP Gateway Configuration

### Cognito User Pool

```yaml
CognitoUserPool:
  Type: AWS::Cognito::UserPool
  Properties:
    UserPoolName: !Sub "${AWS::StackName}-agentcore-pool"
    AutoVerifiedAttributes:
      - email
    Schema:
      - Name: email
        Required: true
        Mutable: true

CognitoUserPoolClient:
  Type: AWS::Cognito::UserPoolClient
  Properties:
    UserPoolId: !Ref CognitoUserPool
    ClientName: !Sub "${AWS::StackName}-agentcore-client"
    GenerateSecret: true
    AllowedOAuthFlows:
      - client_credentials
    AllowedOAuthScopes:
      - "agentcore/read"
    AllowedOAuthFlowsUserPoolClient: true
```

### AgentCore MCP Gateway Registration

Create the AgentCore MCP Gateway using the AWS CLI:

```bash
# 1. Create Gateway (NONE auth — PoC only)
aws bedrock-agentcore-control create-gateway \
  --gateway-name "eda-mcp-noauth" \
  --protocol-type MCP \
  --authorizer-type NONE \
  --region us-east-1

# 2. Register Lambda target (with tool schema)
aws bedrock-agentcore-control create-target \
  --gateway-identifier <gateway-id> \
  --name "eda-log-tools" \
  --target-configuration '{
    "lambdaTarget": {
      "lambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:agentcore-mcp-eda-tools",
      "toolSchema": {
        "tools": [
          {"name": "list_files", "description": "List files on FSx for ONTAP via S3 AP", ...},
          {"name": "read_file", "description": "Read file content via S3 AP", ...},
          {"name": "search_files", "description": "Search files by pattern via S3 AP", ...}
        ]
      }
    }
  }' \
  --region us-east-1

# 3. Verify
curl -s https://<gateway-id>.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | jq '.result.tools | length'
# → 3
```

> **Note**: `aws bedrock-agent create-agent` is the API for Bedrock Agents (conversational agents) and is different from MCP Gateway. MCP Gateway uses the `bedrock-agentcore-control` API namespace.

---

## Knowledge Base vs AgentCore — Selection Criteria

| Criterion | Knowledge Base (Quick Index) | AgentCore (MCP) |
|-----------|------------------------------|-----------------|
| Data freshness | Depends on sync interval (minutes–hours) | Always current (real-time read) |
| Query flexibility | Vector search (semantic) | File operations (browse/read/search) |
| Multi-step reasoning | Limited (single retrieval) | Possible (sequential file reads) |
| Setup | A few clicks in console | Cognito + Lambda + Gateway |
| Cost | KB storage + sync | Lambda execution only (pay-per-use) |
| Best for | FAQ, document search, structured Q&A | Log analysis, correlation, triage |

### Recommended approach

- **Start with Knowledge Base** — set up Quick Index for basic Q&A
- **Add AgentCore** — for real-time cross-log analysis
- Both can coexist, with the agent auto-selecting the optimal approach

---

## Additional MCP Servers for the Same Gateway

Beyond this configuration (EDA Log Analyzer), you can register additional MCP servers on the same AgentCore Gateway for cross-functional use from Quick:

| Category | MCP Server | Capability |
|----------|-----------|------------|
| **AWS API** | [AWS MCP Server](https://awslabs.github.io/mcp/) | 15,000+ AWS API execution + doc search (122 tools) |
| **SAP** | AWS for SAP MCP Server | SAP BTP / S/4HANA data access |
| **Web Search** | AgentCore Web Search (Built-in connector) | Real-time web search with citations |
| **GitHub** | GitHub MCP Server | PR management, issue search, code search |
| **Jira** | Atlassian Jira Cloud | Issue creation/updates (29 actions) |
| **Slack** | Slack MCP Server | Message sending, channel management |
| **Salesforce** | Salesforce MCP Server | CRM record operations (42 actions) |
| **ServiceNow** | ServiceNow NOW Platform | Incident management (26 actions) |
| **Snowflake** | Snowflake Cortex Agent | Data warehouse queries |
| **Custom Lambda** | **This configuration (EDA Log Analyzer)** | FSx for ONTAP S3 AP file operations |

> **Example**: "Search EDA logs for UVM_FATAL, then create a Jira ticket with the failure summary" — multi-step operation combining multiple MCP servers.

---

## Performance and Throughput Considerations

> **Storage note**: S3 AP access shares the same FSx for ONTAP throughput budget as NFS/SMB.

| Item | Impact | Mitigation |
|------|--------|-----------|
| `search_files` full enumeration | Timeout risk (30s) on volumes with tens of thousands to millions of files | Always specify `path` to limit scope. Keep `max_results` at default 20 or lower |
| `read_file` Range GET (max 1MB) | Sequential reads of multiple files can burst throughput | Keep to burst usage; for batch reads use EventBridge + Step Functions pattern |
| `include_content_preview` + many hits | 1KB × N GetObject calls (N=100 = 100 requests) | Set `max_results` to 20 or less; use `read_file` individually for needed files |
| NFS/SMB workload bandwidth sharing | S3 AP latency may increase during EDA simulation runs | Run heavy MCP analysis outside business hours, or use FlexCache to isolate read load |

**Recommendation**: MCP tool reads are minimal (KB–MB per request) relative to FSx for ONTAP throughput capacity (128 MBps+). Normal usage is not a concern, but for sequential processing of many files, monitor CloudWatch `ThroughputUtilization`.

---

## Governance and Security

> **Security note**: This configuration is for PoC. Apply the following for production environments.

### Authentication & Authorization

| Layer | PoC Config | Production Recommended |
|-------|-----------|----------------------|
| Gateway | NONE (no auth) | CUSTOM_JWT + Authorization Policy |
| Lambda | IAM Role (S3 read only) | Add: IP restrictions, resource policy |
| S3 AP | File System Identity (UNIX/Windows) | Least-privilege UID/GID |

### Audit Logging

MCP tool invocations are traceable via:

- **CloudTrail**: GetObject / ListObjectsV2 via S3 AP are recorded as CloudTrail data events
- **Lambda CloudWatch Logs**: Each tool call's parameters (path, pattern) are output as structured logs
- **AgentCore Gateway logs**: Gateway access logs track the caller

### Data Region Note

In this PoC, Lambda is deployed in **ap-northeast-1** (same region as FSx for ONTAP S3 AP). This same-region deployment was verified working on 2026-07-22 — no cross-region data transfer occurs.

- **PoC / non-sensitive data**: No issue (S3 AP is Internet-origin, accessible from any region)
- **Sensitive data / compliance requirements**: Wait for AgentCore Gateway availability in ap-northeast-1, or consider VPC Peering + PrivateLink architecture

### Input Validation

Implement the following defense in your Lambda handler:

```python
import os

def validate_path(path: str) -> str:
    """Prevent path traversal"""
    normalized = os.path.normpath(path)
    if normalized.startswith("..") or normalized.startswith("/"):
        raise ValueError(f"Invalid path: {path}")
    return normalized
```

---

## Related Documents

| Document | Content |
|----------|---------|
| [Workshop EDA Integration Guide](../workshop-eda-integration.md) | Workshop module to UC pattern mapping |
| [UC30 README](../../solutions/genai/quick-agentic-workspace/README.md) | Quick Suite full integration pattern |
| [AgentCore Web Search Integration](../investigations/agentcore-web-search-fsxn-integration.md) | Web Search Tool details |
| [AD-Joined SVM Prerequisites](ad-joined-svm-s3ap-prerequisites.md) | AD configuration prerequisites |
| [S3AP Compatibility Notes](../s3ap-compatibility-notes.md) | S3 AP constraints and workarounds |
