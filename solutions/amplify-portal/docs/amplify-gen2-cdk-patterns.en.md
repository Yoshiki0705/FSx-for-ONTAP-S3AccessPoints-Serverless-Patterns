# Amplify Gen2 + CDK Design Decision Guide

🌐 **Language / 言語**: [日本語](amplify-gen2-cdk-patterns.md) | English

> Reflects takeaways from the CDK Conference Japan 2026 session "Behavioural differences and use cases of defining CDK inside `backend.ts` in Amplify Gen2, versus not doing so".

## Decision criteria: define inside `backend.ts`, or in an external stack

In Amplify Gen2 you can reach the CDK stack through the return value of `defineBackend()` and place additional resources there. However, **packing everything into `backend.ts`** and **separating resources into an external stack** differ in deployment behaviour, dependency handling, and ease of testing.

### Resources that belong inside `backend.ts`

| Resource type | Reason |
|-------------|------|
| AppSync data source (HTTP/Lambda) | A "Data source not found" error occurs unless it lives in the same stack as the AppSync API |
| Lambda functions attached to the AppSync API | Must be in the same stack, because they are registered on the API as data sources |
| Cognito Identity Pool policy additions | Only reachable via `backend.auth.resources` |
| cdk-nag Aspects application | Applied directly to the reference obtained from `Stack.of()` |

### Resources that belong in an external stack (separate CDK app / separate template)

| Resource type | Reason |
|-------------|------|
| VPC / subnet / security group | Different lifecycle (longer-lived than the portal) |
| Amazon FSx for NetApp ONTAP file system | Infrastructure layer. Must not be affected by a portal redeployment |
| Step Functions state machine (UC patterns) | Independently deployable. The portal only references the ARN |
| DynamoDB tables (JobExecution and similar) | Managed automatically by Amplify Gen2 `defineData` |
| S3 bucket (for Athena result output) | Independent of the portal lifecycle |

### Cases this project actually ran into

#### Case 1: data source defined in a separate stack → "Data source not found"

```typescript
// ❌ FAILS: Data Source in a different stack
const infraStack = new Stack(app, "InfraStack");
const sfnDataSource = new HttpDataSource(infraStack, "SfnDS", { ... });
// → The AppSync API lives in dataStack → the resolver cannot find the data source
```

```typescript
// ✅ WORKS: Data Source in the SAME stack as AppSync API
const dataStack = Stack.of(api);
const sfnDataSource = api.addHttpDataSource("SfnDS", endpoint, { ... });
// → Same stack, so the resolver binding succeeds
```

**Root cause**: an AppSync resolver references its data source by logical ID within the CloudFormation template. A cross-stack reference cannot resolve that logical ID.

#### Case 2: placing Lambda inside a VPC → sandbox deploy exceeds 10 minutes

VPC Lambda functions (ListSnapshots and similar) take time to create and delete ENIs. They are outside the hot-swap scope of `npx ampx sandbox`, so a full deployment runs on every VPC configuration change.

**Mitigation**: make VPC Lambda optional through `process.env` and skip VPC placement in DemoMode:

```typescript
// VPC configuration is optional — only applied when env vars are set
...(process.env.VPC_ID ? {
  vpc: ec2.Vpc.fromLookup(dataStack, 'PortalVpc', { vpcId: process.env.VPC_ID }),
  securityGroups: [ec2.SecurityGroup.fromSecurityGroupId(...)],
} : {}),
```

#### Case 3: synth with environment variables unset → Lambda crashes at startup

```typescript
// ❌ The Lambda calls the API with an empty string → runtime error
environment: { ONTAP_MGMT_IP: process.env.ONTAP_MGMT_IP || "" }
```

**Mitigation**: return a fallback UI from within the Lambda code (already addressed in the VersionHistory improvement).

## Amplify Gen2 sandbox lifecycle

```
npx ampx sandbox --once
  ├── cdk synth (backend.ts → CloudFormation template generation)
  │     └── cdk-nag does NOT run (opt-in, applied only when CDK_NAG=1)
  ├── cdk deploy (applies the diff only)
  │     ├── First run: Cognito User Pool + AppSync API + Lambda x N + DynamoDB
  │     └── Subsequent runs: hot-swaps only the changed Lambda code (seconds)
  └── amplify_outputs.json generated (the configuration file the frontend loads)
```

**In scope for hot swap**: Lambda code changes, AppSync resolver code changes
**Changes that force a full deployment**: IAM policy changes, VPC configuration changes, new resources, new environment variables

> **Why cdk-nag is kept out of the sandbox deployment path**: applied always-on, findings on Amplify-managed resources produce `[AssemblyError]` and stop the deployment. In `backend.ts` it is enabled only when `CDK_NAG=1`. See [IaC Governance Patterns](iac-governance-patterns.en.md) and "cdk-nag Design Decision" in AGENTS.md.

## Recommended workflow

1. **During development**: `npx ampx sandbox` (watch mode) — Lambda code changes apply within seconds
2. **Verification**: `npx tsc --noEmit` + `npx vitest run` + `npm run build`. To look at cdk-nag, run `npm run nag` separately (not integrated into CI)
3. **Production**: `npx ampx pipeline-deploy` (the Amplify Hosting CI/CD pipeline)

## Related references

- [Amplify Gen2: Add custom AWS resources](https://docs.amplify.aws/react/build-a-backend/add-aws-services/custom-resources/)
- [CDK Conference Japan 2026 session list](https://qiita.com/issy929/items/f8c5abf9f2e327bec8da)
- [builders.flash: Getting started with CDK from Amplify Gen2](https://aws.amazon.com/jp/builders-flash/202411/cdk-introduction-with-amplify-gen2/)
