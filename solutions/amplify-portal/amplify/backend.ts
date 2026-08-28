import { defineBackend } from "@aws-amplify/backend";
import { auth } from "./auth/resource";
import { data } from "./data/resource";
import { config } from "./portal-config";
import {
  DIRECT_S3_BY_GROUP,
  S3_READ_ACTIONS,
  directS3Problems,
  scopeS3ApArns,
} from "./direct-s3-access";
import { validateAuthorizationConfig } from "./validate-authorization-config";
import * as crypto from "crypto";
import * as fs from "fs";
import * as path from "path";
import { spawnSync } from "node:child_process";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as s3 from "aws-cdk-lib/aws-s3";
import { AssetHashType, Aws, Duration, RemovalPolicy, Stack, Validations } from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import * as cloudwatchActions from "aws-cdk-lib/aws-cloudwatch-actions";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
import * as sns from "aws-cdk-lib/aws-sns";
import * as subscriptions from "aws-cdk-lib/aws-sns-subscriptions";
import { AwsSolutionsChecks } from "cdk-nag";

/**
 * FSx for ONTAP File Portal — Amplify Gen2 Backend
 *
 * Architecture:
 *   defineAuth (Cognito + SAML/OIDC)
 *   defineData (AppSync GraphQL API)
 *     → HTTP Data Source → Step Functions API (StartExecution, DescribeExecution)
 *     → Lambda Data Source → ListFiles Lambda → S3 AP
 *
 * Configuration is loaded from ./portal-config.ts.
 * Copy portal-config.example.ts → portal-config.ts and set your values.
 *
 * Key lessons from deployment verification:
 *   1. Data sources MUST be added to the same CDK stack as the AppSync API
 *      (cross-stack references cause resolver binding failures)
 *   2. APPSYNC_JS resolvers cannot use: new Date(), template literals,
 *      or global constructors — use util.* and string concatenation
 *   3. Step Functions DescribeExecution returns epoch seconds (not ISO 8601)
 *      — conversion must happen on the frontend
 */
const backend = defineBackend({
  auth,
  data,
});

/*
 * The Upload tab needs the S3 AP alias in the browser, because Storage Browser
 * calls S3 directly with Cognito Identity Pool credentials instead of going
 * through a Lambda. It used to read that alias from `src/portal-settings.ts`,
 * which is committed -- so the file held a placeholder alias, the placeholder
 * was what shipped, and every upload failed against an access point that does
 * not exist. Publishing it here puts the value in `amplify_outputs.json`, which
 * `npx ampx sandbox` generates and .gitignore excludes, so the alias has one
 * source (`portal-config.ts`) and an unconfigured clone has none rather than a
 * wrong one.
 */
backend.addOutput({
  custom: {
    s3ApAlias: config.s3ApAlias,
    region: config.region,

    // The authorization policy, published so the browser can describe what the account
    // may do rather than infer it. Without this the UI would have to hardcode a guess at
    // the server's rules, and a guess that drifts is worse than no gating: it hides
    // controls that work, or offers controls that cannot.
    //
    // None of it is a secret and none of it is a control. The server decides -- AppSync
    // group rules for the roles, the handlers for the external scope. This only lets the
    // UI say why something is unavailable instead of failing when it is used.
    enforceRoles: String(config.enforceRoles),
    externalAiEnabled: String(config.externalDefaults.aiEnabled),
    // Serialised, because custom outputs are a flat map of strings.
    externalShareLinksByRole: JSON.stringify(config.externalDefaults.shareLinksByRole),
  },
});

// --- Storage Browser IAM: Add S3 AP access to Cognito Identity Pool authenticated role ---
// This ensures the Upload tab (Storage Browser for S3) can access the S3 AP
// directly from the browser without manual IAM configuration.
const authResources = backend.auth.resources;

// --- Who may create an account ---
//
// `defineAuth` has no field for this, and the construct's own default is to allow it
// (`ALLOW_SELF_SIGN_UP: true` in @aws-amplify/auth-construct), so reaching the L1 is the
// only way to express the other answer. Left alone, anybody who can reach the sign-in
// page can register with a verified email address, and while `enforceRoles` is false a
// registered user can upload and delete.
//
// A property override rather than assigning `adminCreateUserConfig` wholesale: the
// construct may set an invitation message template in the same object, and replacing it
// would drop that without any error.
// A note for anybody who meets a failed user pool update here.
//
// Measured 2026-08-27 against a pool created 2026-08-11: **an existing Amplify user pool
// cannot be updated through CloudFormation at all.** Any property change triggers an update
// that Cognito refuses in two stages:
//
//   Without `AttributeDataType` on the `Schema` entries -- which is how the construct emits
//   them, since Cognito infers it at create time -- the update fails with "Invalid
//   AttributeDataType input". CloudFormation surfaces this as "User pool attributes cannot
//   be changed after a user pool has been created", which reads as a restriction on what may
//   change rather than as a malformed request.
//
//   Adding `AttributeDataType` explicitly gets past that and fails with "Required custom
//   attributes are not supported currently", because on an update Cognito reads `Schema` as
//   attributes to *add*, and a required attribute cannot be added. Re-sending the schema the
//   pool already has is therefore invalid by construction.
//
// So there is no override that makes an existing pool updatable, and one was tried and
// removed rather than left here looking like a fix. Amplify's own resolution -- remove
// `defineAuth`, deploy, add it back -- deletes every user in the pool, as does recreating the
// sandbox. A new deployment is unaffected: the pool is created with all of this in place.

if (!config.signIn.selfSignUpEnabled) {
  authResources.cfnResources.cfnUserPool.addPropertyOverride(
    "AdminCreateUserConfig.AllowAdminCreateUserOnly",
    true
  );
}

// --- The Storage Browser's direct path to S3 -------------------------------------
//
// The Upload tab does not go through AppSync. `@aws-amplify/ui-react-storage` calls S3
// from the browser with the identity pool's credentials, so `enforceRoles` and the path
// prefixes -- both enforced in the Lambda handlers -- do not apply to it. Whatever this
// role grants is what that tab can do.
//
// It used to be one statement, GetObject/PutObject/DeleteObject/ListBucket, on the
// default authenticated role. Measured on a deployed pool (2026-08-27), that produced
// two outcomes and neither was the intended one:
//
//   A user in no group assumed the authenticated role and wrote successfully to a
//   prefix no `groupPathPrefixes` entry grants. `viewer` would have done the same.
//
//   A user in any group did not assume that role at all. Amplify gives every group its
//   own IAM role, sets it as the group's `RoleArn`, and attaches the identity pool with
//   `Type: Token`, so Cognito hands out `cognito:preferred_role` -- the role of the
//   member group with the lowest precedence. Those group roles are created empty, so
//   `contributor` + `external` got AccessDenied on ListBucket. The Upload tab was
//   already broken for everybody who had been given a role.
//
// So the grant moves onto the group roles, which is where the selected credentials
// actually come from. Reads stay on the authenticated role for the ungrouped case,
// matching AppSync: listing and downloading are `allow.authenticated()`.
// The configured ARNs, with a wildcard account or region replaced by this deployment's.
// See `scopeS3ApArns`: the shipped default grants every access point in every account, and
// nothing needs that. The access point *name* is left as configured -- that is the wildcard
// that matters for tenant isolation, and only the operator knows which names exist.
const s3ApArns = scopeS3ApArns(config.s3ApResourceArns, {
  account: Aws.ACCOUNT_ID,
  region: Aws.REGION,
});

const authenticatedRole = authResources.authenticatedUserIamRole;

function grantS3(role: iam.IRole, sid: string, actions: string[]) {
  role.addToPrincipalPolicy(
    new iam.PolicyStatement({ sid, actions, resources: s3ApArns })
  );
}

// The ungrouped case. Read-only, because a user nobody has placed in a group is not a
// contributor -- and because this is the role `AmbiguousRoleResolution` falls back to.
grantS3(authenticatedRole, "StorageBrowserS3APAccess", S3_READ_ACTIONS);

// Both directions of the drift between this mapping and the declared groups, plus a
// shared precedence, which would silently send both groups' members to the read-only
// fallback. Synth is the only cheap place to notice any of them: the deployed result is a
// role that grants nothing, and nothing says so.
const directS3Issues = directS3Problems(Object.keys(authResources.groups));
if (directS3Issues.length > 0) {
  throw new Error(`Direct S3 access configuration: ${directS3Issues.join("; ")}`);
}

for (const { group, precedence, actions } of DIRECT_S3_BY_GROUP) {
  const groupResources = authResources.groups[group];
  groupResources.cfnUserGroup.precedence = precedence;
  if (actions.length > 0) {
    grantS3(groupResources.role, "StorageBrowserS3APAccess", actions);
  }
}

// Access the data stack (same stack where AppSync API lives)
const dataResources = backend.data.resources;
const api = dataResources.graphqlApi;
const dataStack = Stack.of(api);

// --- VPC Configuration for ONTAP-facing Lambda functions ---
// When vpcId is configured, Lambda functions that call ONTAP REST API
// will be deployed inside the VPC with access to the management LIF.
// This is required for: Resource Management, Data Protection, ARP/AI Response.
const vpcConfig = config.vpcId
  ? {
      vpc: ec2.Vpc.fromVpcAttributes(dataStack, "OntapVpc", {
        vpcId: config.vpcId,
        availabilityZones: [`${config.region}a`, `${config.region}c`],
      }),
      securityGroups: config.vpcSecurityGroupIds.map((sgId, idx) =>
        ec2.SecurityGroup.fromSecurityGroupId(dataStack, `OntapSg${idx}`, sgId)
      ),
      vpcSubnets: {
        subnets: config.vpcSubnetIds.map((subnetId, idx) =>
          ec2.Subnet.fromSubnetId(dataStack, `OntapSubnet${idx}`, subnetId)
        ),
      },
    }
  : undefined;

/**
 * DynamoDB gateway endpoint for the VPC Lambda functions.
 *
 * Only created when route table IDs are supplied, because a gateway endpoint is
 * attached to route tables rather than to subnets, and this stack does not own
 * the VPC. Set AMPLIFY_PORTAL_VPC_ROUTE_TABLE_IDS to the route tables used by
 * the Lambda subnets.
 *
 * Why it is needed: a Lambda ENI has no public IP, so a subnet whose default
 * route is an internet gateway gives the function no egress at all. Interface
 * endpoints cover Secrets Manager and friends, and the S3 gateway endpoint
 * covers S3 — DynamoDB has no path unless one is added. Without it the
 * containment ledger is unreachable and nothing expires.
 *
 * A gateway endpoint carries no hourly or data processing charge, unlike an
 * interface endpoint.
 *
 * The handler degrades rather than failing when the ledger is unreachable, so
 * leaving this unset costs the expiry feature, not the ability to contain.
 */
