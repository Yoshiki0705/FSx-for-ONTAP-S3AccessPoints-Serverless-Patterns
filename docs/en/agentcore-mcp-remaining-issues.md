# AgentCore MCP Gateway × Amazon Quick — Remaining Issues Tracker

> **Last updated**: 2026-07-22
> **Verified versions**: Quick Desktop v0.1000.1495 / Quick Web (ap-northeast-1) / AgentCore Gateway GA (us-east-1)

---

## Summary

| Category | Open | Resolved | Workaround |
|----------|:----:|:--------:|:----------:|
| Quick Web console | 0 | 1 | — |
| Quick Desktop | 0 | 1 | ✅ Import method |
| AgentCore Gateway auth | 0 | 1 | ✅ Policy Engine + allowedClients |
| Lambda / Backend | 0 | 3 | — |
| **API Constraint (newly identified)** | **1** | 0 | ⚠️ Console-only |

---

## Resolved Issues

### ISSUE-1: Quick Web console MCP connector creation Step 2 UI bug

| Item | Details |
|------|---------|
| **Status** | ✅ Resolved (2026-07-21) |
| **Severity** | Medium |
| **Found** | 2026-07-19 |
| **Resolved** | 2026-07-20 (no longer reproducible) |
| **Support Case** | filed with AWS Support — resolved |
| **re:Post** | https://repost.aws/questions/QUBkeWVPpWTFiG23LggilqWw |

**Symptom**: Connectors → Create for your team → Model Context Protocol → Step 2 (Authenticate) shows "Fix highlighted fields to proceed." error, but no highlighted fields exist.

**Root cause (confirmed by AWS)**: Navigating from Step 2 back to Step 1 using "Previous" clears OAuth field values. Clicking "Create and continue" in that state triggers a validation error. Reported on re:Post as well.

**Resolution**: Re-attempted on 2026-07-20, connector created successfully. Workaround: close the wizard and restart instead of using "Previous".

---

### ISSUE-2: Quick Desktop MCP server addition not persisted (Local / Remote methods)

| Item | Details |
|------|---------|
| **Status** | ✅ Resolved (2026-07-21) |
| **Severity** | Medium |
| **Found** | 2026-07-20 |
| **Resolved** | 2026-07-20 (no longer reproducible) |
| **Support Case** | filed with AWS Support — resolved |
| **Community** | https://community.amazonquicksight.com/t/bug-all-remote-mcp-servers-fail-with-mcpclientinitializationerror-v0-631-0/52420 |

**Symptom**: + Create → MCP server → Local/Remote → Test connection succeeds → Add server → MCP SERVERS shows 0 items.

**Root cause**: Unknown. Quick Desktop is in preview and may have transient instability. AWS Support could not reproduce.

**Resolution**: Re-attempted on 2026-07-20, server persisted successfully. Likely Quick Desktop auto-update or backend state change.

**If it recurs** (AWS Support recommended info to collect):
- Timestamp (JST)
- Screen recording of the issue
- `~/Library/Logs/quickwork` logs
- Quick Desktop account ID (Manage plan → My account)
- Whether browser Connectors MCP creation works

**Recommended workaround**: Import method (JSON file) remains the most stable approach.

---

## Known Constraints (API Limitation)

### CONSTRAINT-1: MCP connector cannot be created via API (console-only)

| Item | Details |
|------|---------|
| **Status** | ⚠️ Current Limitation (confirmed 2026-07-22) |
| **Confirmed by** | AWS Support investigation + `CreateActionConnector` API documentation review |

**Details**: The `CreateActionConnector` API's `Type` parameter does not include a value for MCP. Specifying `MODEL_CONTEXT_PROTOCOL` returns `InvalidParameterValueException`.

**Impact**:
- Cannot create MCP connectors via IaC (CloudFormation / CDK)
- Cannot automate connector setup in CI/CD pipelines
- Connector configuration is not easily Git-managed or reproducible

**Workarounds**:
1. Create via Quick Web console manually (once created, it persists)
2. Use Quick Desktop Import method (JSON file-based, manageable in Git)
3. AgentCore Gateway itself IS deployable via CloudFormation/CDK — only the Quick connector is manual

**Production impact**: Connector creation is a one-time setup step. Gateway Lambda targets and auth configuration are fully IaC-manageable, so this is not a major operational blocker.

**Future expectation**: When Amazon Quick reaches GA, `CreateActionConnector` API may support MCP type.

---

### ISSUE-3: AgentCore Gateway CUSTOM_JWT auth + Quick Desktop returns 403 Forbidden

| Item | Details |
|------|---------|
| **Status** | ✅ **Resolved** (2026-07-20) |
| **Severity** | High (production impact) |
| **Found** | 2026-07-20 |

**Symptom**: When sending a Cognito ID Token as Bearer header to a CUSTOM_JWT Gateway, it returns 403 Forbidden.

**Root cause (3 combined misconfigurations)**:

1. **No Policy Engine attached**: CUSTOM_JWT Gateway defaults to deny-all on tool calls. Policy Engine + Cedar policy required.
2. **`allowedAudience` incompatible with client_credentials tokens**: Cognito `client_credentials` flow tokens do not include an `aud` claim. Remove `allowedAudience` and use `allowedClients` only.
3. **Gateway Service Role missing permissions**: Policy Engine integration requires `bedrock-agentcore:AuthorizeAction`, `PartiallyAuthorizeActions`, `GetPolicyEngine`.

