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
# 1. Clone the repository
git clone https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns.git
cd FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/solutions/amplify-portal

# 2. Install dependencies
npm install

# 3. Create the config file (DemoMode: leave VPC/ONTAP empty)
cp amplify/portal-config.example.ts amplify/portal-config.ts

# 4. Start (sandbox and dev server come up together)
npm start
```

Open `http://localhost:5173` in a browser, register a user with Cognito, then sign in.
File browsing, AI processing and upload all work in DemoMode.
The admin and data-protection features report "ONTAP connection required".

> **For end users**: once deployment is finished, point the people who will use the portal at the
> [User Guide](../../../docs/en/portal-user-guide.md) ([日本語](../../../docs/ja/portal-user-guide.md)), or the
> [phone walkthrough](../../../docs/en/portal-mobile-guide.md) ([日本語](../../../docs/ja/portal-mobile-guide.md))
> for anyone on a handset. Both assume no knowledge of the deployment steps and cover day-to-day
> operation only. **Do not hand them this document.** What to send, and how to answer what comes back,
> is in the [handover and support guide](portal-handover-guide.en.md).

### Checking it on a real phone

**Opening a LAN address from `npm run dev -- --host` will not let you sign in.** The
portal uses `crypto.subtle` for Amplify's SRP authentication and `navigator.clipboard`
for copying share and upload links. Browsers restrict both to a **secure context**;
`http://localhost` is exempt, and `http://192.168.x.x` is not.

Serve it over HTTPS instead.

| Approach | Command | When |
|----------|---------|------|
| Deploy to Amplify Hosting | connect the branch ([Hosting guide](../../../docs/en/amplify-hosting-production-guide.md)) | to check something close to production |
| Tunnel the local server | `cloudflared tunnel --url http://localhost:5173` or similar | to see a local change on a device straight away; the URL is temporary |

> Cognito does not pin a hostname, so sign-in works either way. A tunnel URL changes on
> every run, so keep it to your own device rather than sharing it.

What to check is in [section 4 of the user
guide](../../../docs/en/portal-user-guide.md); the layout rules are under "On a phone"
in the [section guide](./portal-tabs-guide.en.md).

## Full setup (with an FSx for ONTAP connection)

### Step 1: Check the prerequisites

```bash
# Auto-discover by passing the FSx for ONTAP file system ID
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
# Check for the S3 Gateway Endpoint (usually present in a default VPC)
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=<vpc-id>" "Name=service-name,Values=com.amazonaws.<region>.s3" \
  --query "VpcEndpoints[0].{Id:VpcEndpointId,RouteTables:RouteTableIds}"

# Verify the Lambda subnets' route tables are associated with it
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=<subnet-id>" \
  --query "RouteTables[0].RouteTableId"

# Add them if they are not
aws ec2 modify-vpc-endpoint --vpc-endpoint-id <vpce-id> --add-route-table-ids <rtb-id>

# Create the Secrets Manager Interface Endpoint if it does not exist
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
  region: "ap-northeast-1",  // Region of the FSx for ONTAP file system
  s3ApAlias: "your-s3ap-alias-xxx-s3alias",  // FSx Console > S3 Access Points tab

  // VPC (required by the admin and data-protection features)
  vpcId: "vpc-0123456789abcdef0",
  vpcSubnetIds: ["subnet-0123456789abcdef0"],
  vpcSecurityGroupIds: ["sg-0123456789abcdef0"],
  // Required when vpcId is set. Give the route tables associated with vpcSubnetIds.
  // Setting vpcId without these makes synth fail; the reason is below.
  vpcRouteTableIds: ["rtb-0123456789abcdef0"],
  allowNoBlockExpiry: false,

  // ONTAP connection
  ontapMgmtIp: "172.30.x.x",  // management LIF IP
  ontapSecretName: "fsx-ontap-fsxadmin-credentials",
  ontapSvmName: "svm1",
  ontapVolumeName: "vol1",

  // ... leave the rest at their defaults
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

### Step 6: Grant administrative rights

The administrative sections (Resources, Analytics) are authorised on the Cognito group `storage-admin`. **The group itself is created by `amplify/auth/resource.ts`**, so nothing is needed by hand there, but **membership is deliberately left manual**: who holds administrative rights is not a decision for infrastructure code.

```bash
POOL=$(python3 -c "import json;print(json.load(open('amplify_outputs.json'))['auth']['user_pool_id'])")

aws cognito-idp admin-add-user-to-group \
  --user-pool-id "$POOL" --username <your-email> --group-name storage-admin
