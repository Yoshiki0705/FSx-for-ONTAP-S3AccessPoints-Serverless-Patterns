"""Answer a question about an object's contents, via Bedrock.

This endpoint sends file content to a model, so an unchecked object key is a read of
the whole file by another route. It had a data-classification guardrail and no path
boundary at all: the classification check decides whether a file *may* be sent to AI,
never whether this caller may see it.

The boundary runs before the classification check on purpose. Refusing a file because
it is CONFIDENTIAL tells the caller the file exists and how it is labelled, which is
more than a caller outside its boundary should learn.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3

from shared.exceptions import S3ApHelperError
from shared.portal_external_policy import ai_denial_reason
from shared.portal_path_scope import scope_for_caller
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger()
logger.setLevel(logging.INFO)

region = os.environ.get("AWS_REGION", "ap-northeast-1")
bedrock = boto3.client("bedrock-runtime", region_name=region)

DEFAULT_AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")
GROUP_AP_MAPPING = json.loads(os.environ.get("GROUP_AP_MAPPING", "{}"))
GROUP_PATH_PREFIXES = json.loads(os.environ.get("GROUP_PATH_PREFIXES", "{}"))
# Whether callers from outside the organisation may use this endpoint. Off unless
# set, because the call sends file content to a model and is billed per token.
EXTERNAL_AI_ENABLED = os.environ.get("EXTERNAL_AI_ENABLED", "") == "true"

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
        logger.warning("Classification lookup failed for %s", file_key, exc_info=True)
        return True, "UNKNOWN"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Ask a question about a file on FSx for ONTAP S3 AP using Bedrock.

    Includes CONFIDENTIAL guardrail: checks data classification before
    sending file content to AI. Files classified as CONFIDENTIAL, CUI,
    HIGHLY_RESTRICTED, or RESTRICTED are blocked from AI processing.

    Args:
        event: `key`, `question`, plus `groups` injected by the resolver from the
            Cognito identity.
        context: Lambda context, unused.

    Returns:
        `answer` and `model`, or `error` naming why nothing was answered.
    """
    key = event.get("key", "")
    question = event.get("question", "")
    groups = event.get("groups") if isinstance(event.get("groups"), list) else []

    if not question:
        return {"answer": "", "error": "Missing required parameters (key, question)"}

    # Ahead of the boundary as well as the classification check. The answer does not
    # depend on the key, so refusing here reveals neither the file nor its label.
    denied = ai_denial_reason(groups, ai_enabled=EXTERNAL_AI_ENABLED)
    if denied:
        logger.info("AI endpoint refused for an external caller: %s", denied)
        return {"answer": "", "error": denied}

    # Ahead of the classification check, so a caller outside the boundary learns
    # nothing about the file -- neither that it exists nor how it is labelled.
    ap_alias, refused = scope_for_caller(
        groups,
        group_ap_mapping=GROUP_AP_MAPPING,
        group_path_prefixes=GROUP_PATH_PREFIXES,
        default_alias=DEFAULT_AP_ALIAS,
        key=key,
    )
    if refused:
        return {"answer": "", **refused}

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
        helper = S3ApHelper(ap_alias)
        content_length = helper.head_object(key).get("ContentLength", 0)
        body = helper.get_object_bytes(key, max_bytes=MAX_FILE_SIZE).decode("utf-8", errors="replace")
        if content_length > MAX_FILE_SIZE:
            body += f"\n\n[Truncated: file is {content_length} bytes, showing first {MAX_FILE_SIZE} bytes]"

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

    except S3ApHelperError as e:
        logger.exception("Read failed for key %s on %s", key, ap_alias)
        return {"answer": "", "model": MODEL_ID, "error": str(e)}
    except Exception as e:
        logger.exception("Bedrock call failed for key %s", key)
        return {"answer": "", "model": MODEL_ID, "error": str(e)}
