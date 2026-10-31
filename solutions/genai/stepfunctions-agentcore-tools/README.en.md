# Step Functions × AgentCore Gateway — Workflows as AI Agent Tools

🌐 **Language / 言語**: [日本語](README.md) | English | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

A sample that exposes a Standard Step Functions workflow (Discover → Process → Report)
over files on FSx for ONTAP S3 Access Points as AI agent tools, through the built-in
Step Functions connector of Amazon Bedrock AgentCore Gateway.

The agent decides when to run the workflow and what input to pass; the state machine
owns the ordered steps. Keep the approved sequence in the workflow, leave the launch
decision to the agent.

## Use Cases

- Trigger an existing Step Functions workflow from an agent without changing the state machine
- Keep the steps and approvals in the workflow, delegate only the run decision to the agent
- Let the agent inspect how far an execution progressed from the execution history

## Architecture

```
AI agent ──MCP──▶ AgentCore Gateway (Step Functions connector)
                       │ GatewayServiceRole → states:StartExecution etc.
                       ▼
              Standard StateMachine (Discover→Choice→Map→Report)
                       │
          Discovery / Processing / Report Lambda
                       │
                 S3 Access Point (FSx for ONTAP / regular S3 in DemoMode)
```

See [docs/architecture.md](docs/architecture.md) for details.

## Tools exposed

| Tool | Input | Purpose |
|---|---|---|
| `workflow___StartExecution` | `input` (JSON string) | Start the workflow |
| `workflow___ListExecutions` | `statusFilter` (optional) | List executions (Standard only) |
| `workflow___DescribeStateMachine` | `includedData` (optional) | State machine metadata/definition |
| `workflow___DescribeExecution` | `executionArn`, `includedData` | Check status and result |
| `workflow___GetExecutionHistory` | `executionArn` | Step history |

The pinned state machine ARN never appears in the tool schema, and the agent cannot change it.

## Parameters

| Parameter | Description | Default |
|---|---|---|
| `S3AccessPointAlias` | S3 AP alias for the FSx for ONTAP volume (regular bucket name in DemoMode) | (required) |
| `DemoMode` | `true` runs without FSx for ONTAP (regular S3 bucket) | `false` |
| `FilePrefix` | Prefix to scan | `input/` |
| `BedrockModelId` | Summarization model / inference profile ID ([docs/bedrock-inference-profiles.md](../../../docs/bedrock-inference-profiles.md)) | `apac.amazon.nova-pro-v1:0` |
| `MaxFilesPerExecution` | Max files per execution | `100` |
| `NotificationEmail` | SNS notification target (empty to skip) | `""` |
| `GatewayName` | Gateway name (used by the deploy script) | `sfn-agentcore-tools-gateway` |

## Deploy

The Gateway and the Step Functions connector target are first-class CloudFormation
resources (`AWS::BedrockAgentCore::Gateway` / `GatewayTarget`), so the whole pattern
is one declarative template. The deploy script is a thin `sam build` + `sam deploy`
wrapper that verifies `tools/list` afterward.

```bash
# DemoMode (no FSx for ONTAP)
./scripts/deploy-stepfunctions-agentcore.sh \
  --s3ap-alias my-demo-bucket --demo-mode --stack-name sfn-agentcore-tools-demo

# Production (S3 AP)
./scripts/deploy-stepfunctions-agentcore.sh \
  --s3ap-alias <your-ap>-ext-s3alias --stack-name sfn-agentcore-tools

# Cleanup
./scripts/deploy-stepfunctions-agentcore.sh --cleanup --stack-name sfn-agentcore-tools
```

Conversation examples and verification steps are in [docs/demo-guide.md](docs/demo-guide.md).

## Human Review thresholds

The Processing Lambda scores summarization confidence with `shared/human_review.py`.

| Confidence | Decision |
|---|---|
| `>= 0.85` (default `HUMAN_REVIEW_AUTO_APPROVE_THRESHOLD`) | AUTO_APPROVE |
| `>= 0.30` (default `HUMAN_REVIEW_REJECT_THRESHOLD`) and `< 0.85` | HUMAN_REVIEW |
| `< 0.30` | REJECT |

Thresholds are overridable via environment variables. The decision is carried in the
result; this pattern does not act on it automatically.

## Data classification

The Report Lambda labels output with `data_classification` from
`shared/data_classification.py` (default `INTERNAL`, override via `DATA_CLASSIFICATION`).

## Governance Note

- The agent only decides when to run and checks status. The order, branching, and
  approvals are owned by the state machine; the agent cannot skip or reorder them.
- The pinned state machine ARN is not exposed, so the agent cannot start a different one.
- AI summarization/classification is an **assistive signal**, not a final decision.
  Confidence below the threshold routes to human review.
- Task-token operations (`SendTaskSuccess`, etc.) are not exposed here, because IAM
  cannot scope them to specific executions.
- This is governance guidance, not legal or compliance advice.

## Tests

```bash
python3 -m pytest solutions/genai/stepfunctions-agentcore-tools/tests/ -v
```

## Known gotchas

Same-region constraint, one pin per operation, the Japanese `?` mojibake and the
`\uXXXX` workaround, and the Cedar `input` limitation are collected in
[docs/demo-guide.md](docs/demo-guide.md).

## References

- [AWS Step Functions as Connector Target (official)](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-step-functions.html)
- [AWS Step Functions workflows now available as AI agent tools (What's New)](https://aws.amazon.com/about-aws/whats-new/2026/10/step-functions-workflows-ai-agent-tools/)

---

<!-- playbook-reading:start -->
## Read before going to production

How the constraints that surface after deploying translate into design decisions is covered in the [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook). The same content in two places means the copy that stops being updated outlives the one that was corrected.

- [Data Utilization](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-utilization) — constraints of reaching data through an access point (every pattern)
- [Security & Governance](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/security-governance) — where the decisions concentrate for this pattern
- [Build](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/04-build) — run through before production (every pattern)
<!-- playbook-reading:end -->