if (vpcConfig && config.vpcRouteTableIds.length === 0 && !config.allowNoBlockExpiry) {
  // Fail at synth rather than deploying something that looks complete. Without a
  // path to DynamoDB, containment still blocks but nothing expires, and that is
  // visible only to someone reading the response of an individual action — not
  // to whoever is relying on blocks lifting themselves.
  throw new Error(
    "vpcRouteTableIds is required when vpcId is set, so the VPC functions can reach " +
      "the containment block ledger over a DynamoDB gateway endpoint. Without it, " +
      "blocks are placed on the cluster but never expire.\n\n" +
      "  Find the route tables for your subnets:\n" +
      '    aws ec2 describe-route-tables --filters "Name=association.subnet-id,Values=<subnet-id>" \\\n' +
      '      --query "RouteTables[].RouteTableId" --output text\n\n' +
      "  Then set vpcRouteTableIds in portal-config.ts (or the environment variable\n" +
      "  your configuration reads it from).\n\n" +
      "  To deploy without block expiry on purpose, set allowNoBlockExpiry."
  );
}

/**
 * A default expiry above the ceiling would be silently unreachable: every block
 * that did not name its own `ttlHours` would be refused, and the refusal would
 * point at a value the caller never supplied. Caught at synth because the
 * combination is a configuration mistake with no correct interpretation.
 *
 * `maxBlockTtlHours: 0` removes the ceiling, so it is not a violation.
 */
if (config.maxBlockTtlHours > 0 && config.defaultBlockTtlHours > config.maxBlockTtlHours) {
  throw new Error(
    `defaultBlockTtlHours (${config.defaultBlockTtlHours}) is above maxBlockTtlHours ` +
      `(${config.maxBlockTtlHours}), so every block that does not pass its own ttlHours ` +
      "would be refused for exceeding a limit the caller never set.\n\n" +
      "  Lower defaultBlockTtlHours, raise maxBlockTtlHours, or set maxBlockTtlHours to 0 " +
      "to remove the ceiling."
  );
}

// A gateway endpoint is a route, and a route table holds one route per prefix
// list. So this resource belongs to the VPC rather than to this stack: with two
// stacks pointed at the same route tables, the second one to deploy is refused
// with "route table rtb-... already has a route with destination-prefix-list-id
// pl-...", and the data stack rolls back after the rest of it created cleanly.
// Measured 2026-08-28 bringing up a second sandbox in a VPC that already had one.
//
// The functions need the route, not the ownership, so reusing an existing one is
// equivalent. `dynamoDbGatewayEndpointExists` says which stack owns it;
// `vpcRouteTableIds` still has to be set either way, since it is also the signal
// that the Lambda subnets can reach the ledger at all.
if (vpcConfig && config.vpcRouteTableIds.length > 0 && !config.dynamoDbGatewayEndpointExists) {
  new ec2.CfnVPCEndpoint(dataStack, "DynamoDbGatewayEndpoint", {
    vpcId: config.vpcId,
    serviceName: `com.amazonaws.${config.region}.dynamodb`,
    vpcEndpointType: "Gateway",
    routeTableIds: config.vpcRouteTableIds,
  });
}

// --- DynamoDB Table for Portal Settings (admin-controlled feature gates) ---
// Stores runtime settings like AI Agent enablement.
// Key: settingKey (string), Value: settingValue (string/JSON)
//
// No `removalPolicy`. There was a conditional here that returned `undefined` on both
// branches, under a comment saying the sandbox default is RETAIN -- so it decided nothing,
// and the thing it claimed is not true either: measured 2026-08-27, a sandbox overrides
// removal policies to `Delete` regardless of what the code asks for.
//
// Leaving it unset is the right answer for this table anyway. It holds feature gates, so
// losing it resets them to their defaults, which an administrator can set again.
const portalSettingsTable = new dynamodb.Table(dataStack, "PortalSettingsTable", {
  partitionKey: { name: "settingKey", type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
});

// --- DynamoDB Table for Chat History (per-user conversation persistence) ---
// PK: userId (Cognito username), SK: sessionId (timestamp-based)
// Stores: messages (JSON), title, createdAt, updatedAt
const chatHistoryTable = new dynamodb.Table(dataStack, "ChatHistoryTable", {
  partitionKey: { name: "userId", type: dynamodb.AttributeType.STRING },
  sortKey: { name: "sessionId", type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
  timeToLiveAttribute: "ttl",
});

// --- DynamoDB Table for Agent Directory (custom agent registry) ---
// PK: agentId (UUID). Stores: name, description, systemPrompt, tools, icon, category, isShared
const agentDirectoryTable = new dynamodb.Table(dataStack, "AgentDirectoryTable", {
  partitionKey: { name: "agentId", type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
  // Holds agent definitions somebody wrote. Nothing regenerates it, so a bad write or an
  // accidental delete is unrecoverable without this.
  pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
});

// --- DynamoDB Table for Multi-Agent Teams ---
// PK: teamId (UUID). Stores: name, description, agents (list), createdBy
const agentTeamsTable = new dynamodb.Table(dataStack, "AgentTeamsTable", {
  partitionKey: { name: "teamId", type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
  // Holds team compositions somebody assembled. Nothing regenerates it, so a bad write or an
  // accidental delete is unrecoverable without this.
  pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
});

// --- DynamoDB Table for Containment Blocks (expiry ledger) ---
// PK: blockId ("smb#<svm>#<domain>#<user>" or "nfs#<svm>#<policy>#<ip>").
//
// ONTAP name-mapping and export-policy deny rules carry no timestamp, so a block
// read back from the cluster cannot say when it was placed or when it should
// end. Expiry therefore needs a record of the portal's own blocks, which is what
// this table is. A scheduled sweep lifts the rows whose expiry has passed.
//
// The native TTL is set later than the block's own expiry on purpose, so the
// audit trail of a containment action outlives the containment itself.
const containmentBlocksTable = new dynamodb.Table(dataStack, "ContainmentBlocksTable", {
  partitionKey: { name: "blockId", type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
  timeToLiveAttribute: "ttl",
  // Losing this table would leave blocks in place on the cluster with nothing
  // recording that they should ever be lifted.
  removalPolicy: RemovalPolicy.RETAIN,
  pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
});

/**
 * Per-user record of what the portal did: downloads, share links, upload links, deletes.
 *
 * Created here because it was not created anywhere. The presigned-url handler has always
 * written to a table named by `URL_AUDIT_TABLE_NAME`, which defaulted to an empty string,
 * and the handler skips the write when the name is empty -- so on every deployment that
 * did not set the variable by hand, the per-user trail did not exist and nothing said so.
 *
 * Distinct from the CloudTrail trail the audit tab queries, and not a substitute for it.
 * CloudTrail attributes each object access to the access point's IAM role, which is the
 * same principal for every portal user, so it establishes that a file was read without
 * establishing who asked. This table knows the Cognito user, and it records the things
 * that never reach S3 as a distinguishable event: minting a presigned URL touches no
 * object, and the download that follows is attributed to whoever redeemed the URL.
 *
 * `RETAIN`, because a deleted audit trail cannot be reconstructed from the thing it was
 * recording.
 *
 * **In a sandbox that has no effect.** Measured 2026-08-27: the deployed template carries
 * `DeletionPolicy: Delete` for every table this file marks `RETAIN`, this one and
 * `ContainmentBlocksTable` alike -- a sandbox overrides removal policies so that
 * `sandbox delete` leaves nothing behind. Whether a branch deployment honours it is
 * unverified. So do not read the line below as "the trail survives"; read it as the intent
 * that a non-sandbox deployment is expected to carry out.
 */
const activityLedgerTable = new dynamodb.Table(dataStack, "PortalActivityLedgerTable", {
  partitionKey: { name: "id", type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
  timeToLiveAttribute: "ttl",
  removalPolicy: RemovalPolicy.RETAIN,
  pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
});

// An existing deployment may have pointed the handler at a table of its own. Honour it,
// so turning this on does not silently split one trail across two tables.
const activityLedgerTableName =
  process.env.URL_AUDIT_TABLE_NAME || activityLedgerTable.tableName;

// --- HTTP Data Source for Step Functions ---
const sfnEndpoint = `https://states.${config.region}.amazonaws.com`;

const sfnDataSource = api.addHttpDataSource(
  "StepFunctionsHttpDataSource",
  sfnEndpoint,
  {
    authorizationConfig: {
      signingRegion: config.region,
      signingServiceName: "states",
    },
  }
);

sfnDataSource.grantPrincipal.addToPrincipalPolicy(
  new iam.PolicyStatement({
    actions: [
      "states:StartExecution",
      "states:DescribeExecution",
      "states:StopExecution",
    ],
    resources: [config.stateMachineResourceScope],
  })
);

// --- Lambda Data Source for ListFiles ---
const listFilesRole = new iam.Role(dataStack, "ListFilesLambdaRole", {
  assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole"
    ),
  ],
  inlinePolicies: {
    S3APAccess: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          // Rename, move-to-trash and restore are all CopyObject followed by
          // DeleteObject, and CopyObject is not an IAM action — the list here
          // used to claim `s3:CopyObject`, which does not exist and so granted
          // nothing. What the call actually needs is GetObject on the source,
          // PutObject on the destination, and the tagging pair: S3 reads the
          // source object's tags to carry them across, and writes them on the
          // copy.
          //
          // Observed before this was added: renaming a file returned
          // "not authorized to perform: s3:GetObjectTagging", and so did
          // restoring one from the trash. Moving the same object to the trash
          // succeeded, so the requirement is not raised on every copy — which is
          // why the gap survived: the operation exercised first happened to be
          // the one that works.
          actions: [
            "s3:ListBucket",
            "s3:GetBucketLocation",
            "s3:GetObject",
            "s3:GetObjectTagging",
            "s3:PutObject",
            "s3:PutObjectTagging",
            "s3:DeleteObject",
          ],
          resources: s3ApArns,
        }),
      ],
    }),
  },
});

/**
 * Bundle a Python function directory, leaving out everything that is only
 * needed on a developer machine.
 *
 * Without the exclusions, `functions/<name>/tests/` and the `__pycache__`
 * directories are uploaded with the handler. That ships test code — including
 * the injection payloads used as fixtures — into the runtime, and grows every
 * package for no benefit.
 */
const functionCode = (directory: string) =>
  lambda.Code.fromAsset(directory, {
    exclude: [
      "tests",
      "tests/**",
      "__pycache__",
      "**/__pycache__",
      "*.pyc",
      ".pytest_cache",
      ".pytest_cache/**",
      "conftest.py",
    ],
  });

/**
 * Layer carrying the repository's `shared/` Python modules.
 *
 * `functions/data-protection/handler.py` imports `shared.ontap_client` and
 * `shared.ontap_response` for the containment actions. Neither was ever
 * packaged: the function asset covers only its own directory and no layer
 * existed, so every containment call failed at import time. The failure was
 * additionally disguised, because the fallback path calculation raised
 * `IndexError: 4` and the string "4" was misread as an HTTP status.
 *
 * A layer mounts at `/opt`, and Python only picks up `/opt/python`, so the
 * archive has to carry a `python/` prefix. `Code.fromAsset` would place the
 * files at the archive root, hence the local bundling hook that restages them.
 * It runs without Docker, which keeps `ampx sandbox` usable on a laptop.
 */
// Asset paths in this file are resolved from the working directory (see the
// `functions/...` arguments above), which is `solutions/amplify-portal`. This
// file is an ES module, so `__dirname` is not available.
const sharedModulesDir = path.resolve(process.cwd(), "..", "..", "shared");

