# Getting Started — FSx for ONTAP File Portal

🌐 **Language / 言語**: [日本語](GETTING-STARTED.md) | [English](GETTING-STARTED.en.md)

> Working in 30 minutes. With DemoMode you can start without Amazon FSx for NetApp ONTAP (hereafter FSx for ONTAP).

## Prerequisites

| Item | Required | Version | Check command |
|------|:---:|---------|----------|
| AWS account | ✅ | — | Free Tier is enough. Authenticated as an IAM user or via SSO |
| Node.js | ✅ | 20.x or later | `node --version` |
| npm | ✅ | 10.x or later | `npm --version` |
| AWS CLI | ✅ | 2.x | `aws --version` |
| Amplify CLI | ✅ | latest | `npx ampx --version` |
| FSx for ONTAP | — | ONTAP 9.15+ | Not needed for DemoMode. Required for admin features |
| Docker | — | 24.x or later | `docker --version` (only when using Nextcloud) |

> **Verified environment**: this guide was verified on Node.js 20.18.x / Amplify Gen2 1.x / Python 3.12 (Lambda) / ONTAP 9.17.1 / ap-northeast-1.

## Quick start (DemoMode — without FSx for ONTAP)

```bash
# 1. リポジトリをクローン
git clone https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns.git
cd FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/solutions/amplify-portal

# 2. 依存関係インストール
npm install

# 3. 設定ファイル作成（DemoMode: VPC/ONTAP は空のまま）
cp amplify/portal-config.example.ts amplify/portal-config.ts

# 4. 起動（sandbox + dev server が同時に起動）
npm start
```

Open `http://localhost:5173` in a browser, register a user with Cognito, then sign in.
File browsing, AI processing and upload all work in DemoMode.
The admin and data-protection features report "ONTAP connection required".

> **For end users**: once deployment is finished, point the people who will use the portal at the [User Guide](../../../docs/en/portal-user-guide.md) ([日本語](../../../docs/ja/portal-user-guide.md)). It assumes no knowledge of the deployment steps and covers day-to-day operation only.

## Full setup (with an FSx for ONTAP connection)

### Step 1: Check the prerequisites

```bash
# FSx for ONTAP のファイルシステム ID を指定して自動検出
./scripts/setup-prerequisites.sh --fs-id fs-0123456789abcdef0
```

Note down the values it prints (VPC ID, subnet, SG, management IP, SVM name).

### Step 2: Check the VPC endpoints (required)

For a Lambda inside the VPC to reach AWS services, the following VPC endpoints are needed:

| Endpoint | Type | Purpose |
|----------|--------|------|
| `com.amazonaws.<region>.s3` | Gateway | S3 API (Object Lock, file operations) |
| `com.amazonaws.<region>.secretsmanager` | Interface | Retrieving ONTAP credentials |

```bash
# S3 Gateway Endpoint の確認（通常はデフォルト VPC に存在）
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=<vpc-id>" "Name=service-name,Values=com.amazonaws.<region>.s3" \
  --query "VpcEndpoints[0].{Id:VpcEndpointId,RouteTables:RouteTableIds}"

# Lambda サブネットのルートテーブルが含まれているか確認
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=<subnet-id>" \
  --query "RouteTables[0].RouteTableId"

# 含まれていない場合は追加
aws ec2 modify-vpc-endpoint --vpc-endpoint-id <vpce-id> --add-route-table-ids <rtb-id>

# Secrets Manager Interface Endpoint がない場合は作成
aws ec2 create-vpc-endpoint \
  --vpc-id <vpc-id> \
  --service-name com.amazonaws.<region>.secretsmanager \
  --vpc-endpoint-type Interface \
  --subnet-ids <subnet-id> \
  --security-group-ids <sg-id>
```

> **Security note**: if the Lambda subnet is not in the route tables of the S3 Gateway Endpoint, S3 API calls (Object Lock checks and similar) time out.

### Step 3: Register the credentials in Secrets Manager

```bash
aws secretsmanager create-secret \
  --name fsx-ontap-fsxadmin-credentials \
  --secret-string '{"username":"fsxadmin","password":"YOUR_PASSWORD_HERE"}'
```

> The `fsxadmin` password is the one set when the FSx for ONTAP file system was created.
> To change it: `aws fsx update-file-system --file-system-id <id> --ontap-configuration '{"FsxAdminPassword":"NewPassword"}'`

### Step 4: Edit portal-config.ts

```bash
cp amplify/portal-config.example.ts amplify/portal-config.ts
```

Fill in the values obtained in Step 1:

