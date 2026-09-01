import { Stack, Duration, CfnOutput } from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import { CfnParameter } from "aws-cdk-lib";

/**
 * CDK Custom Stack: Step Functions + S3 AP Integration
 *
 * This stack:
 * 1. Creates an HTTP data source for AppSync → Step Functions direct integration
 * 2. Creates a Lambda data source for AppSync → ListFiles (S3 AP)
 * 3. Grants necessary IAM permissions
 *
 * It does NOT create new Step Functions state machines — it references
 * existing deployed state machines from the core serverless patterns.
 *
 * Prerequisites:
 * - Deploy at least one UC pattern (e.g., make deploy-uc1)
 * - Note the State Machine ARN from the deployment output
 * - Set the ARN in the parameter below (or use SSM Parameter Store)
 */
// `_backend` is typed `unknown` rather than a backend type: this function has
// no callers yet (the wiring at the bottom of this file is still commented out),
// and it previously imported `DefineBackendBase`, which `@aws-amplify/backend`
// does not export. That went unnoticed because `amplify/` was outside the
// tsconfig include list. Give it a real type when the call site lands.
export function stepFunctionsStack(stack: Stack, _backend: unknown) {
  // --- Parameters ---
  const stateMachineArnParam = new CfnParameter(stack, "StateMachineArn", {
    type: "String",
    description:
      "ARN of the deployed Step Functions state machine (from UC pattern deployment). " +
      "Example: arn:aws:states:ap-northeast-1:123456789012:stateMachine:uc1-legal-compliance-workflow",
    default: "",
  });

  const s3ApAliasParam = new CfnParameter(stack, "S3AccessPointAlias", {
    type: "String",
    description:
      "S3 Access Point alias for file listing. " +
      "Example: myap-abc123-s3alias",
    default: "",
  });

  // Kept, not deleted: constructing a CfnParameter is what adds the
  // TargetRegion parameter to the synthesized template. Removing the binding
  // would remove the parameter, which is a template change rather than a
  // cleanup. The `void` below satisfies noUnusedLocals, which — unlike ESLint —
  // has no underscore-prefix exemption.
  const awsRegionParam = new CfnParameter(stack, "TargetRegion", {
    type: "String",
    description: "AWS Region where Step Functions and S3 AP are deployed",
    default: "ap-northeast-1",
  });

  // --- IAM Role for AppSync HTTP Data Source (Step Functions) ---
  // Kept for the same reason as TargetRegion above: the role is created for its
  // presence in the stack, and the data-source wiring that will consume it is
  // still commented out at the bottom of this file.
  const sfnDataSourceRole = new iam.Role(stack, "SfnDataSourceRole", {
    assumedBy: new iam.ServicePrincipal("appsync.amazonaws.com"),
    description: "Allows AppSync to invoke Step Functions StartExecution and DescribeExecution",
    inlinePolicies: {
      StepFunctionsInvoke: new iam.PolicyDocument({
        statements: [
          new iam.PolicyStatement({
            actions: [
              "states:StartExecution",
              "states:DescribeExecution",
              "states:StopExecution",
            ],
            resources: [
              // Allow all state machines in the account (scoped by region)
              // For tighter security, replace with specific ARN patterns
              `arn:aws:states:*:${Stack.of(stack).account}:stateMachine:*`,
              `arn:aws:states:*:${Stack.of(stack).account}:execution:*:*`,
            ],
          }),
        ],
      }),
    },
  });

  // --- IAM Role for ListFiles Lambda ---
  const listFilesRole = new iam.Role(stack, "ListFilesLambdaRole", {
    assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
    managedPolicies: [
      iam.ManagedPolicy.fromAwsManagedPolicyName("service-role/AWSLambdaBasicExecutionRole"),
    ],
    inlinePolicies: {
      S3APAccess: new iam.PolicyDocument({
        statements: [
          new iam.PolicyStatement({
            actions: ["s3:ListBucket", "s3:GetObject", "s3:GetBucketLocation"],
            resources: [
              `arn:aws:s3:*:${Stack.of(stack).account}:accesspoint/*`,
              `arn:aws:s3:*:${Stack.of(stack).account}:accesspoint/*/object/*`,
            ],
          }),
        ],
      }),
    },
  });

  // --- ListFiles Lambda Function ---
  // This Lambda lists objects in the S3 AP. It runs VPC-external
  // (no VpcConfig) for Internet-origin S3 AP access.
  const listFilesFunction = new lambda.Function(stack, "ListFilesFunction", {
    runtime: lambda.Runtime.PYTHON_3_13,
    architecture: lambda.Architecture.ARM_64,
    handler: "handler.handler",
    code: lambda.Code.fromInline(`
import json
import logging
import os
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

def handler(event, context):
    """List files in S3 AP with pagination and directory navigation support."""
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

        # Common prefixes represent "directories"
        folders = [
            {
                "key": cp["Prefix"],
                "size": 0,
                "lastModified": None,
                "storageClass": "DIRECTORY",
            }
            for cp in response.get("CommonPrefixes", [])
        ]

        # Contents represent files at this level
        files = [
            {
                "key": obj["Key"],
                "size": obj["Size"],
                "lastModified": obj["LastModified"].isoformat(),
                "storageClass": obj.get("StorageClass", "STANDARD"),
            }
            for obj in response.get("Contents", [])
            if not obj["Key"].endswith("/")  # Exclude folder marker objects
        ]

        return {
            "files": folders + files,
            "isTruncated": response.get("IsTruncated", False),
            "nextContinuationToken": response.get("NextContinuationToken"),
        }
    except Exception:
        # An empty listing is what the caller sees either way, so the traceback is the
        # only record that the prefix failed rather than being empty. \`print\` reached
        # CloudWatch but carried no level and no stack, so a failure here was
        # indistinguishable from routine output when reading the log.
        #
        # \`shared/observability.py\` is not reachable from inline code: the layer that
        # carries \`shared/\` is mounted at /opt/python for the functions bundled from
        # disk, and this one has no layer attached.
        logger.exception("Failed to list files under prefix %r", prefix)
        return {"files": [], "isTruncated": False, "nextContinuationToken": None}
`),
    role: listFilesRole,
    environment: {
      S3_AP_ALIAS: s3ApAliasParam.valueAsString,
    },
    memorySize: 256,
    timeout: Duration.seconds(30),
    description: "Lists files in FSx for ONTAP S3 Access Point for the Amplify portal",
  });

  // --- Outputs for cross-referencing ---
  new CfnOutput(stack, "StateMachineArnOutput", {
    value: stateMachineArnParam.valueAsString,
    description: "State Machine ARN configured for this portal",
  });

  new CfnOutput(stack, "ListFilesFunctionArn", {
    value: listFilesFunction.functionArn,
    description: "ARN of the ListFiles Lambda function",
  });

  // Note: The actual AppSync data source wiring happens when Amplify
  // deploys the backend. The data source names referenced in resource.ts
  // ("StepFunctionsHttpDataSource", "ListFilesLambdaDataSource") will be
  // connected to these resources during the CDK synthesis phase.
  //
  // For the skeleton, this demonstrates the pattern.
  // Full wiring requires:
  //   1. backend.data.resources.graphqlApi (access the generated API)
  //   2. Create HttpDataSource with endpoint + role
  //   3. Create LambdaDataSource with the listFilesFunction
  //
  // This will be completed when the Amplify sandbox is first deployed
  // and the GraphQL API resource becomes available.

  // Both constructs above exist for their effect on the stack, not for their
  // bindings. Referencing them here keeps noUnusedLocals satisfied without
  // deleting resources from the synthesized template.
  void awsRegionParam;
  void sfnDataSourceRole;
}