if (!fs.existsSync(path.join(sharedModulesDir, "ontap_response.py"))) {
  throw new Error(
    `Shared Python modules not found at ${sharedModulesDir}. ` +
      "Run ampx from solutions/amplify-portal so the layer can be staged; " +
      "deploying without it silently breaks the ARP containment actions."
  );
}

/**
 * Fingerprint of the Python sources that go into the layer.
 *
 * This lands in the layer Description, which matters for a practical reason:
 * `ampx sandbox` deploys through CDK hotswap, and hotswap updates Lambda code
 * in place while skipping LayerVersion content changes. A layer whose only
 * difference is its S3 key therefore never gets republished in a sandbox, and
 * the function keeps running against the previous version.
 *
 * A LayerVersion is immutable, so changing a property forces CloudFormation to
 * create a replacement — and a resource CloudFormation must create is not
 * hotswappable, which makes the deployment fall back to a real stack update.
 * Tying the description to the content means "shared/ changed" and "the layer
 * is republished" cannot drift apart.
 */
const sharedSourcesFingerprint = (() => {
  const hash = crypto.createHash("sha256");
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) =>
      a.name.localeCompare(b.name)
    )) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (["tests", "__pycache__", ".pytest_cache", "cfn", "scripts"].includes(entry.name)) {
          continue;
        }
        walk(full);
      } else if (entry.name.endsWith(".py")) {
        hash.update(path.relative(sharedModulesDir, full));
        hash.update(fs.readFileSync(full));
      }
    }
  };
  walk(sharedModulesDir);
  return hash.digest("hex").slice(0, 12);
})();

// The fingerprint is in the logical ID, not only the description.
//
// A LayerVersion is immutable, so changing its content is a *replacement* — and
// `ampx sandbox` deploys with `DisableRollback=true`, which CloudFormation refuses to
// combine with a replacement: `Replacement type updates not supported on stack with
// disable-rollback`. The stack then sits in UPDATE_FAILED, from which neither
// `continue-update-rollback` nor `rollback-stack` is available, and the only recorded
// recovery was `sandbox delete` and recreate — which destroys the Cognito users and
// the DynamoDB tables.
//
// With the fingerprint in the ID, changed content is a different resource: a create
// plus a delete, never a replacement. A create is accepted under disable-rollback (the
// Pillow layer below was created in the very deployment that this refusal broke), and
// it also cannot be hotswapped away, which is the other half of the problem — hotswap
// silently skips LayerVersion content changes and reports success, so the deployed
// layer drifts from `shared/` until some unrelated change forces a real update and
// fails on someone who did not cause it.
//
// Observed here: the deployed layer was `[sources c85e93ad58e4]` while the working
// tree hashed to `4dc7cbd5285c`.
const sharedPythonLayer = new lambda.LayerVersion(dataStack, `SharedPythonLayer${sharedSourcesFingerprint}`, {
  description:
    "Repository shared/ Python modules (ONTAP client and ARP containment actions) " +
    `at /opt/python/shared [sources ${sharedSourcesFingerprint}]`,
  compatibleRuntimes: [lambda.Runtime.PYTHON_3_12, lambda.Runtime.PYTHON_3_13],
  compatibleArchitectures: [lambda.Architecture.ARM_64],
  code: lambda.Code.fromAsset(sharedModulesDir, {
    exclude: ["tests", "tests/**", "__pycache__", "**/__pycache__", "*.pyc"],
    // Hash the staged tree, not the source directory. With a source hash, fixing
    // the bundler does not change the asset key, so CDK reuses the object it
    // already uploaded — which is how a corrected bundler still produced a layer
    // containing the earlier, incomplete file set.
    assetHashType: AssetHashType.OUTPUT,
    bundling: {
      image: lambda.Runtime.PYTHON_3_13.bundlingImage,
      command: [],
      local: {
        tryBundle(outputDir: string) {
          // `shared/__init__.py` imports its subpackages eagerly (streaming,
          // routing, observability and so on), so copying only the top-level
          // modules produces a layer that fails at `import shared` with
          // "No module named 'shared.streaming'". Copy the whole Python tree.
          const skipDirs = new Set(["tests", "__pycache__", ".pytest_cache", "cfn", "scripts"]);

          const copyPython = (from: string, to: string): number => {
            let copied = 0;
            for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
              const source = path.join(from, entry.name);
              if (entry.isDirectory()) {
                if (skipDirs.has(entry.name)) continue;
                copied += copyPython(source, path.join(to, entry.name));
              } else if (entry.name.endsWith(".py")) {
                fs.mkdirSync(to, { recursive: true });
                fs.copyFileSync(source, path.join(to, entry.name));
                copied += 1;
              }
            }
            return copied;
          };

          const target = path.join(outputDir, "python", "shared");
          fs.mkdirSync(target, { recursive: true });
          const copied = copyPython(sharedModulesDir, target);
          if (copied === 0) {
            throw new Error(`Staged no Python files from ${sharedModulesDir}`);
          }
          return true;
        },
      },
    },
  }),
});

/**
 * Layer carrying Pillow, for the thumbnail function.
 *
 * The portal's only third-party Python dependency, and it is here rather than in the
 * function asset because a compiled wheel is 6 MB and only the thumbnail path needs
 * it. Attaching it to the listing function instead would put that on the cold start
 * of every file listing.
 *
 * Staged with `pip install --target`, which extracts the wheel in place, so no Docker
 * and no unzip utility is involved. The `--platform` tags with
 * `--python-version 3.13` fetch the build this runtime needs rather than the host's:
 * a wheel compiled for macOS arm64 imports on a laptop and fails in Lambda, which is
 * the kind of difference that only appears after deploying.
 *
 * The version comes from the function's `requirements.txt`. Naming it here as well
 * would put it in two places, and the copy that drifts is the one nothing imports.
 */
const thumbnailRequirements = path.resolve(process.cwd(), "functions/thumbnails/requirements.txt");
const pillowPin = (() => {
  const source = fs.readFileSync(thumbnailRequirements, "utf-8");
  const match = source.match(/^Pillow==(\d+\.\d+\.\d+)$/m);
  if (!match) {
    throw new Error(
      `No exact Pillow pin in ${thumbnailRequirements}. ` +
        "The layer is built from that file; a range would make its contents depend on the build date."
    );
  }
  return match[1];
})();

// The pinned version is in the logical ID for the reason given above the shared layer:
// bumping Pillow would otherwise be a replacement, and a replacement is what the
// sandbox refuses.
const pillowLayer = new lambda.LayerVersion(dataStack, `PillowLayer${pillowPin.replace(/\./g, "")}`, {
  description: `Pillow ${pillowPin} for ARM64 Python 3.13, at /opt/python (thumbnail generation)`,
  compatibleRuntimes: [lambda.Runtime.PYTHON_3_13],
  compatibleArchitectures: [lambda.Architecture.ARM_64],
  code: lambda.Code.fromAsset(path.dirname(thumbnailRequirements), {
    // Only the pin decides the contents, so exclude the handler and its tests: an
    // edit to the Python would otherwise republish an identical layer.
    exclude: ["*", "!requirements.txt"],
    // Hash the staged tree. With a source hash, fixing the bundler would not change
    // the asset key and CDK would reuse the object it already uploaded.
    assetHashType: AssetHashType.OUTPUT,
    bundling: {
      image: lambda.Runtime.PYTHON_3_13.bundlingImage,
      command: [],
      local: {
        tryBundle(outputDir: string) {
          const target = path.join(outputDir, "python");
          fs.mkdirSync(target, { recursive: true });
          const result = spawnSync(
            "python3",
            [
              "-m",
              "pip",
              "install",
              "--target",
              target,
              // Two tags, not one. Pillow 12.3.0 publishes no manylinux2014_aarch64
              // wheel for cp313 -- only manylinux_2_27/2_28 -- so a single legacy tag
              // with --only-binary made the version unresolvable: pip reported "no
              // matching distribution" and did not list 12.3.0 as available at all.
              // Both tags run on the python3.13 runtime, which is Amazon Linux 2023
              // (glibc 2.34, so >= the 2.28 the newer tag requires). Listing both lets
              // pip take whichever the release actually shipped instead of making this
              // build depend on how upstream tags its wheels.
              "--platform",
              "manylinux2014_aarch64",
              "--platform",
              "manylinux_2_28_aarch64",
              "--python-version",
              "3.13",
              "--implementation",
              "cp",
              "--only-binary=:all:",
              "--no-deps",
              "--no-compile",
              "--quiet",
              `Pillow==${pillowPin}`,
            ],
            { stdio: ["ignore", "pipe", "pipe"], encoding: "utf-8" }
          );
          if (result.status !== 0) {
            throw new Error(
              `Staging Pillow ${pillowPin} failed. This needs python3 with pip and network access.\n` +
                `${result.stderr || result.stdout || result.error}`
            );
          }
          // Assert the import target exists rather than trusting the exit code: pip
          // reports success for an empty install if the requirement is already
          // satisfied somewhere it can see.
          if (!fs.existsSync(path.join(target, "PIL", "Image.py"))) {
            throw new Error(
              `Pillow ${pillowPin} staged no PIL package into ${target}. ` +
                "The layer would deploy empty and the thumbnail function would fail at import."
            );
          }
          return true;
        },
      },
    },
  }),
});

// Cognito group -> path prefixes that group may see.
//
// Named once because eleven functions now enforce it. Inlining the derivation a
// second time would let the boundaries drift apart, and the failure would be silent
// in the direction that matters (one function showing paths the other hides).
//
// `config.groupPathPrefixes` wins when set. Otherwise the prefixes are derived from
// the group/AP mapping by the original convention: a group reaches its own folder
// plus the shared one. The derivation stays as the fallback rather than being
// deleted, because a deployment that configures only `groupApMapping` would
// otherwise drop to `{}`, and `{}` means unrestricted here -- the boundary would
// disappear without any error to notice it by.
// Raised here rather than at the point each value is used, so a deployment learns
// about every inert setting at once instead of one per attempt. The checks live in
// their own module because they can then be run against a crafted configuration in a
// test; inside this file they could only be asserted by reading the source, which
// confirms the code exists without establishing that it fires.
validateAuthorizationConfig(config);

const groupPathPrefixes: Record<string, string[]> =
  config.groupPathPrefixes ??
  (config.groupApMapping
    ? Object.fromEntries(
        Object.keys(config.groupApMapping).map((group) => [group, [`${group}/`, "shared/"]])
      )
    : {});

const listFilesFunction = new lambda.Function(dataStack, "ListFilesFunction", {
  runtime: lambda.Runtime.PYTHON_3_13,
  architecture: lambda.Architecture.ARM_64,
  handler: "index.handler",
  code: functionCode("functions/list-files"),
  role: listFilesRole,
  environment: {
    S3_AP_ALIAS: config.s3ApAlias,
    GROUP_AP_MAPPING: JSON.stringify(config.groupApMapping || {}),
    // The folder watch inbox is served from here, so this function needs the
    // notification table and the same path-prefix boundary the agent applies.
    NOTIFICATION_TABLE_NAME: dataResources.tables["FileNotification"].tableName,
    GROUP_PATH_PREFIXES: JSON.stringify(groupPathPrefixes),
        URL_AUDIT_TABLE_NAME: activityLedgerTableName,
        EXTERNAL_SHARE_LINKS_BY_ROLE: JSON.stringify(
          config.externalDefaults.shareLinksByRole
        ),
  },
  // `index.py` imports `shared.portal_path_scope`, the path-prefix boundary. The
  // asset covers only this directory, so without the layer the function fails at
  // import and every file action with it. `backend-assertions` asserts the pairing.
  layers: [sharedPythonLayer],
  memorySize: 256,
  timeout: Duration.seconds(30),
  description: "Lists files in FSx for ONTAP S3 AP with group-based AP routing",
});