```typescript
export const config: PortalConfig = {
  region: "ap-northeast-1",  // FSx for ONTAP のリージョン
  s3ApAlias: "your-s3ap-alias-xxx-s3alias",  // FSx Console > S3 Access Points タブ

  // VPC (admin/data-protection 機能に必須)
  vpcId: "vpc-0123456789abcdef0",
  vpcSubnetIds: ["subnet-0123456789abcdef0"],
  vpcSecurityGroupIds: ["sg-0123456789abcdef0"],
  // vpcId を設定する場合は必須。vpcSubnetIds に紐づくルートテーブルを指定します。
  // 未設定のまま vpcId を設定すると synth が失敗します（理由は後述）。
  vpcRouteTableIds: ["rtb-0123456789abcdef0"],
  allowNoBlockExpiry: false,

  // ONTAP 接続
  ontapMgmtIp: "172.30.x.x",  // management LIF IP
  ontapSecretName: "fsx-ontap-fsxadmin-credentials",
  ontapSvmName: "svm1",
  ontapVolumeName: "vol1",

  // ... 他はデフォルトのまま
};
```

#### About `vpcRouteTableIds`

This is the setting that creates the DynamoDB gateway endpoint. A Lambda inside the VPC needs it to reach the containment block ledger (DynamoDB).

A Lambda ENI carries no public IP, so a subnet whose default route points at an Internet Gateway has no outbound path. Secrets Manager is reachable through an interface endpoint, but there is no route to DynamoDB. Gateway endpoints carry no hourly charge and no data processing charge.

**If you set `vpcId` and leave this unset, synth fails.** Documenting it is not enough on its own. Without the endpoint the deployment looks successful while **block expiry does not run at all**. The block is applied to the cluster, but the write to the ledger fails and the periodic sweep cannot see that block. The response returns `expiryTracked: false`, so it does not break silently, but only someone reading the response of each individual operation will notice — it never reaches an operator who assumes "blocks are released automatically".

If you intend to operate without expiry deliberately, set `allowNoBlockExpiry: true`.

Checking the route tables associated with a subnet:

```bash
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=<subnet-id>" \
  --query "RouteTables[].RouteTableId" --output text
```

A subnet with no explicit association uses the main route table of the VPC:

```bash
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=<vpc-id>" "Name=association.main,Values=true" \
  --query "RouteTables[].RouteTableId" --output text
```

### Step 5: Start it

```bash
npm start
```

The first run takes 3-5 minutes because the CloudFormation stack is created.
It is done once `Deployment completed` and `http://localhost:5173` are shown.

### Step 6: Verify

1. **File browsing**: folders appear under Browse > All Files
2. **SMB shares**: the share list appears under Admin > Resources > SMB shares
3. **Lock panel**: the tabs appear under Data Protection > Lock
4. **ARP/AI**: the protection state of each volume appears under Data Protection > ARP/AI

## What this portal assumes, and where it fits

**Audience**: anyone holding unstructured data on NAS who wants to protect and make use of that data.

| Your environment | How to use this portal |
|-----------|-------------------|
| Considering a migration from on-premises NAS | Use FSx for ONTAP + S3 AP to get browser access, AI processing and data protection |
| Already using FSx for ONTAP | Enable S3 AP and add every portal feature on top of existing data |
| NAS alongside Box / SharePoint / Google Drive | Leave the SaaS as it is. Add AI processing, auditing and protection for the NAS data |
| Running Nextcloud | Attach the S3 AP as External Storage (setup guide available) |

In a NAS-only environment it works standalone; alongside SaaS it works as an additional layer. Either fits, depending on your situation.

**Examples by industry**:
- **Financial services**: anomaly detection on trading logs + FISC 7-year audit trail
- **Manufacturing**: AI quality inspection of CAD/EDA files
- **Healthcare**: AI-assisted reading of DICOM images + HIPAA retention management
- **Media**: automatic AI metadata tagging of video assets
- **Legal**: AI classification of contract PDFs + deadline visibility
- **Research**: browser search over genomics and simulation results

### Adding a web experience to an NFS/SMB file server

The high throughput, low latency and multiprotocol support of an NFS/SMB file server stay as they are, while the following web experience is added **with no data movement**:

| What is added | How the portal delivers it |
|---|---|
| Browser access (no VPN) | S3 AP + Cognito authentication (Internet-origin) |
| Natural language file search | Bedrock Knowledge Base semantic search |
| Share links (time-limited) | Presigned URL + QR code |
| Version history and one-click recovery | Snapshot UI + FlexClone |
| Audit trail visible in the UI | CloudTrail + Athena self-service |
| Automatic AI classification and tagging | Bedrock + Step Functions, one click |
| Visibility into ransomware defence | ARP/AI dashboard |

