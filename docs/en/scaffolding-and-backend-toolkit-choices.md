# Foundations for a full-stack AWS app — Nx Plugin for AWS / AWS Blocks / Amplify Gen 2

> 🌐 **Language / 言語**: [日本語](../ja/scaffolding-and-backend-toolkit-choices.md) | English

## TL;DR

- The three are **not the same layer**. Nx Plugin for AWS generates a monorepo and manages
  what runs in which order, AWS Blocks abstracts backend capabilities called from
  application code, and Amplify Gen 2 combines a backend definition, a per-developer
  sandbox and hosting. They are not replacements for one another: AWS's own documentation
  describes Blocks and Amplify as complementary.
- **This repository uses Amplify Gen 2.** The file portal (`solutions/amplify-portal/`)
  runs on a sandbox plus Amplify Hosting, and this document records that as one of the
  repository's deployment patterns, with the reasons and the conditions under which we
  would move.
- The same starting shape was built three ways and measured up to a local synth
  (2026-09-07, nothing deployed to AWS). CloudFormation resource counts for the starters:
  **Amplify Gen 2: 79 / AWS Blocks: 83 (sandbox preset), 117 (production preset) /
  Nx Plugin for AWS: 86**. Same order of magnitude — **what differs is the defaults, not
  the count**.
- Those defaults turn into **fixed cost that does not depend on traffic**. In the measured
  configuration the Nx Plugin output carries 3 WAF Web ACLs, 4 KMS customer managed keys
  and the Cognito Plus plan, which at published ap-northeast-1 rates is **$25+/month**
  before any traffic. The Blocks production preset comes to **$1** (one key), and the
  Amplify starter to **$0**. Not better or worse: a choice between a production-leaning
  starting point and an environment that is easy to tear down.
