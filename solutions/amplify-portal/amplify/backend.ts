import { defineBackend } from "@aws-amplify/backend";
import { auth } from "./auth/resource";
import { data } from "./data/resource";
import { config } from "./portal-config";
import * as crypto from "crypto";
import * as fs from "fs";
import * as path from "path";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as s3 from "aws-cdk-lib/aws-s3";
import { AssetHashType, Aspects, Duration, RemovalPolicy, Stack } from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import * as cloudwatchActions from "aws-cdk-lib/aws-cloudwatch-actions";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
import * as sns from "aws-cdk-lib/aws-sns";
import * as subscriptions from "aws-cdk-lib/aws-sns-subscriptions";
import { AwsSolutionsChecks, NagSuppressions } from "cdk-nag";

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

// --- Storage Browser IAM: Add S3 AP access to Cognito Identity Pool authenticated role ---
// This ensures the Upload tab (Storage Browser for S3) can access the S3 AP
// directly from the browser without manual IAM configuration.
const authResources = backend.auth.resources;
const identityPoolId = authResources.cfnResources.cfnIdentityPool.ref;

// Get the authenticated role created by Amplify Auth
const authenticatedRole = authResources.authenticatedUserIamRole;

// Add S3 AP permissions for Storage Browser (Upload tab)
authenticatedRole.addToPrincipalPolicy(
  new iam.PolicyStatement({
    sid: "StorageBrowserS3APAccess",
    actions: [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ],
    resources: config.s3ApResourceArns,
  })
);

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

if (vpcConfig && config.vpcRouteTableIds.length > 0) {
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
const portalSettingsTable = new dynamodb.Table(dataStack, "PortalSettingsTable", {
  partitionKey: { name: "settingKey", type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
  removalPolicy: Stack.of(dataStack).stackName.includes("sandbox")
    ? undefined // default RETAIN for sandbox
    : undefined,
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
});

// --- DynamoDB Table for Multi-Agent Teams ---
// PK: teamId (UUID). Stores: name, description, agents (list), createdBy
const agentTeamsTable = new dynamodb.Table(dataStack, "AgentTeamsTable", {
  partitionKey: { name: "teamId", type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
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
  pointInTimeRecovery: true,
});

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
          actions: ["s3:ListBucket", "s3:GetObject", "s3:GetBucketLocation", "s3:PutObject", "s3:DeleteObject", "s3:CopyObject"],
          resources: config.s3ApResourceArns,
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

const sharedPythonLayer = new lambda.LayerVersion(dataStack, "SharedPythonLayer", {
  description:
    "Repository shared/ Python modules (ONTAP client and ARP containment actions) " +
    `at /opt/python/shared [sources ${sharedSourcesFingerprint}]`,
  compatibleRuntimes: [lambda.Runtime.PYTHON_3_12],
  compatibleArchitectures: [lambda.Architecture.ARM_64],
  code: lambda.Code.fromAsset(sharedModulesDir, {
    exclude: ["tests", "tests/**", "__pycache__", "**/__pycache__", "*.pyc"],
    // Hash the staged tree, not the source directory. With a source hash, fixing
    // the bundler does not change the asset key, so CDK reuses the object it
    // already uploaded — which is how a corrected bundler still produced a layer
    // containing the earlier, incomplete file set.
    assetHashType: AssetHashType.OUTPUT,
    bundling: {
      image: lambda.Runtime.PYTHON_3_12.bundlingImage,
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

const listFilesFunction = new lambda.Function(dataStack, "ListFilesFunction", {
  runtime: lambda.Runtime.PYTHON_3_12,
  architecture: lambda.Architecture.ARM_64,
  handler: "index.handler",
  code: functionCode("functions/list-files"),
  role: listFilesRole,
  environment: {
    S3_AP_ALIAS: config.s3ApAlias,
    GROUP_AP_MAPPING: JSON.stringify(config.groupApMapping || {}),
  },
  memorySize: 256,
  timeout: Duration.seconds(30),
  description: "Lists files in FSx for ONTAP S3 AP with group-based AP routing",
});

api.addLambdaDataSource("ListFilesLambdaDataSource", listFilesFunction);

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
          resources: config.s3ApResourceArns,
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
    runtime: lambda.Runtime.PYTHON_3_12,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/folder-download"),
    role: folderDownloadRole,
    environment: {
      S3_AP_ALIAS: config.s3ApAlias,
      GROUP_AP_MAPPING: JSON.stringify(config.groupApMapping || {}),
      ZIP_TEMP_BUCKET: zipTempBucket.bucketName,
    },
    // ZIP assembly is memory and time bound; see the caps in the handler.
    memorySize: 1024,
    timeout: Duration.minutes(5),
    description:
      "Builds a ZIP of an S3 Access Point prefix and returns a presigned download URL",
  }
);

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
          resources: config.s3ApResourceArns,
        }),
        new iam.PolicyStatement({
          actions: ["dynamodb:PutItem"],
          resources: ["*"], // Restrict to URL_AUDIT_TABLE ARN in production
        }),
      ],
    }),
  },
});

const getPresignedUrlFunction = new lambda.Function(
  dataStack,
  "GetPresignedUrlFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_12,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/presigned-url"),
    role: getPresignedUrlRole,
    environment: {
      S3_AP_ALIAS: config.s3ApAlias,
      URL_AUDIT_TABLE_NAME: process.env.URL_AUDIT_TABLE_NAME || "",
    },
    memorySize: 128,
    timeout: Duration.seconds(10),
    description: "Generates presigned URLs for FSx for ONTAP S3 AP file preview/download",
  }
);

