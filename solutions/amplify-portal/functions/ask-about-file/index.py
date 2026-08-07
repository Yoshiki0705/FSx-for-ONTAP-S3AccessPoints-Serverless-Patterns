import os

import boto3
from botocore.config import Config

region = os.environ.get("AWS_REGION", "ap-northeast-1")
s3 = boto3.client(
    "s3", region_name=region, endpoint_url=f"https://s3.{region}.amazonaws.com", config=Config(signature_version="s3v4")
)
bedrock = boto3.client("bedrock-runtime", region_name=region)

MAX_FILE_SIZE = 100 * 1024  # 100KB max for inline context
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
CLASSIFICATION_TABLE = os.environ.get("CLASSIFICATION_TABLE_NAME", "")
AI_BLOCKED_LEVELS = set(
    level.strip().upper()
    for level in os.environ.get("AI_BLOCKED_LEVELS", "CONFIDENTIAL,CUI,HIGHLY_RESTRICTED,RESTRICTED").split(",")
    if level.strip()
)


def check_classification(file_key: str) -> tuple[bool, str]:
    """Check if file is allowed for AI processing based on classification.

    Returns (allowed: bool, classification: str).
    If no classification table is configured or file is unclassified, allows by default.
    """
    if not CLASSIFICATION_TABLE:
        return True, "UNCLASSIFIED"

    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(CLASSIFICATION_TABLE)

        # Check file-level classification
        resp = table.get_item(Key={"file_key": file_key})
        if resp.get("Item"):
            classification = resp["Item"].get("classification", "").upper()
            return classification not in AI_BLOCKED_LEVELS, classification

        # Check folder-level classification (walk up path)
        parts = file_key.rsplit("/", 1)
        while len(parts) == 2 and parts[0]:
            folder_key = parts[0] + "/"
            resp = table.get_item(Key={"file_key": folder_key})
            if resp.get("Item"):
                classification = resp["Item"].get("classification", "").upper()
                return classification not in AI_BLOCKED_LEVELS, classification
            parts = parts[0].rsplit("/", 1)

        return True, "UNCLASSIFIED"
    except Exception as e:
        print(f"Classification check warning: {e}")
        return True, "UNKNOWN"


def handler(event, context):
    """Ask a question about a file on FSx for ONTAP S3 AP using Bedrock.

    Includes CONFIDENTIAL guardrail: checks data classification before
    sending file content to AI. Files classified as CONFIDENTIAL, CUI,
    HIGHLY_RESTRICTED, or RESTRICTED are blocked from AI processing.
    """
    ap_alias = os.environ.get("S3_AP_ALIAS", "")
    key = event.get("key", "")
    question = event.get("question", "")

    if not ap_alias or not key or not question:
        return {"answer": "", "error": "Missing required parameters (key, question)"}

    # F-2: CONFIDENTIAL guardrail — check classification before AI processing
    allowed, classification = check_classification(key)
    if not allowed:
        return {
            "answer": "",
            "model": MODEL_ID,
            "error": f"AI processing blocked: file classified as {classification}. "
            f"Files with classification {', '.join(sorted(AI_BLOCKED_LEVELS))} "
            f"cannot be sent to AI services.",
            "blocked": True,
            "classification": classification,
        }

    try:
        # Get file content from S3 AP
        obj = s3.get_object(Bucket=ap_alias, Key=key)
        content_length = obj.get("ContentLength", 0)

        if content_length > MAX_FILE_SIZE:
            # Read first 100KB for large files
            body = obj["Body"].read(MAX_FILE_SIZE).decode("utf-8", errors="replace")
            body += f"\n\n[Truncated: file is {content_length} bytes, showing first {MAX_FILE_SIZE} bytes]"
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

        # Call Bedrock (Messages API format for Nova/Claude models)
        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": prompt}],
                }
            ],
            inferenceConfig={
                "maxTokens": 1024,
                "temperature": 0.3,
                "topP": 0.9,
            },
        )

        answer = response["output"]["message"]["content"][0]["text"]

        return {"answer": answer, "model": MODEL_ID, "error": None, "classification": classification}

    except Exception as e:
        print(f"Error: {e}")
        return {"answer": "", "model": MODEL_ID, "error": str(e)}