Existing NFS/SMB workflows are unaffected. The S3 AP is an additional access path to the same volume.

## Troubleshooting

| Symptom | Cause | Action |
|------|------|------|
| `ONTAP connection not configured` | VPC/ONTAP settings are empty | Set the VPC and ONTAP values in portal-config.ts |
| `Execution timed out` (admin operation) | No Secrets Manager VPC endpoint | Add a `com.amazonaws.<region>.secretsmanager` interface endpoint to the VPC |
| `Unknown action: xxx` | Lambda code is stale | Stop the sandbox with Ctrl+C, then restart with `npm start` |
| S3 Object Lock shows "not configured" | The Lambda subnet is not in the route tables of the S3 Gateway Endpoint | `aws ec2 modify-vpc-endpoint --add-route-table-ids <rtb-id>` |
| `CDK Assembly Error` | cdk-nag is running (normally CI-only) | Delete `.amplify/artifacts` and restart |

## Production migration checklist

Items to confirm when taking this from DemoMode/sandbox to production:

| # | Item | Action |
|---|------|------|
| 1 | Least-privilege IAM | Narrow `resources: ["*"]` to concrete ARNs. See the comments in portal-config.ts |
| 2 | Separate Lambda security group | Do not share the FSx SG; create a Lambda-only SG. Outbound: TCP/443 only (ONTAP mgmt LIF IP + VPC endpoints) |
| 3 | Cognito production settings | Require MFA, strengthen the password policy, federate an external IdP (SAML/OIDC) |
| 4 | Log retention | Set `LogRetentionInDays` to match your regulatory requirement (FISC: 2557 days / 7 years, SOX: 1825 days / 5 years) |
| 5 | Enable CloudTrail | Enable data events and management events for the S3 AP ARN |
| 6 | Amplify Hosting | `amplify deploy` for production CloudFront + a custom domain |
| 7 | Add WAF | Add AWS WAF to AppSync (rate limiting, IP filtering) |
| 8 | Bedrock data residency | Check the inference region of the models you use. Nova/Claude in ap-northeast-1 infer in the same region (no cross-region transfer) |
| 9 | Enable cdk-nag | Set `CDK_NAG=1` in CI to catch new findings |
| 10 | Provisioned Concurrency | Cuts VPC Lambda cold start to 1-2 seconds (optional) |
| 11 | Disable GraphQL introspection | AppSync Console → Settings → Introspection: OFF (prevents schema disclosure) |
| 12 | CloudWatch alarms | Alarm on VPC Lambda p99 latency > 5s. Use it as the trigger for considering Provisioned Concurrency |
| 13 | Cost estimate after Free Tier | AppSync: ~$4 per million requests, Cognito: $0.0055/MAU, Lambda: $0.20 per million invocations. Rough monthly figure: $25-60 (depends on usage) |

> **Security note**: in production, separate the Lambda security group from the FSx SG. The FSx SG opens all ports (for intra-VPC traffic), whereas TCP/443 outbound alone is enough for the Lambda.

> **Data residency note**: Amazon Bedrock on-demand models (Nova, Claude) run inference in the same region as the caller. Called from ap-northeast-1, data stays within ap-northeast-1. Cross-Region Inference may send data to other regions, so restrict the `bedrock:InferenceProfile` ARN according to your regulatory requirement.

## Deleting the environment

```bash
# sandbox 環境を完全削除（CloudFormation スタック + 全リソース）
npx ampx sandbox delete

# S3 Object Lock テストバケットも削除する場合
aws s3 rb s3://fsxn-portal-objectlock-demo --force
```

## Next steps

- [PoC → Production Guide](../../../docs/en/portal-poc-to-production.md) — migration checklist from DemoMode to a production connection
- [Scaling Guide](../../../docs/en/portal-scaling-guide.md) — capacity planning and throughput management
- [Accessibility](../../../docs/en/portal-accessibility.md) — keyboard navigation, ARIA, screen reader support
- [Admin Resource Management Demo Guide](../../../docs/en/admin-resource-management-demo.md) — operating steps for every admin feature
- [AI Agent Demo Guide](./ai-agent-demo-guide.en.md) — E2E demo of the AI agent features
- [DemoMode Guide](../../../docs/demo-mode-guide.en.md) — how to verify without FSx for ONTAP
- [IMPLEMENTATION.en.md](./IMPLEMENTATION.en.md) — design intent and modification log
- [Authorization Model](../../../docs/en/portal-authorization-model.md) — access control via Cognito groups