api.addLambdaDataSource(
  "GetPresignedUrlLambdaDataSource",
  getPresignedUrlFunction
);

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
    runtime: lambda.Runtime.PYTHON_3_12,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/snapshots"),
    role: listSnapshotsRole,
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
//           getArpSuspects, getSnapLockConfig, getS3ObjectLockStatus,
//           getProtectionSummary, createSnapshot, deleteSnapshot,
//           updateArpState, updateRetentionPolicy
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
    runtime: lambda.Runtime.PYTHON_3_12,
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
    runtime: lambda.Runtime.PYTHON_3_12,
    architecture: lambda.Architecture.ARM_64,
    handler: "handler.handler",
    code: functionCode("functions/resource-management"),
    role: resourceMgmtRole,
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
          resources: config.s3ApResourceArns.length > 0
            ? config.s3ApResourceArns
            : ["arn:aws:s3:*:*:accesspoint/*", "arn:aws:s3:*:*:accesspoint/*/object/*"],
        }),
      ],
    }),
  },
});

const searchFilesFunction = new lambda.Function(
  dataStack,
  "SearchFilesFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_12,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/search-files"),
    role: searchFilesRole,
    environment: {
      BEDROCK_KB_ID: config.bedrockKbId || "",
      S3_AP_ALIAS: config.s3ApAlias,
    },
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
          resources: config.s3ApResourceArns.length > 0
            ? config.s3ApResourceArns
            : ["arn:aws:s3:*:*:accesspoint/*", "arn:aws:s3:*:*:accesspoint/*/object/*"],
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
    runtime: lambda.Runtime.PYTHON_3_12,
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
      GROUP_PATH_PREFIXES: JSON.stringify(config.groupApMapping ? Object.fromEntries(
        Object.entries(config.groupApMapping).map(([group]) => [group, [`${group}/`, "shared/"]])
      ) : {}),
    },
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
    runtime: lambda.Runtime.PYTHON_3_12,
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
    },
    memorySize: 256,
    timeout: Duration.seconds(60),
    description:
      "Queries CloudTrail S3 data events via Athena for file access audit trail",
  }
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
    runtime: lambda.Runtime.PYTHON_3_12,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/file-metadata"),
    role: getFileMetadataRole,
    environment: {
      AI_METADATA_TABLE_NAME: process.env.AI_METADATA_TABLE_NAME || "",
    },
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
          resources: config.s3ApResourceArns,
        }),
      ],
    }),
  },
});

const generateQrCodeFunction = new lambda.Function(
  dataStack,
  "GenerateQrCodeFunction",
  {
    runtime: lambda.Runtime.PYTHON_3_12,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/generate-qr"),
    role: generateQrCodeRole,
    environment: {
      S3_AP_ALIAS: config.s3ApAlias,
      MAX_QR_EXPIRY_SECONDS: "300",
    },
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
          resources: config.s3ApResourceArns,
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
    runtime: lambda.Runtime.PYTHON_3_12,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/ask-about-file"),
    role: askAboutFileRole,
    environment: {
      S3_AP_ALIAS: config.s3ApAlias,
      BEDROCK_MODEL_ID: "amazon.nova-lite-v1:0",
      CLASSIFICATION_TABLE_NAME:
        process.env.CLASSIFICATION_TABLE_NAME || "",
      AI_BLOCKED_LEVELS:
        process.env.AI_BLOCKED_LEVELS || "CONFIDENTIAL,CUI,HIGHLY_RESTRICTED,RESTRICTED",
    },
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
          resources: config.s3ApResourceArns,
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
    runtime: lambda.Runtime.PYTHON_3_12,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/detect-labels"),
    role: detectLabelsRole,
    environment: {
      S3_AP_ALIAS: config.s3ApAlias,
    },
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
            ...config.s3ApResourceArns,
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
    runtime: lambda.Runtime.PYTHON_3_12,
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
          resources: config.s3ApResourceArns,
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
    runtime: lambda.Runtime.PYTHON_3_12,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/textract"),
    role: textractRole,
    environment: {
      S3_AP_ALIAS: config.s3ApAlias,
    },
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
          resources: config.s3ApResourceArns,
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
    runtime: lambda.Runtime.PYTHON_3_12,
    architecture: lambda.Architecture.ARM_64,
    handler: "index.handler",
    code: functionCode("functions/comprehend-analysis"),
    role: comprehendRole,
    environment: {
      S3_AP_ALIAS: config.s3ApAlias,
    },
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
    runtime: lambda.Runtime.PYTHON_3_12,
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


// --- cdk-nag: Apply AWS Solutions Checks ---
// --- cdk-nag: AWS Solutions Checks ---
// cdk-nag is NOT applied as a CDK Aspect here because Amplify Gen2 creates resources
// (AppSync, Cognito, internal S3 buckets, DynamoDB) that produce Non-Compliant findings
// which are NOT user-configurable, causing [AssemblyError] and blocking deployment.
//
// Instead, cdk-nag validation is performed in CI via a separate synth step:
//   CDK_NAG=1 npx ampx generate outputs --format cdk-nag-report
// This produces NagReport CSVs without blocking deployment.
//
// For local validation: npx vitest run (CDK harness tests check our custom resources)
//
// Suppressions are documented here for reference (applied when CDK_NAG=1):
const enableNag = process.env.CDK_NAG === "1";
if (enableNag) {
  Aspects.of(dataStack).add(new AwsSolutionsChecks({ verbose: true, logIgnores: true }));
}

// Known suppressions — these are intentional design decisions, not oversights.
// Each suppression includes the rationale for future reviewers.
// apply_to_children: true ensures suppressions propagate to nested stack resources.
NagSuppressions.addStackSuppressions(dataStack, [
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
      "All Lambda functions explicitly use Python 3.12 (latest supported runtime as of 2026-07). " +
      "cdk-nag may flag this if a newer runtime becomes available.",
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
], true);