// Read-only on the notifications: this function serves the inbox and must not be
// able to forge or remove an event record.
listFilesFunction.addToRolePolicy(
  new iam.PolicyStatement({
    actions: ["dynamodb:Scan"],
    resources: [dataResources.tables["FileNotification"].tableArn],
  })
);
/*
 * Lets the listAccessPoints action check that a configured alias still exists
 * and is AVAILABLE, instead of the portal offering a location that was deleted
 * or is MISCONFIGURED and failing later with no obvious cause.
 *
 * `*` because the API describes attachments across the account and does not
 * accept a resource-level condition; it is a read of metadata only, and the
 * handler still narrows the answer to the aliases the caller's groups map to,
 * so the permission does not widen what anyone can browse.
 */
listFilesFunction.addToRolePolicy(
  new iam.PolicyStatement({
    actions: ["fsx:DescribeS3AccessPointAttachments"],
    resources: ["*"],
  })
);

api.addLambdaDataSource("ListFilesLambdaDataSource", listFilesFunction);

// --- Folder watch: FPolicy / Transfer Family events -> FileNotification ---
//
// The events come from outside the portal. FPolicy publishes to EventBridge only
// if the customer runs an FPolicy server (solutions/event-driven/fpolicy), and
// Transfer Family only if SFTP is deployed. Neither is created here, so this rule
// is idle until one of them exists — which is why the admin switch that reveals
// the inbox is off by default rather than the rule being the thing that gates it.
//
// The bridge writes into the FileNotification model's own table rather than a
// table of its own. That is what makes the records readable through the typed
// client and its subscriptions; a parallel table would need its own query path
// and would drift from the model.
const notificationTable = dataResources.tables["FileNotification"];

const notificationBridgeRole = new iam.Role(dataStack, "NotificationBridgeLambdaRole", {
  assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole"
    ),
  ],
  inlinePolicies: {
    WriteNotifications: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          // Write only. The bridge translates events; reading them back is the
          // inbox's job and belongs to a different function.
          actions: ["dynamodb:PutItem"],
          resources: [notificationTable.tableArn],
        }),
      ],
    }),
  },
});

const notificationBridgeFunction = new lambda.Function(
  dataStack,
  "NotificationBridgeFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_13,
    architecture: lambda.Architecture.ARM_64,
    handler: "handler.handler",
    code: functionCode("functions/notification-bridge"),
    role: notificationBridgeRole,
    environment: {
      NOTIFICATION_TABLE_NAME: notificationTable.tableName,
    },
    memorySize: 256,
    timeout: Duration.seconds(15),
    description:
      "Translates FPolicy and Transfer Family EventBridge events into portal file notifications",
  }
);

// Matches both publishers in one rule. The detail-type values are what the
// FPolicy pattern and Transfer Family emit; the bridge ignores anything else and
// returns 200, so a broader match costs a log line rather than an error.
new events.Rule(dataStack, "FileEventNotificationRule", {
  description:
    "Routes FSx for ONTAP FPolicy and Transfer Family file events to the portal notification bridge",
  eventPattern: {
    source: ["fsx.fpolicy", "aws.transfer", "portal.fpolicy"],
  },
  targets: [new targets.LambdaFunction(notificationBridgeFunction)],
});

// --- Lambda Data Source for FolderDownload (ZIP of a prefix) ---
// Uses functions/folder-download/index.py
// Reads every object under a prefix through the S3 Access Point, builds a ZIP in
// memory, stores it in a short-lived bucket and returns a presigned URL.
const zipTempBucket = new s3.Bucket(dataStack, "FolderZipTempBucket", {
  blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
  encryption: s3.BucketEncryption.S3_MANAGED,
  enforceSSL: true,
  removalPolicy: RemovalPolicy.DESTROY,
  autoDeleteObjects: true,
  // Archives are a transient download artefact, so expire them the next day.
  lifecycleRules: [
    {
      id: "expire-zip-archives",
      enabled: true,
      expiration: Duration.days(1),
      abortIncompleteMultipartUploadAfter: Duration.days(1),
    },
  ],
  serverAccessLogsPrefix: undefined,
});

const folderDownloadRole = new iam.Role(dataStack, "FolderDownloadLambdaRole", {
  assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole"
    ),
  ],
  inlinePolicies: {
    S3ApReadAndZipWrite: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          actions: ["s3:GetObject", "s3:ListBucket"],
          resources: s3ApArns,
        }),
        new iam.PolicyStatement({
          actions: ["s3:PutObject", "s3:GetObject"],
          resources: [`${zipTempBucket.bucketArn}/*`],
        }),
      ],
    }),
  },
});

const folderDownloadFunction = new lambda.Function(
  dataStack,
  "FolderDownloadFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_13,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/folder-download"),
    role: folderDownloadRole,
    environment: {
      S3_AP_ALIAS: config.s3ApAlias,
      // The mapping was already passed here and the handler ignored it, so every ZIP
      // was assembled through the default access point regardless of the caller. The
      // prefixes are new: a ZIP is the contents of a prefix, so the boundary has to
      // decide which prefix may be packaged, not only which alias serves it.
      GROUP_AP_MAPPING: JSON.stringify(config.groupApMapping || {}),
      GROUP_PATH_PREFIXES: JSON.stringify(groupPathPrefixes),
        URL_AUDIT_TABLE_NAME: activityLedgerTableName,
      ZIP_TEMP_BUCKET: zipTempBucket.bucketName,
    },
    // ZIP assembly is memory and time bound; see the caps in the handler.
    // Imports `shared.portal_path_scope`; without the layer the import fails.
    layers: [sharedPythonLayer],
    memorySize: 1024,
    timeout: Duration.minutes(5),
    description:
      "Builds a ZIP of an S3 Access Point prefix and returns a presigned download URL",
  }
);

// The per-user activity ledger. `list-files` records deletes and upload links,
// `folder-download` records the retrieval it performed. `PutItem` only: a handler able to
// amend or remove a row could rewrite the record of what it did.
//
// Granted here rather than beside each function because `folderDownloadFunction` is
// declared after `listFilesFunction`, and a loop placed earlier reads it before its
// declaration.
for (const ledgerWriter of [listFilesFunction, folderDownloadFunction]) {
  ledgerWriter.addToRolePolicy(
    new iam.PolicyStatement({
      actions: ["dynamodb:PutItem"],
      resources: [activityLedgerTable.tableArn],
    })
  );
}

api.addLambdaDataSource("FolderDownloadLambdaDataSource", folderDownloadFunction);

// --- Lambda Data Source for GetPresignedUrl ---
const getPresignedUrlRole = new iam.Role(dataStack, "GetPresignedUrlLambdaRole", {
  assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole"
    ),
  ],
  inlinePolicies: {
    S3APGetObject: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          actions: ["s3:GetObject"],
          resources: s3ApArns,
        }),
        // Narrowed from `["*"]`, which carried a comment saying to restrict it in
        // production. It could not be narrowed while the table was named by an
        // environment variable and created by nobody; now that the stack owns it, the
        // ARN is available here.
        new iam.PolicyStatement({
          actions: ["dynamodb:PutItem"],
          resources: [activityLedgerTable.tableArn],
        }),
      ],
    }),
  },
});

const getPresignedUrlFunction = new lambda.Function(
  dataStack,
  "GetPresignedUrlFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_13,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/presigned-url"),
    role: getPresignedUrlRole,
    environment: {
      S3_AP_ALIAS: config.s3ApAlias,
      URL_AUDIT_TABLE_NAME: activityLedgerTableName,
      // A presigned URL executes as the identity of the access point it was signed
      // against, so this function needs both halves of the boundary. It had
      // neither: every URL was signed against the default access point, which
      // measurement showed lets a caller mapped to a read-only access point read
      // and write through the permissive one.
      GROUP_AP_MAPPING: JSON.stringify(config.groupApMapping || {}),
      GROUP_PATH_PREFIXES: JSON.stringify(groupPathPrefixes),
        EXTERNAL_SHARE_LINKS_BY_ROLE: JSON.stringify(
          config.externalDefaults.shareLinksByRole
        ),
    },
    // `index.py` imports `shared.portal_path_scope`. Without the layer the function
    // fails at import and every preview and download with it.
    layers: [sharedPythonLayer],
    memorySize: 128,
    timeout: Duration.seconds(10),
    description: "Generates presigned URLs for FSx for ONTAP S3 AP file preview/download",
  }
);

api.addLambdaDataSource(
  "GetPresignedUrlLambdaDataSource",
  getPresignedUrlFunction
);

// --- Thumbnails: generated once, cached, served as one batch per page ---
//
// A separate function rather than an action on the listing one, for the reason the
// folder-download function is separate: it needs more memory and a longer timeout
// than a listing, and it carries a 6 MB layer the listing has no use for.
const thumbnailCacheBucket = new s3.Bucket(dataStack, "ThumbnailCacheBucket", {
  blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
  encryption: s3.BucketEncryption.S3_MANAGED,
  enforceSSL: true,
  removalPolicy: RemovalPolicy.DESTROY,
  autoDeleteObjects: true,
  // A derived artefact, and cheap to rebuild. Expiring it bounds what a stale entry
  // can cost and keeps the bucket from growing with every file ever viewed. A
  // thumbnail is re-generated on the next view, so expiry costs one decode.
  lifecycleRules: [
    {
      id: "expire-thumbnails",
      enabled: true,
      expiration: Duration.days(30),
      abortIncompleteMultipartUploadAfter: Duration.days(1),
    },
  ],
});

const thumbnailsRole = new iam.Role(dataStack, "ThumbnailsLambdaRole", {
  assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole"
    ),
  ],
  inlinePolicies: {
    S3ApReadAndThumbnailCache: new iam.PolicyDocument({
      statements: [
        // Read-only on the source. This function renders pictures of files; it has
        // no reason to be able to change one.
        new iam.PolicyStatement({
          actions: ["s3:GetObject", "s3:ListBucket"],
          resources: s3ApArns,
        }),
        new iam.PolicyStatement({
          actions: ["s3:GetObject", "s3:PutObject"],
          resources: [`${thumbnailCacheBucket.bucketArn}/*`],
        }),
      ],
    }),
  },
});