- How to choose is in [Choosing](#choosing). Building one app once is the case where Nx's
  value has not appeared yet; a repository that keeps accumulating websites, APIs, data
  projects, agents and IaC is where its graph pays off. Blocks is the local-first option
  (in preview). Amplify Gen 2 is the one that keeps auth, backend and hosting together.

## Scope

**Covered**: how the three differ in layer, measured resource counts for an equivalent
starting shape, the differences in generated defaults, the fixed cost those defaults imply,
the conditions that select each one, and why this repository uses Amplify Gen 2.

**Not covered**: which one is best. Benchmarks — no performance measurement was taken.
A comparison of production track records (of the three, only Amplify Gen 2 has one in this
repository). AWS Blocks after general availability — the measurements here are from preview.

**Audience**: anyone choosing a foundation for a full-stack app on AWS, anyone already on
one of the three who wants grounds for moving, and anyone asking why this repository's
portal is Amplify Gen 2.

## Where each one sits

| | Primary concern | What it leaves you with | Status (as of 2026-09-07) |
|---|---|---|---|
| Nx Plugin for AWS | Generating a monorepo, connecting projects, managing execution order | Ordinary React / tRPC / ElectroDB / CDK code | v1.0 (released 2026-09, open source) |
| AWS Blocks | Backend capabilities called from application code, with a local implementation and an AWS one | A CDK app; each Block has a runtime API | **preview** (announced 2026-06-17, open source) |
| Amplify Gen 2 | Backend definition, developer sandbox and hosting as one | A TypeScript backend definition (`defineAuth` / `defineData`) plus CDK | Generally available |

That they are not replacements is documented rather than inferred. The AWS Blocks overview
describes the relationship with Amplify as **complementary**: Amplify provides hosting,
CI/CD and a managed backend experience, while Blocks focuses on type-safe
infrastructure-from-code with local-first development. The Amplify documentation carries a
page on Blocks in turn.

For the same reason Nx Plugin for AWS is not exclusive with either. What Nx manages is the
generation and execution order of a repository holding several projects, and what it
generates is ordinary CDK code.

## What this repository chose

**The file portal is built with Amplify Gen 2, and it is treated as one of the
repository's deployment patterns.** Saying so explicitly matters because every other
pattern under `solutions/` is a SAM/CloudFormation template deployable on its own, while
the portal alone uses an Amplify sandbox and CDK inside `amplify/backend.ts` — a different
shape, and one that should read as deliberate.

Three reasons, all specific to this repository's constraints.

1. **Authorization is central to the requirements.** The portal uses Cognito groups on two
   axes (role and scope), and the AppSync authorization rules name those groups.
   `defineAuth` and `defineData` express the groups and the rules in one place, which is
   the shortest way to write this shape.
2. **Per-developer sandboxes were needed.** The portal includes VPC Lambdas that reach an
   ONTAP management LIF, so verification does not close locally. An independent environment
   per `ampx sandbox` identifier is what makes it possible to try things without breaking a
   shared one.
3. **There is a way out to CDK.** The portal builds FSx for ONTAP S3 Access Point access,
   Step Functions, Bedrock and DynamoDB as CDK inside `backend.ts`. Writing outside what
   Amplify manages was a requirement, not a nicety.

**Conditions that would prompt a move** (for this repository):

- Websites and APIs accumulate beyond the portal, and dependencies and execution order stop
  fitting in `package.json` scripts → the Nx Plugin for AWS dependency graph
- A decision to move authentication off Cognito → the Blocks `AuthBasic` / `AuthOIDC` become
  candidates
- Local-only iteration becomes the dominant factor in development speed → the Blocks local
  implementations

None of these holds today, so there is no plan to move.

## Measurements

The same starting shape (web frontend + API + data store + auth + IaC) was built three
ways and measured **up to a local synth**. **Nothing was deployed to AWS**, so these are
measurements of templates rather than of running configurations.

Environment: macOS, Node.js v26.4.0, npm 11.17.0, taken 2026-09-07.

| | How it was generated | Stacks | CloudFormation resources |
|---|---|---|---|
| Amplify Gen 2 | `npm create amplify` (the `defineAuth` + `defineData` starter) | 5 (including nested) | **79** |
| AWS Blocks (preview) | `npm create @aws-blocks/blocks-app` (todo app), `BlocksPresets.sandbox` | 1 | **83** |
| AWS Blocks (preview) | same, `BlocksPresets.production` | 1 | **117** |
| Nx Plugin for AWS 1.0 | `ts#website` + `ts#website#auth` + `ts#api --framework=trpc` + `ts#dynamodb` + `connection` ×2 + `ts#infra`, with only the generated `echo` procedure | 2 | **86** |

> **Not the same ruler**: the three starters do not produce the same application (Amplify a
> GraphQL Todo, Blocks a Todo with authentication, Nx a Welcome page and an echo API). What
> is being compared is the scale of what appears in the template right after following each
> project's own getting-started path — not one application implemented three times.

### What the Nx Plugin run showed

- **`ApplicationStack` is empty immediately after `ts#infra`.** Synthesised in that state
  the template holds a single resource (CDK metadata). The 86 came after placing the
  generated constructs (`FeedbackWeb` / `FeedbackApi` / `FeedbackData` / `UserIdentity`) in
  `ApplicationStack` and writing the IAM grants and CORS by hand. The generators produce
  reusable constructs; which ones to adopt and how to connect their permissions stays a
  design decision.
- 7 Nx projects (`common-constructs`, `common-scripts`, `common-shadcn`, `feedback-web`,
  `feedback-api`, `feedback-data`, `infra`).
- `infra:synth` runs the bundles and compiles it depends on first: 13 tasks in 5.1 s as nx
  reported it, with 7 of 13 served from cache.
- One business Lambda (the `echo` procedure). Of the 7 Lambda functions in the template the
  rest are CDK custom resources. Adding procedures adds Lambdas and API Gateway methods.

### Differences in the generated defaults

Taken from the measured templates, limited to what bears on fixed cost and on tearing an
environment down.

| | Amplify Gen 2 (starter) | AWS Blocks (production preset) | Nx Plugin for AWS |
|---|---|---|---|
| WAF Web ACLs | none | none | **3** (2 REGIONAL + 1 CLOUDFRONT), 2 managed rules each |
| KMS customer managed keys | none | 1 (for the alarm topic) | **4**, all with automatic rotation |
| Authentication | Cognito user pool; `UserPoolTier` unset (so the `ESSENTIALS` default) | `AuthBasic` (DynamoDB + JWT); no Cognito | Cognito user pool; **`UserPoolTier: PLUS`**, MFA `ON`, threat protection `AUDIT` |
| User pool deletion protection | unset | — | `ACTIVE` |
| DynamoDB | through `Custom::AmplifyDynamoDBTable` | 4 tables, all with deletion protection and `Retain`; the two application tables have PITR and SSE, the two auth tables have neither | 1 table with PITR, deletion protection, SSE with a CMK, 2 GSIs and `Retain` |
| S3 bucket `DeletionPolicy` | `Delete` (starter) | `Delete` | — |
| Anonymous telemetry | on by default (`ampx configure telemetry disable`) | on by default (`AWS_BLOCKS_DISABLE_TELEMETRY=1`) | (not measured) |

Neither thicker nor thinner is the right answer. **The Nx Plugin defaults are a reassuring
production starting point, and in a short-lived environment the deletion protection and
`Retain` make cleanup harder.** The Amplify starter is the reverse: easy to remove, with
work left before production. Blocks puts the choice in a preset, which is what separates 83
from 117.

## The fixed-cost difference

The part of those defaults that is charged with no traffic at all, at published rates.

Source: AWS Price List API, region **ap-northeast-1**, retrieved **2026-09-07** (the API's
`publicationDate` is 2026-09-11; the Cognito rates are effective 2026-08-01).

| Item | Rate |
|---|---|
| WAF Web ACL | $5.00/month (ap-northeast-1; us-east-1 is the same) |
| WAF rule | $1.00/month |
| WAF request processing | $0.60 per million requests |
| KMS customer managed key | $1.00/month. **The first and second rotation each add $1.00/month, and it is capped at the second** (subsequent rotations are not billed) |
| Cognito MAU (Lite) | $0.0055 (first 90,000 MAU) |
| Cognito MAU (Essentials) | $0.015 |
| Cognito MAU (Plus) | $0.020 |

Applied to a sample assumption of **1,000 monthly active users and no traffic**:

| | WAF | KMS | Cognito (1,000 MAU) | Total |
|---|---|---|---|---|
| Amplify Gen 2 (starter) | $0 | $0 | $15.00 (Essentials) | **$15.00** |
| AWS Blocks (production preset) | $0 | $1.00 | $0 (no Cognito) | **$1.00** |
| Nx Plugin for AWS | $21.00 (3 ACLs × $5 + 6 rules × $1) | $4.00, rising to at most $12.00 after two rotations | $20.00 (Plus) | **$45.00, up to $53.00** |

> **This is a sample estimate, not a production one.** It excludes everything proportional
> to traffic — Lambda, API Gateway, DynamoDB, CloudFront, S3, Bedrock — along with
> CloudWatch Logs retention, data transfer, the free tier, Savings Plans and agreement-based
> discounts. A real bill is decided by the workload. What is shown here is only how much the
> difference in defaults costs every month while nothing is being used.
>
> The Cognito free tier is not applied; a new account may see less than the figures above.

Three things worth keeping straight:

- **KMS rotation does not grow without bound.** The cap is reached at the second rotation,
  so a rotating CMK settles at $3.00/month. With annual rotation, four keys go $4 → $8 →
  $12 over two years and stop.
- **The CloudFront-scoped Web ACL is created in us-east-1**, at the same published rate.
- **The default for an unspecified Cognito `UserPoolTier` is `ESSENTIALS`** (confirmed in
  the AWS documentation). The Nx Plugin output names `PLUS` in order to enable features such
  as threat protection; the difference is $5/month at 1,000 MAU and $50/month at 10,000.
  It can be lowered if the requirements allow.

## Choosing

Start from whichever conditions hold. If several do, they can be combined — the three are
not exclusive.

**Nx Plugin for AWS fits when**

- websites, APIs, data projects, AI agents, MCP servers and CDK/Terraform will **keep
  accumulating in one repository**
- you want "what depends on what, and what runs first" held in a dependency graph rather
  than in individual shell scripts
- you can take on the generated code as yours to maintain (ordinary React / TypeScript / CDK
  rather than a closed format is an advantage, but the update policy is yours to set)

**It fits less well when** you are generating one app once. The problem the graph solves has
not appeared yet.

**AWS Blocks fits when**

- **local iteration without an AWS account** is the dominant factor in development speed
- you want to call backend capabilities (key-value store, table, realtime, jobs, agents)
  from application code with types
- you can accept **preview**. The interface may change, and the documentation states that
  renaming a Block ID deletes and recreates the corresponding resource, which for stateful
  Blocks means **permanent data loss** (treat Block IDs as immutable once deployed)

**Amplify Gen 2 fits when**

- authentication (Cognito groups, external IdPs, MFA) is central to the requirements
- per-developer sandbox environments are needed
- frontend hosting should live in the same framework
- you need to write outside what Amplify manages, reaching the CDK stacks through the return
  value of `defineBackend()`

**It fits less well when** several independent applications grow side by side in one
repository. An Amplify sandbox is scoped to one backend, so cross-project execution order
needs handling elsewhere.

## Trade-offs

Stated symmetrically, including for the option this repository uses.

| | Strengths | Trade-offs |
|---|---|---|
| Nx Plugin for AWS | Production-leaning defaults (WAF, KMS, deletion protection, observability) from the start. Dependencies and execution order hold as projects accumulate. The output is ordinary React and CDK | Not a working application when generated (Welcome page, echo, sample entity). The final IaC wiring remains a design decision. Highest fixed cost. Deletion protection and `Retain` make short-lived environments harder to clear. The update policy for generated code is yours |
| AWS Blocks | The whole app runs locally with no AWS account. Types carry from backend to UI. You can drop to CDK. Composes with Amplify and with existing CDK | **Preview.** Renaming a Block ID is permanent data loss for stateful Blocks. Local and AWS implementations are not identical, so integration still has to be verified against AWS. Telemetry on by default |
| Amplify Gen 2 | Backend definition, sandbox and hosting as one. Auth and data authorization in one place. A way out to CDK. A production-grade track record in this repository | An attempt to update an existing Cognito user pool through CloudFormation was refused by Cognito on 2026-08-27, and the way round it — a new pool — lost the users (the record and the conditions are in the design-decisions guide below). A failed sandbox stops with what it created still in place. Some cdk-nag findings come from Amplify-managed resources, so it is run as a baseline comparison rather than as a pass/fail gate. Telemetry on by default |

The Amplify Gen 2 trade-offs are covered in detail in
[Amplify Gen2 + CDK design decisions](../../solutions/amplify-portal/docs/amplify-gen2-cdk-patterns.en.md)
and [IaC governance patterns](../../solutions/amplify-portal/docs/iac-governance-patterns.en.md).

## Reproducing the measurements

How to get the same numbers on your own machine. **None of this deploys to AWS** — synth only.

```bash
# Nx Plugin for AWS
#   `npm create @aws/nx-workspace` stalled with no output, so this goes through pnpm
npx --yes pnpm@10 create @aws/nx-workspace@1.0.0 research-board \
  --interactive=false --pm=pnpm --nxCloud=skip --skipGit --aiAgents=none
cd research-board
NX=node_modules/.bin/nx          # `npx pnpm` stalls on a version confirmation prompt
$NX g @aws/nx-plugin:ts#website feedback-web --no-interactive
$NX g @aws/nx-plugin:ts#website#auth --project=@research-board/feedback-web --no-interactive
$NX g @aws/nx-plugin:ts#api feedback-api --framework=trpc --no-interactive
$NX g @aws/nx-plugin:ts#dynamodb feedback-data --no-interactive
$NX g @aws/nx-plugin:connection --sourceProject=@research-board/feedback-web \
  --targetProject=@research-board/feedback-api --no-interactive
$NX g @aws/nx-plugin:connection --sourceProject=@research-board/feedback-api \
  --targetProject=@research-board/feedback-data --no-interactive
$NX g @aws/nx-plugin:ts#infra infra --no-interactive
# Place the constructs in ApplicationStack here; left empty it synthesises one resource
NX_TUI=false $NX sync && NX_TUI=false $NX run @research-board/infra:synth
```

```bash
# AWS Blocks (preview)
npm create @aws-blocks/blocks-app@latest my-todo-app
cd my-todo-app && npm install
npx --yes aws-cdk synth --context sandboxMode=true --output out-sandbox --quiet
npx --yes aws-cdk synth --output out-prod --quiet
```

```bash
# Amplify Gen 2
npm create amplify@latest
CDK_OUTDIR=out CDK_CONTEXT_JSON='{"amplify-backend-name":"probe","amplify-backend-namespace":"probe","amplify-backend-type":"sandbox"}' \
  npx --yes tsx amplify/backend.ts
```

Counting resources (summing the keys under `Resources` in each template):

```bash
find <output-dir> -name '*.template.json' -exec node -e \
  'const t=require(process.argv[1]);console.log(Object.keys(t.Resources||{}).length)' {} \;
```

To synthesise this repository's portal the same way, use `npm run nag` in
`solutions/amplify-portal`. It synthesises against the committed
`portal-config.example.ts` and sends nothing to AWS.

## FAQ

**Q. Does one of the three have to be chosen?**
No. AWS documents Blocks and Amplify as complementary, and a Blocks app is a CDK app, so it
can be embedded in an existing CDK stack. What the Nx Plugin generates is ordinary CDK too.
In practice a repository structured with Nx, one of whose projects is Amplify Gen 2, is a
valid shape.

**Q. Are fewer resources better?**
It is one input among several. Most of the gap between 79 and 117 is protection that arrives
by default — encryption, monitoring, hosting — and the smaller number leaves that work to be
added later. What matters is not the count but **whether those defaults match your
organisation's standard**.

**Q. The portal in this repository is 472 resources. Does that make Amplify heavy?**
No. The portal is a working application with 78 AppSync resolvers, 24 Lambda functions and
6 DynamoDB tables. It is not comparable to a starter's 79. The figure is here precisely so
that **472 is not placed in the starter comparison row**.

**Q. Can the Nx Plugin's Cognito Plus plan be lowered?**
Yes — it is a setting on a generated construct. Features only available on Plus, threat
protection among them, are enabled by default, so check what is lost before lowering it.
Treat the generated defaults as something to review rather than to inherit.

**Q. Is AWS Blocks ready for production?**
As of 2026-09-07 it is in preview, and the documentation warns that renaming a Block ID is
permanent data loss for stateful Blocks. Decide on whether the preview terms are acceptable.
This repository does not use it for production-grade purposes.

## Sources

- [AWS announces Nx Plugin for AWS for scaffolding full-stack applications](https://aws.amazon.com/about-aws/whats-new/2026/09/nx-plugin-for-aws/) (What's New, 2026-09)
- [awslabs/nx-plugin-for-aws](https://github.com/awslabs/nx-plugin-for-aws) and its
  [documentation](https://awslabs.github.io/nx-plugin-for-aws/)
- [What is AWS Blocks?](https://docs.aws.amazon.com/blocks/latest/devguide/what-is-blocks.html),
  [Getting started](https://docs.aws.amazon.com/blocks/latest/devguide/getting-started.html),
  [AWS Blocks concepts](https://docs.aws.amazon.com/blocks/latest/devguide/concepts.html) (Block ID immutability)
- [AWS Blocks (preview) announcement](https://aws.amazon.com/about-aws/whats-new/2026/06/aws-blocks-preview/) (2026-06-17)
- [AWS Amplify Gen 2 documentation](https://docs.amplify.aws/) and
  [AWS Blocks as seen from Amplify](https://docs.amplify.aws/nextjs/build-a-backend/aws-blocks/)
- [AWS Key Management Service pricing](https://aws.amazon.com/kms/pricing/) (the rotation cap)
- [Cost and billing management best practices for AWS KMS](https://docs.aws.amazon.com/prescriptive-guidance/latest/aws-kms-best-practices/cost.html)
- `UserPoolTier` defaulting to `ESSENTIALS`:
  [AWS CDK API reference (CfnUserPoolProps)](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cognito-readme.html)
- Rates retrieved from the AWS Price List API on 2026-09-07 (ap-northeast-1)
- An article that generated and verified Nx Plugin for AWS in practice, by a Solutions
  Architect at AWS Japan:
  [AWSアプリ開発の初手が変わる？ Nx Plugin for AWSは何を自動化し、何を人に残すのか](https://zenn.dev/aws_japan/articles/nx-plugin-for-aws-nx-explained).
  The division of labour between the generators, the fact that `connection` behaves
  differently per pair, and that maintaining the generated code becomes your own
  responsibility are drawn from it. The figures in this document were measured
  independently here and do not match that article's, because the configurations differ:
  it implements three procedures, this one keeps only the generated `echo`.

> Content was rephrased for compliance with licensing restrictions.

## Related documents

- [Amplify Gen2 + CDK design decisions](../../solutions/amplify-portal/docs/amplify-gen2-cdk-patterns.en.md) — what belongs inside `backend.ts` and what does not
- [IaC governance patterns](../../solutions/amplify-portal/docs/iac-governance-patterns.en.md) — why cdk-nag is not a gate here, and the alpha-module policy
- [Portal Getting Started](../../solutions/amplify-portal/docs/GETTING-STARTED.en.md) — deploying into another environment
- [PoC to production](portal-poc-to-production.md) — moving a sandbox configuration toward production
