# AgentCore MCP Gateway × Amazon Quick — Remaining Issues Tracker

> **Last updated**: 2026-07-20
> **Verified versions**: Quick Desktop v0.1000.1495 / Quick Web (ap-northeast-1) / AgentCore Gateway GA (us-east-1)

---

## Summary

| Category | Open | Resolved | Workaround |
|----------|:----:|:--------:|:----------:|
| Quick Web console | 1 | 0 | — |
| Quick Desktop | 1 | 0 | ✅ Import method |
| AgentCore Gateway auth | 1 | 0 | ✅ NONE auth |
| Lambda / Backend | 0 | 3 | — |

---

## Open Issues

### ISSUE-1: Quick Web console MCP connector creation Step 2 UI bug

| Item | Details |
|------|---------|
| **Status** | 🔴 Open — filed with AWS Support (tracked internally) |
| **Severity** | Medium (workaround available) |
| **Found** | 2026-07-19 |
| **Support Case** | filed with AWS Support (tracked internally) |
| **re:Post** | https://repost.aws/questions/QUBkeWVPpWTFiG23LggilqWw |

**Symptom**: Connectors → Create for your team → Model Context Protocol → Step 2 (Authenticate) shows "Fix highlighted fields to proceed." error, but no highlighted fields exist.

**Impact**: Cannot create MCP connectors from the Web console. Cannot link MCP tools to Chat Agents.

**Root cause**: Client-side form validation bug. No HTTP request is sent to the backend when clicking "Create and continue" (confirmed via Network tab).

**Workaround**: Add MCP servers via Quick Desktop's Import method instead.

**Resolution path**: AWS Quick team console UI fix required.

---

### ISSUE-2: Quick Desktop MCP server addition not persisted (Local / Remote methods)

| Item | Details |
|------|---------|
| **Status** | 🔴 Open — filed with AWS Support (tracked internally) |
| **Severity** | Medium (workaround available) |
| **Found** | 2026-07-20 |
| **Support Case** | filed with AWS Support (tracked internally) |
| **Community** | https://community.amazonquicksight.com/t/bug-all-remote-mcp-servers-fail-with-mcpclientinitializationerror-v0-631-0/52420 |

**Symptom**: + Create → MCP server → Local/Remote → Test connection succeeds ("Connected — 3 tools available") → + Add MCP → confirmation dialog → Add server → **MCP SERVERS section shows 0 items (not persisted)**.

**Impact**: Cannot add MCP servers via Local or Remote methods.

**Version**: v0.1000.1495 (Build 6475741731)

**Workaround**: **Import method** (load from JSON file) persists successfully.

**Resolution path**: AWS Quick Desktop team persistence logic fix required.

---

### ISSUE-3: AgentCore Gateway CUSTOM_JWT auth + Quick Desktop returns 403 Forbidden

| Item | Details |
|------|---------|
| **Status** | 🟡 Investigation needed |
| **Severity** | High (production impact) |
| **Found** | 2026-07-20 |

**Symptom**: When sending a Cognito ID Token as Bearer header to a CUSTOM_JWT Gateway, it returns 403 Forbidden. JWT `aud` claim matches the Gateway's `allowedAudience`.

**Impact**: Cannot use authenticated Gateways from Quick Desktop. PoC works with NONE auth, but production requires authentication.

**Investigated**:
- JWT claims verified: `aud`, `iss`, `sub` all correct
- Gateway RFC 9728 metadata: returns normally
- 401 → 403 transition: token is recognized but authorization denies

**Hypotheses**:
1. CUSTOM_JWT Gateway default authorization policy denies all tool invocations
2. Explicit authorization rules (policy) required beyond `allowedClients` / `allowedAudience`
3. `customClaims` mapping not configured, causing permission evaluation failure

**Next actions**:
- Investigate AgentCore Gateway policy configuration (`Use an AgentCore Gateway with Policy`)
- AWS documentation: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/use-gateway-with-policy.html

**Interim workaround**: `authorizerType: NONE` + VPC / Security Group for network-level protection.

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
| 1 | CUSTOM_JWT auth 403 issue | Must use no-auth Gateway | ISSUE-3 investigation |
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