const thumbnailsFunction = new lambda.Function(dataStack, "ThumbnailsFunction", {
  runtime: lambda.Runtime.PYTHON_3_13,
  architecture: lambda.Architecture.ARM_64,
  handler: "handler.handler",
  code: functionCode("functions/thumbnails"),
  role: thumbnailsRole,
  // Pillow, plus `shared.portal_path_scope` for the same path boundary the listing
  // applies. Without the second one this endpoint would read any key it was handed.
  layers: [pillowLayer, sharedPythonLayer],
  environment: {
    S3_AP_ALIAS: config.s3ApAlias,
    GROUP_AP_MAPPING: JSON.stringify(config.groupApMapping || {}),
    GROUP_PATH_PREFIXES: JSON.stringify(groupPathPrefixes),
    THUMBNAIL_CACHE_BUCKET: thumbnailCacheBucket.bucketName,
  },
  // Decoding holds the whole source image in memory, and the source limit is 25 MB.
  // Lambda scales CPU with memory, so this is as much about decode time as space.
  memorySize: 1024,
  timeout: Duration.seconds(60),
  description: "Generates and caches image thumbnails for the file list (batched)",
});

api.addLambdaDataSource("ThumbnailsLambdaDataSource", thumbnailsFunction);

// --- Lambda Data Source for ListSnapshots (ONTAP REST API, VPC) ---
const listSnapshotsRole = new iam.Role(dataStack, "ListSnapshotsLambdaRole", {
  assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole"
    ),
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaVPCAccessExecutionRole"
    ),
  ],
  inlinePolicies: {
    SecretsManager: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          actions: ["secretsmanager:GetSecretValue"],
          resources: ["*"], // Restrict to specific secret ARN in production
        }),
      ],
    }),
  },
});

const listSnapshotsFunction = new lambda.Function(
  dataStack,
  "ListSnapshotsFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_13,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/snapshots"),
    role: listSnapshotsRole,
    // Reads shared.ontap_diagnosis, which classifies an ONTAP failure instead of
    // reporting every one of them as a missing volume. Without the layer the import
    // fails at cold start and the panel shows a blank error.
    layers: [sharedPythonLayer],
    environment: {
      ONTAP_MGMT_IP: config.ontapMgmtIp,
      ONTAP_SECRET_NAME: config.ontapSecretName,
      VOLUME_NAME: config.ontapVolumeName,
      SVM_NAME: config.ontapSvmName,
    },
    memorySize: 256,
    timeout: Duration.seconds(30),
    description:
      "Lists ONTAP snapshots for version history (VPC Lambda, ONTAP REST API)",
    ...(vpcConfig && { vpc: vpcConfig.vpc, securityGroups: vpcConfig.securityGroups, vpcSubnets: vpcConfig.vpcSubnets }),
  }
);

api.addLambdaDataSource("ListSnapshotsLambdaDataSource", listSnapshotsFunction);

// --- Lambda Data Source for ARP/AI Response Actions ---
// Uses functions/data-protection/handler.py (dedicated handler for write operations)
// Actions from: functions/data-protection/handler.py
// Provides: blockSmbUser, unblockSmbUser, blockNfsIp, unblockNfsIp,
//           containThreat, listActiveBlocks, disconnectSessions, listSvms,
//           sweepExpiredBlocks, getSnapshotsWithLockStatus, getArpStatus,
//           getArpSuspects, getSnapLockConfig,
//           getProtectionSummary, createSnapshot, deleteSnapshot,
//           updateArpState, updateRetentionPolicy
// Not here: getS3ObjectLockStatus, and updateRetentionPolicy's s3_object_lock
// target. Both belong to resource-management, which holds the configured bucket
// and the s3:*BucketObjectLockConfiguration permissions; this role has no S3
// permissions at all. A second copy lived here and could only ever fail.
const arpResponseRole = new iam.Role(dataStack, "ArpResponseLambdaRole", {
  assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole"
    ),
    ...(config.vpcId ? [iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaVPCAccessExecutionRole"
    )] : []),
  ],
  inlinePolicies: {
    SecretsManagerAccess: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          actions: ["secretsmanager:GetSecretValue"],
          resources: ["*"], // Restrict to ONTAP_SECRET_NAME ARN in production
        }),
        new iam.PolicyStatement({
          // Scan is needed by the expiry sweep, which has to find due rows
          // without knowing their keys. No DeleteItem: rows are closed out by
          // status so the audit trail survives, and the native TTL removes them
          // later.
          actions: [
            "dynamodb:PutItem",
            "dynamodb:GetItem",
            "dynamodb:UpdateItem",
            "dynamodb:Scan",
          ],
          resources: [containmentBlocksTable.tableArn],
        }),
      ],
    }),
  },
});

const arpResponseFunction = new lambda.Function(
  dataStack,
  "ArpResponseFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_13,
    architecture: lambda.Architecture.ARM_64,
    handler: "handler.handler",
    code: functionCode("functions/data-protection"),
    role: arpResponseRole,
    environment: {
      ONTAP_MGMT_IP: config.ontapMgmtIp,
      ONTAP_SECRET_NAME: config.ontapSecretName,
      VOLUME_NAME: config.ontapVolumeName,
      SVM_NAME: config.ontapSvmName,
      CONTAINMENT_BLOCKS_TABLE: containmentBlocksTable.tableName,
      DEFAULT_BLOCK_TTL_HOURS: String(config.defaultBlockTtlHours),
      MAX_BLOCK_TTL_HOURS: String(config.maxBlockTtlHours),
    },
    // Without this layer the containment actions cannot import
    // shared.ontap_response and fail before reaching ONTAP.
    layers: [sharedPythonLayer],
    memorySize: 256,
    timeout: Duration.seconds(60),
    description:
      "ARP/AI response actions — user/IP blocking, snapshot, session disconnect " +
      "(VPC Lambda, ONTAP REST, requires the shared-modules layer)",
    ...(vpcConfig && { vpc: vpcConfig.vpc, securityGroups: vpcConfig.securityGroups, vpcSubnets: vpcConfig.vpcSubnets }),
  }
);

api.addLambdaDataSource("ArpResponseLambdaDataSource", arpResponseFunction);

// --- Scheduled sweep that lifts expired containment blocks ---
//
// Reuses the ARP function rather than adding a second one. That function already
// sits in the VPC with a route to the ONTAP management endpoint and already holds
// the unblock logic; a separate Lambda would need the same VPC attachment and the
// same credential for no gain.
//
// An EventBridge rule is enough here. EventBridge Scheduler would add a schedule
// group and an invocation role to manage, and buys nothing for a fixed interval
// with no timezone or one-off semantics involved.
//
// The interval bounds how long a block outlives its expiry, so it is a coarser
// control than it looks: at one hour, "expires in 1h" can mean up to two.
// --- Alerting on the sweep ---
//
// A failing sweep used to be visible only in CloudWatch Logs, so a principal
// could stay contained long past its expiry with nobody notified.
//
// Two alarms, because the two failure modes are not the same shape:
//
//   SweepFailures  — the sweep ran and could not lift something
//   SweepRuns      — the sweep did not run at all
//
// The second is the one that matters more and is the easier to miss: a sweep
// that has stopped firing reports no failures, so alarming only on errors would
// call that healthy. It uses treatMissingData: BREACHING for exactly that reason.
const containmentAlarmTopic = new sns.Topic(dataStack, "ContainmentAlarmTopic", {
  displayName: "FSx for ONTAP portal containment alarms",
});

// Refuse anything that did not arrive over TLS.
//
// A topic has no "SSL only" switch; the enforcement is a resource policy denying the
// action when `aws:SecureTransport` is false. Nothing in this deployment publishes over
// plain HTTP -- CloudWatch alarms and the AWS SDK both use TLS -- so this removes a
// capability nobody is using rather than changing how the topic is reached.
//
// The condition tests for the string "false" rather than negating a truthy test: a
// request that omits the key entirely must not match, and `Bool: {"...": false}` on an
// absent key does not match either, so a Deny written that way would be silent about
// exactly the requests it is meant to catch.
containmentAlarmTopic.addToResourcePolicy(
  new iam.PolicyStatement({
    sid: "DenyPublishWithoutTls",
    effect: iam.Effect.DENY,
    principals: [new iam.AnyPrincipal()],
    actions: ["sns:Publish"],
    resources: [containmentAlarmTopic.topicArn],
    conditions: { Bool: { "aws:SecureTransport": "false" } },
  })
);

if (config.alarmEmail) {
  containmentAlarmTopic.addSubscription(new subscriptions.EmailSubscription(config.alarmEmail));
}

// One period per sweep, so the alarm window follows the schedule instead of
// being a number picked independently of it. A fixed hour meant four datapoints
// per period and a recovery that took two hours after the sweep came back.
const sweepMetric = (metricName: string, statistic: string) =>
  new cloudwatch.Metric({
    namespace: "FsxOntapPortal/Containment",
    metricName,
    statistic,
    period: Duration.minutes(config.blockSweepIntervalMinutes),
  });

// How many sweeps may be missed before anyone is told. Four is long enough that
// a single throttled or slow run is not an incident, and short enough that a
// block does not outlive its expiry by much more than an hour at the default
// interval.
const MISSED_SWEEPS_BEFORE_ALARM = 4;

const sweepFailureAlarm = new cloudwatch.Alarm(dataStack, "ContainmentSweepFailureAlarm", {
  alarmName: `${Stack.of(dataStack).stackName}-containment-sweep-failures`,
  alarmDescription:
    "The containment sweep could not lift one or more expired blocks. Access stays " +
    "cut off for those principals until this succeeds. Check the ARP function logs, " +
    "then scripts/portal-probes/diagnose_vpc_egress.py and probe_containment.py blocks.",
  metric: sweepMetric("SweepFailures", "Sum"),
  threshold: 0,
  comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
  evaluationPeriods: 2,
  // A single failed lift is retried on the next tick by design, so alarm on a
  // failure that persists rather than on the first one.
  datapointsToAlarm: 2,
  // Missing data here is covered by the other alarm; treating it as a failure
  // would make both fire for one cause.
  treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
});
sweepFailureAlarm.addAlarmAction(new cloudwatchActions.SnsAction(containmentAlarmTopic));

const sweepSilentAlarm = new cloudwatch.Alarm(dataStack, "ContainmentSweepSilentAlarm", {
  alarmName: `${Stack.of(dataStack).stackName}-containment-sweep-not-running`,
  alarmDescription:
    "The containment sweep has stopped reporting. Blocks will not expire while this " +
    "is true, and nothing else will say so. Check the EventBridge rule and the ARP " +
    "function's own errors.",
  metric: sweepMetric("SweepRuns", "Sum"),
  threshold: 1,
  comparisonOperator: cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
  evaluationPeriods: MISSED_SWEEPS_BEFORE_ALARM,
  datapointsToAlarm: MISSED_SWEEPS_BEFORE_ALARM,
  // The point of this alarm: no data means the sweep is not running, which is a
  // problem, not an absence of one. A freshly deployed stack sits here until the
  // first sweep reports, which is correct — nothing is expiring yet.
  treatMissingData: cloudwatch.TreatMissingData.BREACHING,
});
sweepSilentAlarm.addAlarmAction(new cloudwatchActions.SnsAction(containmentAlarmTopic));