```

**Sign out and back in** afterwards. Group membership is carried in the ID token, so an existing token does not reflect it.

> Without it, the Resources and Analytics sections do not appear in the sidebar. That is deliberate: a menu that only returns authorisation errors is worse than an absent one.

### Step 7: Verify

**Check from the command line first.** Six stages have to line up before an ONTAP panel shows data, and which one is missing is not visible from the screen (for the reason below).

```bash
# From the repository root
make ontap-preflight FS_ID=<fs-id> LAMBDA=<name of ResourceMgmtFunction>
```

Once every stage passes, open the UI:

1. **File browsing**: folders appear under Browse > All Files
2. **SMB shares**: the share list appears under Admin > Resources > SMB shares
3. **Lock panel**: the tabs appear under Data Protection > Lock
4. **ARP/AI**: the protection state of each volume appears under Data Protection > ARP/AI

Leave `LAMBDA=` out and stage 6 — whether ONTAP accepts the credentials — reports **SKIP** rather than passing. The management LIF is private, so it cannot be reached from your machine; the deployed function has to make the call. Its name:

```bash
aws lambda list-functions \
  --query "Functions[?contains(FunctionName, 'ResourceMgmtFunction')].FunctionName" \
  --output text
```

> **Why not reason backwards from the screen**: with only stage 6 failing — the password in Secrets Manager and the one ONTAP held had diverged — the portal displayed "ONTAP connection required" and advice about the VPC and security groups. The volume existed and the request was reaching the cluster. The panels now classify the cause into five classes, but **immediately after a deploy it is faster to run the preflight than to open the UI**. See the [ONTAP connection guide](ONTAP-CONNECTION-GUIDE.en.md#start-with-make-ontap-preflight).

## Settings left outside the templates, and why

Everything is in infrastructure code by default, for reproducibility. These are **deliberately outside** it.

| Setting | Where it lives | Why it stays manual |
|---------|---------------|--------------------|
| Membership of `storage-admin` | `admin-add-user-to-group` | Who gets administrative rights is a per-environment decision. Creating the group is already in the templates |
| ONTAP credentials | Secrets Manager (Step 3) | So the password enters neither the repository nor a CloudFormation template |
| The S3 Object Lock bucket | Created separately (`s3ObjectLockBucket`) | Inside the portal's stack, objects under Object Lock retention would block the stack from being deleted for as long as the retention lasts. The lifecycles are kept apart |
| VPC Endpoint route-table associations | `modify-vpc-endpoint` (Step 2) | The endpoint may be shared with other stacks, and changing its associations from here has a blast radius that cannot be read locally |

> **Creating** the `storage-admin` group used to be in neither this document nor the templates. A long-running environment had one made by hand and worked; a fresh deploy lost the administrative sections. It is created by `defineAuth` now, and `make drift` checks that every group an authorization rule names is one `defineAuth` declares.

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
# Delete the sandbox entirely (CloudFormation stack and every resource)
npx ampx sandbox delete

# To delete the S3 Object Lock test bucket as well
aws s3 rb s3://fsxn-portal-objectlock-demo --force
```

## Next steps

**Once it works, the next job is handing it over.** What to send (URL, account, guide) and where to look
when a user asks something are in the
[handover and support guide](portal-handover-guide.en.md). **Do not hand this document
(Getting Started) to a user** — it is written for a different reader.

- **[Handover and support guide](portal-handover-guide.en.md)** — the three things to send, where every value lives, a reverse index from what the user said to what to check, and replies you can copy
- [PoC → Production Guide](../../../docs/en/portal-poc-to-production.md) — migration checklist from DemoMode to a production connection
- [Scaling Guide](../../../docs/en/portal-scaling-guide.md) — capacity planning and throughput management
- [Accessibility](../../../docs/en/portal-accessibility.md) — keyboard navigation, ARIA, screen reader support
- [Admin Resource Management Demo Guide](../../../docs/en/admin-resource-management-demo.md) — operating steps for every admin feature
- [AI Agent Demo Guide](./ai-agent-demo-guide.en.md) — E2E demo of the AI agent features
- [DemoMode Guide](../../../docs/demo-mode-guide.en.md) — how to verify without FSx for ONTAP
- [Section Guide](./portal-tabs-guide.en.md) — what each of the 17 sidebar sections does, theming, phone layout
- [IMPLEMENTATION.en.md](./IMPLEMENTATION.en.md) — design intent and modification log
- [Authorization Model](../../../docs/en/portal-authorization-model.md) — access control via Cognito groups
