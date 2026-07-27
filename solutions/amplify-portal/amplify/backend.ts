import { defineBackend } from "@aws-amplify/backend";
import { auth } from "./auth/resource";
import { data } from "./data/resource";
import { config } from "./portal-config";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import { Aspects, Duration, Stack } from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
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

const listFilesFunction = new lambda.Function(dataStack, "ListFilesFunction", {
  runtime: lambda.Runtime.PYTHON_3_12,
  architecture: lambda.Architecture.ARM_64,
  handler: "index.handler",
  code: lambda.Code.fromAsset("functions/list-files"),
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
    code: lambda.Code.fromAsset("functions/presigned-url"),
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
    code: lambda.Code.fromAsset("functions/snapshots"),
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
// Provides: blockSmbUser, unblockSmbUser, blockNfsIp, unblockNfsIp,
//           containThreat, listActiveBlocks, disconnectSessions
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
    code: lambda.Code.fromAsset("functions/data-protection"),
    role: arpResponseRole,
    environment: {
      ONTAP_MGMT_IP: config.ontapMgmtIp,
      ONTAP_SECRET_NAME: config.ontapSecretName,
      VOLUME_NAME: config.ontapVolumeName,
      SVM_NAME: config.ontapSvmName,
    },
    memorySize: 256,
    timeout: Duration.seconds(60),
    description:
      "ARP/AI response actions — user/IP blocking, snapshot, session disconnect (VPC Lambda, ONTAP REST)",
    ...(vpcConfig && { vpc: vpcConfig.vpc, securityGroups: vpcConfig.securityGroups, vpcSubnets: vpcConfig.vpcSubnets }),
  }
);

api.addLambdaDataSource("ArpResponseLambdaDataSource", arpResponseFunction);

// --- Lambda Data Source for Resource Management (Admin) ---
// Uses functions/resource-management/handler.py
// Provides: Volume CRUD, Export Policy, QoS Policy, SnapLock management
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
    code: lambda.Code.fromAsset("functions/resource-management"),
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
      "Resource management — Volume/ExportPolicy/QoS/SnapLock/S3ObjectLock CRUD (VPC Lambda, ONTAP REST + S3)",
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
    code: lambda.Code.fromAsset("functions/search-files"),
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
    code: lambda.Code.fromAsset("functions/agent-chat"),
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
    code: lambda.Code.fromAsset("functions/audit-log"),
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
    code: lambda.Code.fromAsset("functions/file-metadata"),
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
    code: lambda.Code.fromAsset("functions/generate-qr"),
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
    code: lambda.Code.fromAsset("functions/ask-about-file"),
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
    code: lambda.Code.fromAsset("functions/detect-labels"),
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
    code: lambda.Code.fromAsset("functions/athena-query"),
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
    code: lambda.Code.fromAsset("functions/textract"),
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
    code: lambda.Code.fromAsset("functions/comprehend-analysis"),
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
    code: lambda.Code.fromAsset("functions/glue-catalog"),
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