/**
 * A containment action that arrived without a portal identity behind it.
 *
 * This is detection and not prevention, and the difference is worth stating
 * plainly. Inside a single account a principal may invoke a function if *either*
 * its identity policy or the function's resource policy allows it, and the
 * Lambda permission API writes only Allow statements. No resource policy added
 * here could take invoke rights away from a principal that already holds them.
 * Prevention belongs to the identity policies and to any SCP or permissions
 * boundary above them, which this stack does not own — the copy-paste policy for
 * that is in docs/portal-authorization-model.md.
 *
 * So the function reports instead: the AppSync resolver is the only path that
 * supplies a Cognito identity, and anything else is recorded as
 * `unattributed` / `direct-invoke` in the ledger. Until now that was visible
 * only to somebody reading the row afterwards. This alarms on it while the
 * containment is still in force.
 *
 * Fires on the first occurrence rather than waiting for a pattern. One
 * containment action nobody is accountable for is already the thing worth
 * looking at, and unlike a failed sweep it is not something that retries itself.
 *
 * Expect this to fire when scripts/portal-probes/ is run against a deployment:
 * those invoke the function directly, which is exactly the event described above.
 * Exempting them would leave a hole the shape of the thing being watched for.
 */
const unattributedActionAlarm = new cloudwatch.Alarm(dataStack, "ContainmentUnattributedActionAlarm", {
  alarmName: `${Stack.of(dataStack).stackName}-containment-unattributed-action`,
  alarmDescription:
    "A state-changing containment action ran without a portal identity, so the ledger " +
    "records it as unattributed/direct-invoke. Either something invoked the ARP function " +
    "directly (the probe scripts do this deliberately) or a principal holds " +
    "lambda:InvokeFunction that should not. Check CloudTrail for the Invoke call and the " +
    "ledger row for what it changed.",
  metric: sweepMetric("UnattributedContainmentActions", "Sum"),
  threshold: 0,
  comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
  evaluationPeriods: 1,
  datapointsToAlarm: 1,
  // No data means no containment actions ran, which is the normal state.
  treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
});
unattributedActionAlarm.addAlarmAction(new cloudwatchActions.SnsAction(containmentAlarmTopic));

new events.Rule(dataStack, "ContainmentBlockSweepSchedule", {
  description:
    "Lifts FSx for ONTAP containment blocks whose expiry has passed (portal-created blocks only)",
  schedule: events.Schedule.rate(Duration.minutes(config.blockSweepIntervalMinutes)),
  targets: [
    new targets.LambdaFunction(arpResponseFunction, {
      event: events.RuleTargetInput.fromObject({ action: "sweepExpiredBlocks" }),
      // A failed sweep is retried by the next tick, so a dead-letter queue would
      // collect events that are already superseded.
      retryAttempts: 2,
    }),
  ],
});

// --- Lambda Data Source for Resource Management (Admin) ---
// Uses functions/resource-management/handler.py
// --- Data platform inventory ------------------------------------------------
//
// Provides: listDataPlatforms
//
// Outside the VPC, unlike every other ONTAP-adjacent function here, and that is
// the point rather than an oversight. It answers the AWS control plane, and its
// value is that it still answers when the ONTAP path does not: a mismatched
// credential or an unreachable management LIF leaves the panels unable to say
// what exists, which is when an operator most needs to see the inventory. Put in
// the VPC it would need an FSx interface endpoint or a NAT gateway, and would
// fail for network reasons while reporting an inventory problem.
//
// It also holds no ONTAP credential and needs none. Listing what exists is a
// different question from being able to act on it.
const platformDiscoveryFunction = new lambda.Function(dataStack, "PlatformDiscoveryFunction", {
  runtime: lambda.Runtime.PYTHON_3_13,
  architecture: lambda.Architecture.ARM_64,
  handler: "handler.handler",
  code: functionCode("functions/platform-discovery"),
  environment: {
    // Platforms that are not FSx for ONTAP, which no AWS API lists. Each appears
    // only once a probe answers for it, so this is a claim that something exists
    // rather than an entry in the inventory.
    DECLARED_PLATFORMS: JSON.stringify(config.declaredDataPlatforms || []),
    // Compared, not published. The inventory says which platform is the working
    // one as a boolean; the address itself never leaves this function, so the
    // response stays answerable to every signed-in user.
    ONTAP_MGMT_IP: config.ontapMgmtIp,
    DISCOVERY_REGIONS: config.discoveryRegions.join(","),
    DISCOVERY_ACCOUNTS: config.discoveryAccounts.join(","),
    DISCOVERY_ROLE_NAME: config.discoveryRoleName,
  },
  // Imports `shared.storage_systems`; the asset covers only this directory.
  layers: [sharedPythonLayer],
  memorySize: 256,
  timeout: Duration.seconds(30),
  description: "Lists the data platforms the portal can scope to (FSx control plane)",
});

// Account-wide read on the FSx control plane. Neither call takes a resource, so
// there is nothing narrower to scope them to: `DescribeFileSystems` and
// `DescribeStorageVirtualMachines` enumerate, and an enumeration cannot be
// restricted to the resources it is meant to find. Both are read-only.
platformDiscoveryFunction.addToRolePolicy(
  new iam.PolicyStatement({
    effect: iam.Effect.ALLOW,
    actions: ["fsx:DescribeFileSystems", "fsx:DescribeStorageVirtualMachines"],
    resources: ["*"],
  })
);

// Cross-account discovery, scoped to the one role name rather than to `*`. The
// role is named the same in every account and the ARN is built from it, so the
// wildcard belongs in the account field and nowhere else: `role/*` would let this
// function assume anything it can reach, for the sake of reading two listings.
//
// Only added when accounts are configured. Granting it unconditionally would leave
// a permission in place that nothing uses, and would make the policy imply a
// capability the deployment does not have.
if (config.discoveryRoleName && config.discoveryAccounts.length > 0) {
  platformDiscoveryFunction.addToRolePolicy(
    new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ["sts:AssumeRole"],
      resources: config.discoveryAccounts.map(
        account => `arn:aws:iam::${account}:role/${config.discoveryRoleName}`
      ),
    })
  );
}

api.addLambdaDataSource("PlatformDiscoveryLambdaDataSource", platformDiscoveryFunction);

// Provides: Volume CRUD, Export Policy, QoS Policy, SnapLock, Quota, Qtree,
// CIFS share, ARP admin, snapshot policy, SMB local users/groups, name mapping,
// FlexCache and FlexClone management, SnapMirror lifecycle (transfer, quiesce,
// resume, break, resync, delete), Vscan and FPolicy policy management, cluster
// and SVM peering, and cluster inventory. All ONTAP access is HTTPS to the
// management endpoint using the Secrets Manager credential, so no extra AWS
// permissions are required.
const resourceMgmtRole = new iam.Role(dataStack, "ResourceMgmtLambdaRole", {
  assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole"
    ),
    ...(config.vpcId ? [iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaVPCAccessExecutionRole"
    )] : []),
  ],
  inlinePolicies: {
    SecretsManagerAndS3Access: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          actions: ["secretsmanager:GetSecretValue"],
          resources: ["*"], // Restrict to ONTAP_SECRET_NAME ARN in production
        }),
        new iam.PolicyStatement({
          actions: ["s3:GetBucketObjectLockConfiguration", "s3:GetBucketVersioning", "s3:ListAllMyBuckets", "s3:PutBucketObjectLockConfiguration"],
          resources: ["*"], // Restrict to S3_OBJECT_LOCK_BUCKET ARN in production
        }),
        new iam.PolicyStatement({
          actions: ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Scan"],
          resources: [portalSettingsTable.tableArn],
        }),
      ],
    }),
  },
});

const resourceMgmtFunction = new lambda.Function(
  dataStack,
  "ResourceMgmtFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_13,
    architecture: lambda.Architecture.ARM_64,
    handler: "handler.handler",
    code: functionCode("functions/resource-management"),
    role: resourceMgmtRole,
    // The SnapMirror actions call shared/ontap_client.py, which reaches this
    // function at /opt/python/shared through the layer. functionCode() bundles
    // only the function directory, so without the layer the import fails at
    // request time rather than at deploy time. The import is lazy and only the
    // SnapMirror actions take that path; the other actions are unaffected.
    layers: [sharedPythonLayer],
    environment: {
      ONTAP_MGMT_IP: config.ontapMgmtIp,
      ONTAP_SECRET_NAME: config.ontapSecretName,
      SVM_NAME: config.ontapSvmName,
      S3_OBJECT_LOCK_BUCKET: config.s3ObjectLockBucket,
      PORTAL_SETTINGS_TABLE: portalSettingsTable.tableName,
    },
    memorySize: 256,
    timeout: Duration.seconds(60),
    description:
      "Resource management — Volume/ExportPolicy/QoS/SnapLock/Quota/Qtree/CIFS/ARP/Snapshot/LocalUser/NameMapping/FlexCache/FlexClone/SnapMirror/Vscan/FPolicy/Peering CRUD and cluster inventory (VPC Lambda, ONTAP REST + S3)",
    ...(vpcConfig && { vpc: vpcConfig.vpc, securityGroups: vpcConfig.securityGroups, vpcSubnets: vpcConfig.vpcSubnets }),
  }
);

api.addLambdaDataSource("ResourceMgmtLambdaDataSource", resourceMgmtFunction);

// --- Lambda Data Source for SearchFiles (Bedrock Knowledge Base) ---
const searchFilesRole = new iam.Role(dataStack, "SearchFilesLambdaRole", {
  assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole"
    ),
  ],
  inlinePolicies: {
    BedrockKB: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          actions: [
            "bedrock:Retrieve",
            "bedrock:RetrieveAndGenerate",
          ],
          resources: ["*"], // Restrict to specific KB ARN in production
        }),
        new iam.PolicyStatement({
          actions: ["s3:ListBucket", "s3:GetObject"],
          // Both branches go through the same narrowing, so the fallback is not a way
          // back to every account.
          resources:
            s3ApArns.length > 0
              ? s3ApArns
              : scopeS3ApArns(
                  ["arn:aws:s3:*:*:accesspoint/*", "arn:aws:s3:*:*:accesspoint/*/object/*"],
                  { account: Aws.ACCOUNT_ID, region: Aws.REGION }
                ),
        }),
      ],
    }),
  },
});

const searchFilesFunction = new lambda.Function(
  dataStack,
  "SearchFilesFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_13,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/search-files"),
    role: searchFilesRole,
    environment: {
      BEDROCK_KB_ID: config.bedrockKbId || "",
      S3_AP_ALIAS: config.s3ApAlias,
      // Search results are object keys, so an unfiltered search is a listing by
      // another name. The knowledge base indexes whatever it was pointed at and has
      // no notion of the portal's groups, so the semantic mode needs the boundary as
      // much as the keyword one.
      GROUP_AP_MAPPING: JSON.stringify(config.groupApMapping || {}),
      GROUP_PATH_PREFIXES: JSON.stringify(groupPathPrefixes),
        EXTERNAL_AI_ENABLED: String(config.externalDefaults.aiEnabled),
    },
    // Imports `shared.portal_path_scope`; without the layer the import fails.
    layers: [sharedPythonLayer],
    memorySize: 256,
    timeout: Duration.seconds(30),
    description: "Semantic file search via Bedrock Knowledge Base (S3 AP data source)",
  }
);

api.addLambdaDataSource("SearchFilesLambdaDataSource", searchFilesFunction);

