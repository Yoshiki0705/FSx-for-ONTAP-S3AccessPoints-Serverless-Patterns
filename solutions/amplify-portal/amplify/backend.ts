import { defineBackend } from "@aws-amplify/backend";
import { auth } from "./auth/resource";
import { data } from "./data/resource";
import { config } from "./portal-config";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import { Duration, Stack } from "aws-cdk-lib";

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

// Access the data stack (same stack where AppSync API lives)
const dataResources = backend.data.resources;
const api = dataResources.graphqlApi;
const dataStack = Stack.of(api);

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
          actions: ["s3:ListBucket", "s3:GetObject", "s3:GetBucketLocation"],
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
  code: lambda.Code.fromInline(`
import os
import boto3

s3 = boto3.client("s3")

def handler(event, context):
    """List files in S3 AP with pagination and directory navigation.

    Supports both FSx for ONTAP S3 Access Points and regular S3 buckets.
    Set S3_AP_ALIAS environment variable to the AP alias or bucket name.
    Uses Delimiter='/' for directory-style navigation (CommonPrefixes).
    """
    ap_alias = os.environ.get("S3_AP_ALIAS", "")
    prefix = event.get("prefix", "")
    max_keys = event.get("maxKeys", 100)
    continuation_token = event.get("continuationToken")

    if not ap_alias:
        return {"files": [], "isTruncated": False, "nextContinuationToken": None}

    params = {
        "Bucket": ap_alias,
        "Prefix": prefix,
        "Delimiter": "/",
        "MaxKeys": min(max_keys, 1000),
    }
    if continuation_token:
        params["ContinuationToken"] = continuation_token

    try:
        response = s3.list_objects_v2(**params)
        folders = [
            {"key": cp["Prefix"], "size": 0, "lastModified": None, "storageClass": "DIRECTORY"}
            for cp in response.get("CommonPrefixes", [])
        ]
        files = [
            {
                "key": obj["Key"],
                "size": obj["Size"],
                "lastModified": obj["LastModified"].isoformat(),
                "storageClass": obj.get("StorageClass", "STANDARD"),
            }
            for obj in response.get("Contents", [])
            if not obj["Key"].endswith("/")
        ]
        return {
            "files": folders + files,
            "isTruncated": response.get("IsTruncated", False),
            "nextContinuationToken": response.get("NextContinuationToken"),
        }
    except Exception as e:
        print(f"Error listing files: {e}")
        return {"files": [], "isTruncated": False, "nextContinuationToken": None}
`),
  role: listFilesRole,
  environment: {
    S3_AP_ALIAS: config.s3ApAlias,
  },
  memorySize: 256,
  timeout: Duration.seconds(30),
  description: "Lists files in FSx for ONTAP S3 AP for Amplify portal",
});

api.addLambdaDataSource("ListFilesLambdaDataSource", listFilesFunction);
