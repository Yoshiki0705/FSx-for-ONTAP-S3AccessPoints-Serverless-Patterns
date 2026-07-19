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
    code: lambda.Code.fromInline(`
import os
import boto3
from botocore.config import Config

# Use SigV4 signing with explicit regional endpoint (required for FSx for ONTAP S3 AP)
region = os.environ.get("AWS_REGION", "ap-northeast-1")
s3 = boto3.client(
    "s3",
    region_name=region,
    endpoint_url=f"https://s3.{region}.amazonaws.com",
    config=Config(signature_version="s3v4"),
)

def handler(event, context):
    """Generate a presigned URL for an object on FSx for ONTAP S3 AP.

    Presigned URLs on FSx for ONTAP S3 AP are client-side SigV4 calculations
    that execute as standard GetObject requests. Verified working (2026-07-19).

    Args:
        event: { "key": "path/to/file.jpg", "expiresIn": 300 }
    Returns:
        { "url": "https://...", "expiresIn": 300 }
    """
    ap_alias = os.environ.get("S3_AP_ALIAS", "")
    key = event.get("key", "")
    expires_in = min(event.get("expiresIn", 300), 3600)  # Max 1 hour

    if not ap_alias or not key:
        return {"url": None, "expiresIn": 0, "error": "Missing S3_AP_ALIAS or key"}

    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": ap_alias, "Key": key},
            ExpiresIn=expires_in,
        )
        return {"url": url, "expiresIn": expires_in, "error": None}
    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        return {"url": None, "expiresIn": 0, "error": str(e)}
`),
    role: getPresignedUrlRole,
    environment: {
      S3_AP_ALIAS: config.s3ApAlias,
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
          actions: ["bedrock:InvokeModel"],
          resources: ["arn:aws:bedrock:*::foundation-model/*"],
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
    code: lambda.Code.fromInline(`
import os
import json
import boto3
from botocore.config import Config

region = os.environ.get("AWS_REGION", "ap-northeast-1")
s3 = boto3.client("s3", region_name=region, endpoint_url=f"https://s3.{region}.amazonaws.com", config=Config(signature_version="s3v4"))
bedrock = boto3.client("bedrock-runtime", region_name=region)

MAX_FILE_SIZE = 100 * 1024  # 100KB max for inline context
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

def handler(event, context):
    """Ask a question about a file on FSx for ONTAP S3 AP using Bedrock.

    Reads file content via S3 AP, sends to Bedrock with the user question,
    returns the AI-generated answer.
    """
    ap_alias = os.environ.get("S3_AP_ALIAS", "")
    key = event.get("key", "")
    question = event.get("question", "")

    if not ap_alias or not key or not question:
        return {"answer": "", "error": "Missing required parameters (key, question)"}

    try:
        # Get file content from S3 AP
        obj = s3.get_object(Bucket=ap_alias, Key=key)
        content_length = obj.get("ContentLength", 0)

        if content_length > MAX_FILE_SIZE:
            # Read first 100KB for large files
            body = obj["Body"].read(MAX_FILE_SIZE).decode("utf-8", errors="replace")
            body += f"\\n\\n[Truncated: file is {content_length} bytes, showing first {MAX_FILE_SIZE} bytes]"
        else:
            body = obj["Body"].read().decode("utf-8", errors="replace")

        # Build prompt
        prompt = f"""Based on the following file content, answer the user's question concisely.

File: {key}
Content:
---
{body}
---

Question: {question}

Answer:"""

        # Call Bedrock
        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": 1024,
                    "temperature": 0.3,
                    "topP": 0.9,
                }
            }),
        )

        result = json.loads(response["body"].read())
        answer = result.get("results", [{}])[0].get("outputText", "")
        if not answer:
            # Try Claude/Nova response format
            answer = result.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "")
        if not answer:
            answer = json.dumps(result)[:500]

        return {"answer": answer, "model": MODEL_ID, "error": None}

    except Exception as e:
        print(f"Error: {e}")
        return {"answer": "", "model": MODEL_ID, "error": str(e)}
`),
    role: askAboutFileRole,
    environment: {
      S3_AP_ALIAS: config.s3ApAlias,
      BEDROCK_MODEL_ID: "amazon.nova-lite-v1:0",
    },
    memorySize: 512,
    timeout: Duration.seconds(60),
    description: "Asks Bedrock about file content from FSx for ONTAP S3 AP",
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
    code: lambda.Code.fromInline(`
import os
import json
import boto3
from botocore.config import Config

region = os.environ.get("AWS_REGION", "ap-northeast-1")
s3 = boto3.client("s3", region_name=region, endpoint_url=f"https://s3.{region}.amazonaws.com", config=Config(signature_version="s3v4"))
rekognition = boto3.client("rekognition", region_name=region)

def handler(event, context):
    """Detect objects/labels in an image file on FSx for ONTAP S3 AP using Rekognition.

    Downloads image via S3 AP, sends to Rekognition DetectLabels,
    returns labels with bounding boxes and confidence scores.
    """
    ap_alias = os.environ.get("S3_AP_ALIAS", "")
    key = event.get("key", "")
    max_labels = event.get("maxLabels", 10)
    min_confidence = event.get("minConfidence", 70.0)

    if not ap_alias or not key:
        return {"labels": [], "error": "Missing required parameters (key)"}

    try:
        # Get image from S3 AP
        obj = s3.get_object(Bucket=ap_alias, Key=key)
        image_bytes = obj["Body"].read()

        # Detect labels
        response = rekognition.detect_labels(
            Image={"Bytes": image_bytes},
            MaxLabels=max_labels,
            MinConfidence=min_confidence,
        )

        labels = []
        for label in response.get("Labels", []):
            label_data = {
                "name": label["Name"],
                "confidence": round(label["Confidence"], 1),
                "instances": [],
            }
            for instance in label.get("Instances", []):
                box = instance.get("BoundingBox", {})
                label_data["instances"].append({
                    "boundingBox": {
                        "width": round(box.get("Width", 0), 4),
                        "height": round(box.get("Height", 0), 4),
                        "left": round(box.get("Left", 0), 4),
                        "top": round(box.get("Top", 0), 4),
                    },
                    "confidence": round(instance.get("Confidence", 0), 1),
                })
            labels.append(label_data)

        return {"labels": labels, "imageWidth": None, "imageHeight": None, "error": None}

    except Exception as e:
        print(f"Error: {e}")
        return {"labels": [], "error": str(e)}
`),
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
    code: lambda.Code.fromInline(`
import os
import json
import time
import boto3

region = os.environ.get("AWS_REGION", "ap-northeast-1")
athena = boto3.client("athena", region_name=region)

WORKGROUP = os.environ.get("ATHENA_WORKGROUP", "primary")
OUTPUT_LOCATION = os.environ.get("ATHENA_OUTPUT_LOCATION", "")

def handler(event, context):
    """Execute an Athena SQL query and return results.

    Starts query execution, polls for completion, and returns results.
    Max wait: 30 seconds (then returns execution ID for async polling).
    """
    sql = event.get("sql", "")
    database = event.get("database", "default")

    if not sql:
        return {"columns": [], "rows": [], "status": "ERROR", "error": "No SQL query provided"}

    try:
        params = {
            "QueryString": sql,
            "QueryExecutionContext": {"Database": database},
            "WorkGroup": WORKGROUP,
        }
        if OUTPUT_LOCATION:
            params["ResultConfiguration"] = {"OutputLocation": OUTPUT_LOCATION}

        response = athena.start_query_execution(**params)
        execution_id = response["QueryExecutionId"]

        # Poll for completion (max 30s)
        for _ in range(30):
            time.sleep(1)
            status_resp = athena.get_query_execution(QueryExecutionId=execution_id)
            state = status_resp["QueryExecution"]["Status"]["State"]
            if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
                break

        if state != "SUCCEEDED":
            reason = status_resp["QueryExecution"]["Status"].get("StateChangeReason", "")
            return {"columns": [], "rows": [], "status": state, "error": reason, "executionId": execution_id}

        # Get results
        results = athena.get_query_results(QueryExecutionId=execution_id, MaxResults=100)
        columns = [col["Name"] for col in results["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]]
        rows = []
        for row in results["ResultSet"]["Rows"][1:]:  # Skip header
            rows.append([datum.get("VarCharValue", "") for datum in row["Data"]])

        return {"columns": columns, "rows": rows, "status": "SUCCEEDED", "error": None, "executionId": execution_id}

    except Exception as e:
        return {"columns": [], "rows": [], "status": "ERROR", "error": str(e)}
`),
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
    code: lambda.Code.fromInline(`
import os
import json
import boto3
from botocore.config import Config

region = os.environ.get("AWS_REGION", "ap-northeast-1")
s3 = boto3.client("s3", region_name=region, endpoint_url=f"https://s3.{region}.amazonaws.com", config=Config(signature_version="s3v4"))
textract = boto3.client("textract", region_name=region)

def handler(event, context):
    """Extract text from a document/image on FSx for ONTAP S3 AP using Textract."""
    ap_alias = os.environ.get("S3_AP_ALIAS", "")
    key = event.get("key", "")
    mode = event.get("mode", "text")  # "text" or "analyze"

    if not ap_alias or not key:
        return {"text": "", "blocks": [], "error": "Missing parameters"}

    try:
        obj = s3.get_object(Bucket=ap_alias, Key=key)
        doc_bytes = obj["Body"].read()

        if mode == "analyze":
            response = textract.analyze_document(
                Document={"Bytes": doc_bytes},
                FeatureTypes=["TABLES", "FORMS"],
            )
        else:
            response = textract.detect_document_text(
                Document={"Bytes": doc_bytes}
            )

        # Extract text lines
        lines = []
        for block in response.get("Blocks", []):
            if block["BlockType"] == "LINE":
                lines.append(block["Text"])

        return {
            "text": "\\n".join(lines),
            "blockCount": len(response.get("Blocks", [])),
            "pageCount": len([b for b in response.get("Blocks", []) if b["BlockType"] == "PAGE"]),
            "error": None,
        }

    except Exception as e:
        return {"text": "", "blockCount": 0, "pageCount": 0, "error": str(e)}
`),
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
    code: lambda.Code.fromInline(`
import os
import json
import boto3
from botocore.config import Config

region = os.environ.get("AWS_REGION", "ap-northeast-1")
s3 = boto3.client("s3", region_name=region, endpoint_url=f"https://s3.{region}.amazonaws.com", config=Config(signature_version="s3v4"))
comprehend = boto3.client("comprehend", region_name=region)

MAX_TEXT_SIZE = 5000  # Comprehend limit per request

def handler(event, context):
    """Analyze text file from FSx for ONTAP S3 AP using Comprehend."""
    ap_alias = os.environ.get("S3_AP_ALIAS", "")
    key = event.get("key", "")
    analysis_type = event.get("analysisType", "entities")  # entities, sentiment, keyPhrases

    if not ap_alias or not key:
        return {"results": [], "error": "Missing parameters"}

    try:
        obj = s3.get_object(Bucket=ap_alias, Key=key)
        text = obj["Body"].read(MAX_TEXT_SIZE).decode("utf-8", errors="replace")

        if analysis_type == "sentiment":
            response = comprehend.detect_sentiment(Text=text, LanguageCode="en")
            return {
                "results": {
                    "sentiment": response["Sentiment"],
                    "scores": response["SentimentScore"],
                },
                "error": None,
            }
        elif analysis_type == "keyPhrases":
            response = comprehend.detect_key_phrases(Text=text, LanguageCode="en")
            phrases = [{"text": p["Text"], "score": round(p["Score"], 3)} for p in response["KeyPhrases"][:20]]
            return {"results": phrases, "error": None}
        else:  # entities
            response = comprehend.detect_entities(Text=text, LanguageCode="en")
            entities = [
                {"text": e["Text"], "type": e["Type"], "score": round(e["Score"], 3)}
                for e in response["Entities"][:30]
            ]
            return {"results": entities, "error": None}

    except Exception as e:
        return {"results": [], "error": str(e)}
`),
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
    code: lambda.Code.fromInline(`
import os
import json
import boto3

region = os.environ.get("AWS_REGION", "ap-northeast-1")
glue = boto3.client("glue", region_name=region)

def handler(event, context):
    """Browse Glue Data Catalog — databases, tables, and schema."""
    action = event.get("action", "listDatabases")
    database = event.get("database", "")
    table = event.get("table", "")

    try:
        if action == "listDatabases":
            response = glue.get_databases(MaxResults=50)
            databases = [{"name": db["Name"], "description": db.get("Description", "")} for db in response["DatabaseList"]]
            return {"databases": databases, "error": None}

        elif action == "listTables":
            if not database:
                return {"tables": [], "error": "database required"}
            response = glue.get_tables(DatabaseName=database, MaxResults=50)
            tables = [
                {
                    "name": t["Name"],
                    "description": t.get("Description", ""),
                    "columns": len(t.get("StorageDescriptor", {}).get("Columns", [])),
                    "location": t.get("StorageDescriptor", {}).get("Location", ""),
                }
                for t in response["TableList"]
            ]
            return {"tables": tables, "error": None}

        elif action == "getSchema":
            if not database or not table:
                return {"schema": [], "error": "database and table required"}
            response = glue.get_table(DatabaseName=database, Name=table)
            columns = [
                {"name": c["Name"], "type": c["Type"], "comment": c.get("Comment", "")}
                for c in response["Table"].get("StorageDescriptor", {}).get("Columns", [])
            ]
            partition_keys = [
                {"name": p["Name"], "type": p["Type"]}
                for p in response["Table"].get("PartitionKeys", [])
            ]
            return {
                "schema": columns,
                "partitionKeys": partition_keys,
                "location": response["Table"].get("StorageDescriptor", {}).get("Location", ""),
                "error": None,
            }

        return {"error": f"Unknown action: {action}"}

    except Exception as e:
        return {"error": str(e)}
`),
    role: glueCatalogRole,
    environment: {},
    memorySize: 256,
    timeout: Duration.seconds(15),
    description: "Browses Glue Data Catalog for the file portal",
  }
);

api.addLambdaDataSource("GlueCatalogLambdaDataSource", glueCatalogFunction);