// --- Lambda Data Source for AgentChat (Bedrock Converse with tool_use) ---
const agentChatRole = new iam.Role(dataStack, "AgentChatLambdaRole", {
  assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole"
    ),
  ],
  inlinePolicies: {
    BedrockAndS3: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          actions: [
            "bedrock:InvokeModel",
            "bedrock:Converse",
            "bedrock:ApplyGuardrail",
            "bedrock:Retrieve",
            "bedrock:RetrieveAndGenerate",
          ],
          resources: ["*"], // Restrict to specific model ARN in production
        }),
        new iam.PolicyStatement({
          actions: ["s3:GetObject", "s3:ListBucket"],
          // Both branches go through the same narrowing, so the fallback is not a way
          // back to every account.
          resources:
            s3ApArns.length > 0
              ? s3ApArns
              : scopeS3ApArns(
                  ["arn:aws:s3:*:*:accesspoint/*", "arn:aws:s3:*:*:accesspoint/*/object/*"],
                  { account: Aws.ACCOUNT_ID, region: Aws.REGION }
                ),
        }),
        new iam.PolicyStatement({
          actions: ["dynamodb:GetItem"],
          resources: [portalSettingsTable.tableArn],
        }),
        new iam.PolicyStatement({
          actions: ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query", "dynamodb:DeleteItem"],
          resources: [chatHistoryTable.tableArn],
        }),
        new iam.PolicyStatement({
          actions: ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Scan", "dynamodb:DeleteItem", "dynamodb:UpdateItem"],
          resources: [agentDirectoryTable.tableArn, agentTeamsTable.tableArn],
        }),
      ],
    }),
  },
});

const agentChatFunction = new lambda.Function(
  dataStack,
  "AgentChatFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_13,
    architecture: lambda.Architecture.ARM_64,
    handler: "handler.handler",
    code: functionCode("functions/agent-chat"),
    role: agentChatRole,
    environment: {
      S3_AP_ALIAS: config.s3ApAlias,
      AGENT_MODEL_ID: process.env.AGENT_MODEL_ID || "amazon.nova-lite-v1:0",
      MAX_TOOL_ITERATIONS: "8",
      BEDROCK_GUARDRAIL_ID: config.bedrockGuardrailId || "",
      BEDROCK_GUARDRAIL_VERSION: config.bedrockGuardrailVersion || "DRAFT",
      BEDROCK_KB_ID: config.bedrockKbId || "",
      PORTAL_SETTINGS_TABLE: portalSettingsTable.tableName,
      CHAT_HISTORY_TABLE: chatHistoryTable.tableName,
      AGENT_DIRECTORY_TABLE: agentDirectoryTable.tableName,
      AGENT_TEAMS_TABLE: agentTeamsTable.tableName,
      GROUP_PATH_PREFIXES: JSON.stringify(groupPathPrefixes),
        EXTERNAL_AI_ENABLED: String(config.externalDefaults.aiEnabled),
    },
    // `handler.py` imports `shared.portal_path_scope` for the path-prefix boundary.
    layers: [sharedPythonLayer],
    memorySize: 512,
    timeout: Duration.seconds(90),
    description: "AI Agent Chat — Bedrock Converse with tool_use (list/read/search files via S3 AP)",
  }
);

api.addLambdaDataSource("AgentChatLambdaDataSource", agentChatFunction);

// --- Lambda Data Source for QueryAuditLog (Athena over CloudTrail) ---
const queryAuditLogRole = new iam.Role(dataStack, "QueryAuditLogLambdaRole", {
  assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole"
    ),
  ],
  inlinePolicies: {
    AthenaAndS3: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          actions: [
            "athena:StartQueryExecution",
            "athena:GetQueryExecution",
            "athena:GetQueryResults",
          ],
          resources: ["*"], // Restrict to specific Athena WorkGroup ARN in production
        }),
        new iam.PolicyStatement({
          actions: ["s3:GetObject", "s3:ListBucket", "s3:PutObject"],
          resources: ["*"], // Restrict to CloudTrail + Athena output buckets in production
        }),
        new iam.PolicyStatement({
          actions: ["glue:GetTable", "glue:GetDatabase", "glue:GetPartitions"],
          resources: ["*"], // Restrict to specific Glue database/tables in production
        }),
      ],
    }),
  },
});

const queryAuditLogFunction = new lambda.Function(
  dataStack,
  "QueryAuditLogFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_13,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/audit-log"),
    role: queryAuditLogRole,
    environment: {
      S3_AP_ALIAS: config.s3ApAlias,
      ATHENA_DATABASE: process.env.ATHENA_AUDIT_DATABASE || "cloudtrail_logs",
      ATHENA_TABLE: process.env.ATHENA_AUDIT_TABLE || "cloudtrail_s3_events",
      ATHENA_OUTPUT_LOCATION:
        process.env.ATHENA_AUDIT_OUTPUT || "",
      // The second source. `source: "PORTAL"` reads this instead of Athena.
      URL_AUDIT_TABLE_NAME: activityLedgerTableName,
    },
    memorySize: 256,
    timeout: Duration.seconds(60),
    description:
      "Queries the file access audit trail: CloudTrail S3 data events via Athena, or the per-user portal activity ledger",
  }
);

// Read-only on the ledger, and only the ledger. The audit path must not be able to
// amend the record it reports.
queryAuditLogFunction.addToRolePolicy(
  new iam.PolicyStatement({
    actions: ["dynamodb:Scan"],
    resources: [activityLedgerTable.tableArn],
  })
);

api.addLambdaDataSource(
  "QueryAuditLogLambdaDataSource",
  queryAuditLogFunction
);

// --- Lambda Data Source for GetFileMetadata (DynamoDB) ---
const getFileMetadataRole = new iam.Role(dataStack, "GetFileMetadataLambdaRole", {
  assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole"
    ),
  ],
  inlinePolicies: {
    DynamoDB: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          actions: ["dynamodb:BatchGetItem", "dynamodb:GetItem"],
          resources: ["*"],
        }),
      ],
    }),
  },
});

const getFileMetadataFunction = new lambda.Function(
  dataStack,
  "GetFileMetadataFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_13,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/file-metadata"),
    role: getFileMetadataRole,
    environment: {
      // Both halves of the path boundary. This endpoint takes an object key from
      // the client, and took neither: the access point decides which ONTAP identity
      // reads the file, the prefixes decide whether this caller may name that key.
      GROUP_PATH_PREFIXES: JSON.stringify(groupPathPrefixes),
      AI_METADATA_TABLE_NAME: process.env.AI_METADATA_TABLE_NAME || "",
    },
    // Imports `shared.portal_path_scope` and `shared.s3ap_helper`. Without the
    // layer the function fails at import.
    layers: [sharedPythonLayer],
    memorySize: 256,
    timeout: Duration.seconds(15),
    description: "Fetches AI processing metadata for file inline display",
  }
);

api.addLambdaDataSource("GetFileMetadataLambdaDataSource", getFileMetadataFunction);

// --- Lambda Data Source for GenerateQrCode (Presigned URL + QR) ---
const generateQrCodeRole = new iam.Role(dataStack, "GenerateQrCodeLambdaRole", {
  assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole"
    ),
  ],
  inlinePolicies: {
    S3APGetObject: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          actions: ["s3:GetObject"],
          resources: s3ApArns,
        }),
      ],
    }),
  },
});

const generateQrCodeFunction = new lambda.Function(
  dataStack,
  "GenerateQrCodeFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_13,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/generate-qr"),
    role: generateQrCodeRole,
    environment: {
      // Both halves of the path boundary. This endpoint takes an object key from
      // the client, and took neither: the access point decides which ONTAP identity
      // reads the file, the prefixes decide whether this caller may name that key.
      GROUP_AP_MAPPING: JSON.stringify(config.groupApMapping || {}),
      GROUP_PATH_PREFIXES: JSON.stringify(groupPathPrefixes),
        EXTERNAL_SHARE_LINKS_BY_ROLE: JSON.stringify(
          config.externalDefaults.shareLinksByRole
        ),
      S3_AP_ALIAS: config.s3ApAlias,
      MAX_QR_EXPIRY_SECONDS: "300",
    },
    // Imports `shared.portal_path_scope` and `shared.s3ap_helper`. Without the
    // layer the function fails at import.
    layers: [sharedPythonLayer],
    memorySize: 256,
    timeout: Duration.seconds(15),
    description: "Generates Presigned URL + QR code PNG for OT/manufacturing file access",
  }
);

api.addLambdaDataSource("GenerateQrCodeLambdaDataSource", generateQrCodeFunction);

// --- Lambda Data Source for AskAboutFile (Bedrock) ---
const askAboutFileRole = new iam.Role(dataStack, "AskAboutFileLambdaRole", {
  assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole"
    ),
  ],
  inlinePolicies: {
    S3APAndBedrock: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          actions: ["s3:GetObject"],
          resources: s3ApArns,
        }),
        new iam.PolicyStatement({
          actions: ["bedrock:InvokeModel", "bedrock:Converse"],
          resources: ["arn:aws:bedrock:*::foundation-model/*"],
        }),
        new iam.PolicyStatement({
          actions: ["dynamodb:GetItem"],
          resources: ["*"], // Restrict to specific classification table ARN in production
        }),
      ],
    }),
  },
});

const askAboutFileFunction = new lambda.Function(
  dataStack,
  "AskAboutFileFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_13,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/ask-about-file"),
    role: askAboutFileRole,
    environment: {
      // Both halves of the path boundary. This endpoint takes an object key from
      // the client, and took neither: the access point decides which ONTAP identity
      // reads the file, the prefixes decide whether this caller may name that key.
      GROUP_AP_MAPPING: JSON.stringify(config.groupApMapping || {}),
      GROUP_PATH_PREFIXES: JSON.stringify(groupPathPrefixes),
        EXTERNAL_AI_ENABLED: String(config.externalDefaults.aiEnabled),
      S3_AP_ALIAS: config.s3ApAlias,
      BEDROCK_MODEL_ID: "amazon.nova-lite-v1:0",
      CLASSIFICATION_TABLE_NAME:
        process.env.CLASSIFICATION_TABLE_NAME || "",
      AI_BLOCKED_LEVELS:
        process.env.AI_BLOCKED_LEVELS || "CONFIDENTIAL,CUI,HIGHLY_RESTRICTED,RESTRICTED",
    },
    // Imports `shared.portal_path_scope` and `shared.s3ap_helper`. Without the
    // layer the function fails at import.
    layers: [sharedPythonLayer],
    memorySize: 512,
    timeout: Duration.seconds(60),
    description: "Asks Bedrock about file content with CONFIDENTIAL guardrail (F-2)",
  }
);

api.addLambdaDataSource("AskAboutFileLambdaDataSource", askAboutFileFunction);

// --- Lambda Data Source for DetectLabels (Rekognition) ---
const detectLabelsRole = new iam.Role(dataStack, "DetectLabelsLambdaRole", {
  assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole"
    ),
  ],
  inlinePolicies: {
    S3APAndRekognition: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          actions: ["s3:GetObject"],
          resources: s3ApArns,
        }),
        new iam.PolicyStatement({
          actions: ["rekognition:DetectLabels"],
          resources: ["*"],
        }),
      ],
    }),
  },
});