**Fix (verified 2026-07-20)**:

```bash
# 1. Create Policy Engine
aws bedrock-agentcore-control create-policy-engine --name eda_mcp_policy --region us-east-1

# 2. Add Cedar permit-all policy (PoC — use IGNORE_ALL_FINDINGS)
aws bedrock-agentcore-control create-policy \
  --policy-engine-id <engine-id> \
  --name permit_all_poc \
  --definition '{"cedar":{"statement":"permit(principal, action, resource is AgentCore::Gateway);"}}' \
  --validation-mode IGNORE_ALL_FINDINGS --region us-east-1

# 3. Add permissions to Gateway service role
aws iam put-role-policy --role-name <gateway-role> --policy-name PolicyEngineAccess \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"bedrock-agentcore:*","Resource":"arn:aws:bedrock-agentcore:<region>:<account>:*"}]}'

# 4. Update Gateway (remove allowedAudience, attach policy engine)
aws bedrock-agentcore-control update-gateway --gateway-identifier <id> \
  --name <name> --role-arn <role-arn> --authorizer-type CUSTOM_JWT \
  --authorizer-configuration '{"customJWTAuthorizer":{"discoveryUrl":"...","allowedClients":["<client-id>"],"allowedScopes":["scope1"]}}' \
  --policy-engine-configuration '{"arn":"<policy-engine-arn>","mode":"ENFORCE"}'

# 5. Get M2M token (client_credentials flow)
curl -X POST "https://<domain>.auth.<region>.amazoncognito.com/oauth2/token" \
  -H "Authorization: Basic <base64(client_id:secret)>" \
  -d "grant_type=client_credentials&scope=scope1+scope2"
```

**Verification**: tools/list returns 3 tools, tools/call executes successfully.

**Production note**: Replace `permit(principal, action, resource is AgentCore::Gateway)` with scoped Cedar policies (e.g., restrict by principal claims, specific tools, or time-based conditions). Do not use `IGNORE_ALL_FINDINGS` in production.

---

## Resolved Issues

### RESOLVED-1: Lambda AgentCore input format mismatch

| Item | Details |
|------|---------|
| **Resolved** | 2026-07-19 |
| **Root cause** | Lambda handler referenced `event.toolName`, but AgentCore passes tool name in `context.client_context.custom['bedrockAgentCoreToolName']` |

**Fix**: Updated handler.py to use AgentCore format (`context.client_context.custom` for tool name, event as flat parameter dictionary).

---

### RESOLVED-2: AgentCore Gateway cannot invoke cross-region Lambda

| Item | Details |
|------|---------|
| **Resolved** | 2026-07-19 |
| **Root cause** | Gateway (us-east-1) to Lambda (ap-northeast-1) invocation is not supported |

**Fix**: Deploy Lambda in the same region as Gateway (us-east-1). S3 AP is accessible from any region (Internet-origin AP).

---

### RESOLVED-3: Quick Web connector tool detection shows only `listTools`

| Item | Details |
|------|---------|
| **Resolved** | 2026-07-19 (root cause identified) |
| **Root cause** | When creating Web connector with AWS_IAM Gateway, Quick's OAuth token and Gateway's IAM auth are incompatible. Gateway returns only `tools/list` metadata |

**Fix**: Switch to CUSTOM_JWT or NONE auth Gateway. Tool detection works correctly (3 tools confirmed via curl).

---

## Production Blockers

The following must be resolved before Quick + AgentCore MCP integration moves beyond **PoC phase** in production:

| # | Blocker | Impact | Resolution path |
|---|---------|--------|-----------------|
| ~~1~~ | ~~CUSTOM_JWT auth 403 issue~~ | ~~Must use no-auth Gateway~~ | ✅ **Resolved** (Policy Engine + allowedClients) |
| 2 | Web console MCP UI bug | Cannot link tools to Agents | AWS fix pending |
| 3 | Desktop MCP persistence bug | Only Import works | AWS fix pending |
| 4 | `CreateActionConnector` API lacks MCP type | No API-based workaround | API extension pending |

---

## Next Actions

- [ ] Await AWS Support response (2 open cases)
- [ ] Investigate and test CUSTOM_JWT Gateway + Policy configuration
- [ ] Verify if MCP persistence bug is fixed in next Quick Desktop version
- [ ] After Web console UI fix, run E2E test of Agent tool linking
- [ ] Design production auth pattern document (VPC + CUSTOM_JWT + Policy)

---

## Reference Links

| Resource | URL |
|----------|-----|
| AgentCore Gateway Policy | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/use-gateway-with-policy.html |
| Quick MCP Integration docs | https://docs.aws.amazon.com/quick/latest/userguide/mcp-integration.html |
| Quick Desktop Connectors | https://docs.aws.amazon.com/quick/latest/userguide/connections-desktop.html |
| re:Post (Web UI bug) | https://repost.aws/questions/QUBkeWVPpWTFiG23LggilqWw |
| Community (Desktop bug) | https://community.amazonquicksight.com/t/bug-all-remote-mcp-servers-fail-with-mcpclientinitializationerror-v0-631-0/52420 |
| Community (mcp-remote workaround) | https://community.amazonquicksight.com/t/tip-connecting-remote-mcp-servers-to-amazon-quick-stdio-proxy-method-tried-and-tested/52790 |