const detectLabelsFunction = new lambda.Function(
  dataStack,
  "DetectLabelsFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_13,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/detect-labels"),
    role: detectLabelsRole,
    environment: {
      // Both halves of the path boundary. This endpoint takes an object key from
      // the client, and took neither: the access point decides which ONTAP identity
      // reads the file, the prefixes decide whether this caller may name that key.
      GROUP_AP_MAPPING: JSON.stringify(config.groupApMapping || {}),
      GROUP_PATH_PREFIXES: JSON.stringify(groupPathPrefixes),
        EXTERNAL_AI_ENABLED: String(config.externalDefaults.aiEnabled),
      S3_AP_ALIAS: config.s3ApAlias,
    },
    // Imports `shared.portal_path_scope` and `shared.s3ap_helper`. Without the
    // layer the function fails at import.
    layers: [sharedPythonLayer],
    memorySize: 512,
    timeout: Duration.seconds(30),
    description: "Detects labels/objects in images from FSx for ONTAP S3 AP via Rekognition",
  }
);

api.addLambdaDataSource("DetectLabelsLambdaDataSource", detectLabelsFunction);

// --- Lambda Data Source for Athena Query ---
const athenaQueryRole = new iam.Role(dataStack, "AthenaQueryLambdaRole", {
  assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole"
    ),
  ],
  inlinePolicies: {
    AthenaAndGlue: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          actions: [
            "athena:StartQueryExecution",
            "athena:GetQueryExecution",
            "athena:GetQueryResults",
            "athena:StopQueryExecution",
          ],
          resources: ["*"],
        }),
        new iam.PolicyStatement({
          actions: [
            "glue:GetTable",
            "glue:GetTables",
            "glue:GetDatabase",
            "glue:GetDatabases",
            "glue:GetPartitions",
          ],
          resources: ["*"],
        }),
        new iam.PolicyStatement({
          actions: ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:GetBucketLocation"],
          resources: [
            ...s3ApArns,
            "arn:aws:s3:::*athena-results*",
            "arn:aws:s3:::*athena-results*/*",
          ],
        }),
      ],
    }),
  },
});

const athenaQueryFunction = new lambda.Function(
  dataStack,
  "AthenaQueryFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_13,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/athena-query"),
    role: athenaQueryRole,
    environment: {
      ATHENA_WORKGROUP: "primary",
      ATHENA_OUTPUT_LOCATION: "",
    },
    memorySize: 256,
    timeout: Duration.seconds(60),
    description: "Executes Athena SQL queries for the file portal",
  }
);

api.addLambdaDataSource("AthenaQueryLambdaDataSource", athenaQueryFunction);

// --- Lambda Data Source for Textract ---
const textractRole = new iam.Role(dataStack, "TextractLambdaRole", {
  assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole"
    ),
  ],
  inlinePolicies: {
    S3APAndTextract: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          actions: ["s3:GetObject"],
          resources: s3ApArns,
        }),
        new iam.PolicyStatement({
          actions: ["textract:AnalyzeDocument", "textract:DetectDocumentText"],
          resources: ["*"],
        }),
      ],
    }),
  },
});

const textractFunction = new lambda.Function(
  dataStack,
  "TextractFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_13,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/textract"),
    role: textractRole,
    environment: {
      // Both halves of the path boundary. This endpoint takes an object key from
      // the client, and took neither: the access point decides which ONTAP identity
      // reads the file, the prefixes decide whether this caller may name that key.
      GROUP_AP_MAPPING: JSON.stringify(config.groupApMapping || {}),
      GROUP_PATH_PREFIXES: JSON.stringify(groupPathPrefixes),
        EXTERNAL_AI_ENABLED: String(config.externalDefaults.aiEnabled),
      S3_AP_ALIAS: config.s3ApAlias,
    },
    // Imports `shared.portal_path_scope` and `shared.s3ap_helper`. Without the
    // layer the function fails at import.
    layers: [sharedPythonLayer],
    memorySize: 512,
    timeout: Duration.seconds(60),
    description: "Extracts text from documents on FSx for ONTAP S3 AP via Textract",
  }
);

api.addLambdaDataSource("TextractLambdaDataSource", textractFunction);

// --- Lambda Data Source for Comprehend ---
const comprehendRole = new iam.Role(dataStack, "ComprehendLambdaRole", {
  assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole"
    ),
  ],
  inlinePolicies: {
    S3APAndComprehend: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          actions: ["s3:GetObject"],
          resources: s3ApArns,
        }),
        new iam.PolicyStatement({
          actions: [
            "comprehend:DetectEntities",
            "comprehend:DetectSentiment",
            "comprehend:DetectKeyPhrases",
          ],
          resources: ["*"],
        }),
      ],
    }),
  },
});

const comprehendFunction = new lambda.Function(
  dataStack,
  "ComprehendFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_13,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/comprehend-analysis"),
    role: comprehendRole,
    environment: {
      // Both halves of the path boundary. This endpoint takes an object key from
      // the client, and took neither: the access point decides which ONTAP identity
      // reads the file, the prefixes decide whether this caller may name that key.
      GROUP_AP_MAPPING: JSON.stringify(config.groupApMapping || {}),
      GROUP_PATH_PREFIXES: JSON.stringify(groupPathPrefixes),
        EXTERNAL_AI_ENABLED: String(config.externalDefaults.aiEnabled),
      S3_AP_ALIAS: config.s3ApAlias,
    },
    // Imports `shared.portal_path_scope` and `shared.s3ap_helper`. Without the
    // layer the function fails at import.
    layers: [sharedPythonLayer],
    memorySize: 256,
    timeout: Duration.seconds(30),
    description: "Analyzes text from FSx for ONTAP S3 AP via Comprehend",
  }
);

api.addLambdaDataSource("ComprehendLambdaDataSource", comprehendFunction);

// --- Lambda Data Source for Glue Catalog ---
const glueCatalogRole = new iam.Role(dataStack, "GlueCatalogLambdaRole", {
  assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName(
      "service-role/AWSLambdaBasicExecutionRole"
    ),
  ],
  inlinePolicies: {
    GlueReadOnly: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          actions: [
            "glue:GetDatabases",
            "glue:GetDatabase",
            "glue:GetTables",
            "glue:GetTable",
            "glue:GetPartitions",
          ],
          resources: ["*"],
        }),
      ],
    }),
  },
});

const glueCatalogFunction = new lambda.Function(
  dataStack,
  "GlueCatalogFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_13,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/glue-catalog"),
    role: glueCatalogRole,
    environment: {},
    memorySize: 256,
    timeout: Duration.seconds(15),
    description: "Browses Glue Data Catalog for the file portal",
  }
);

api.addLambdaDataSource("GlueCatalogLambdaDataSource", glueCatalogFunction);


// --- cdk-nag: AWS Solutions Checks ---
// cdk-nag is NOT registered on every synth because Amplify Gen2 creates resources
// (AppSync, Cognito, internal S3 buckets, DynamoDB) that produce Non-Compliant findings
// which are NOT user-configurable, and a reported violation interrupts synthesis and
// blocks deployment.
//
// Instead, cdk-nag validation is performed in CI via a separate synth step:
//   CDK_NAG=1 npx ampx generate outputs --format cdk-nag-report
// This produces NagReport CSVs without blocking deployment.
//
// For local validation: npx vitest run (CDK harness tests check our custom resources)
//
// cdk-nag v3 moved from a CDK `IAspect` to CDK's native policy validation framework
// (`IPolicyValidationPlugin`), so adding the pack as an Aspect became
// `Validations.of(...).addPlugins(...)` and `NagSuppressions` was removed in favour of
// `Validations.of(...).acknowledge(...)`.
//
// The plugin is registered on the app root rather than on `dataStack` because a
// registered pack validates the whole app either way — measured, not assumed: a
// plugin added on one stack still reports findings in a sibling stack. Putting it on
// the root says that plainly instead of implying the scope narrows anything.
// Acknowledgments do narrow by scope, so those stay on `dataStack`.
const enableNag = process.env.CDK_NAG === "1";
if (enableNag) {
  Validations.of(dataStack.node.root).addPlugins(
    new AwsSolutionsChecks(dataStack.node.root, { verbose: true }),
  );
}

// Known acknowledgments — these are intentional design decisions, not oversights.
// Each one includes the rationale for future reviewers. Acknowledging on the stack
// covers the resources beneath it, including those in nested stacks.
Validations.of(dataStack).acknowledge(
  {
    id: "AwsSolutions-IAM5",
    reason:
      "Wildcard (*) resources are used for: (1) DynamoDB tables that are environment-specific " +
      "(resolved at deploy time), (2) Secrets Manager secrets (single secret per deployment), " +
      "(3) Glue catalog (read-only cross-database access). " +
      "Production deployments should scope these to specific ARNs via portal-config.ts.",
  },
  {
    id: "AwsSolutions-IAM4",
    reason:
      "AWS managed policies (AWSLambdaBasicExecutionRole, AWSLambdaVPCAccessExecutionRole) " +
      "are used for standard Lambda execution permissions. These are AWS-recommended for Lambda.",
  },
  {
    id: "AwsSolutions-L1",
    reason:
      "All Lambda functions explicitly use Python 3.13, matching `Runtime: python3.13` in the " +
      "SAM templates. cdk-nag may flag this if a newer runtime becomes available.",
  },
  {
    id: "AwsSolutions-COG4",
    reason:
      "Cognito User Pool is configured by Amplify Gen2 defineAuth with MFA=OPTIONAL and " +
      "email verification. Advanced security features (WAF, compromised credentials) are " +
      "production additions not included in this reference architecture.",
  },
  {
    id: "AwsSolutions-ASC3",
    reason:
      "AppSync GraphQL API request-level logging is managed by Amplify Gen2. " +
      "CloudWatch logging can be enabled in production via Amplify backend configuration.",
  },
  {
    id: "AwsSolutions-S1",
    reason:
      "S3 buckets (AmplifyCodegenAssets, modelIntrospectionSchema) are created and managed " +
      "by Amplify Gen2 internally. Server access logs are a production enhancement.",
  },
  {
    id: "AwsSolutions-S10",
    reason:
      "S3 bucket SSL-only policy is managed by Amplify Gen2. These are internal deployment " +
      "buckets not directly accessed by users.",
  },
);

// --- The auth stack's own IAM5 findings -------------------------------------------
//
// Held in `security/cdk-nag-baseline.txt` rather than acknowledged here, because
// `Validations.acknowledge` cannot express them. Two measured properties of that API
// decided it, and both are worth keeping written down:
//
//   A coarse id suppresses nothing. `acknowledge({ id: "AwsSolutions-IAM5" })` left all 18
//   findings on these roles in place, because cdk-nag reports each under a granular name
//   like `AwsSolutions-IAM5[Resource::<arn>]` and the coarse name matches none of them.
//   The acknowledgments listed above are coarse, which is why findings remain in the data
//   stack despite being described there as accepted.
//
//   It rejects an id containing more than one `::`, splitting on that delimiter to
//   separate an optional prefix. A granular id already carries one inside `[Resource::…]`,
//   and these ARNs now resolve through `Aws.REGION` and `Aws.ACCOUNT_ID`, which cdk-nag
//   renders as `<AWS::Region>` and `<AWS::AccountId>` -- two more. Acknowledging them
//   throws at synth.
//
// So the baseline is the mechanism: `scripts/check_cdk_nag_baseline.py` fails on a finding
// it does not know and on a recorded finding that has been fixed.
