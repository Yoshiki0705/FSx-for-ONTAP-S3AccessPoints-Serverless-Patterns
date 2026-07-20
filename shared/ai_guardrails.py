"""AI Processing Guardrails — Data Classification Gate

Prevents AI/ML services from processing files classified as CONFIDENTIAL
or above. This module is imported by AI-facing Lambda functions (Bedrock,
Rekognition, Comprehend, Textract) to enforce data classification policies
before sending file content to AI services.

Usage:
    from shared.ai_guardrails import check_ai_allowed, AiGuardrailDenied

    # Check before calling AI service
    try:
        check_ai_allowed(file_key, classification_table_name)
    except AiGuardrailDenied as e:
        return {"error": str(e), "blocked": True, "classification": e.classification}

    # Proceed with AI processing...

Architecture:
    File classification labels are stored in DynamoDB (partition key: file_key).
    Labels can be set by:
    - Initial ingestion pipeline (auto-classification via Comprehend)
    - Manual tagging via portal UI
    - Organization policy (folder-based rules)

Environment variables:
    CLASSIFICATION_TABLE_NAME: DynamoDB table name for file classifications
    AI_BLOCKED_LEVELS: Comma-separated list of blocked classification levels
                       (default: "CONFIDENTIAL,CUI,HIGHLY_RESTRICTED,RESTRICTED")
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Classification levels that block AI processing (configurable via env)
DEFAULT_BLOCKED_LEVELS = "CONFIDENTIAL,CUI,HIGHLY_RESTRICTED,RESTRICTED"


class AiGuardrailDenied(Exception):
    """Raised when AI processing is blocked by data classification policy."""

    def __init__(self, file_key: str, classification: str, reason: str):
        self.file_key = file_key
        self.classification = classification
        self.reason = reason
        super().__init__(f"AI processing blocked for '{file_key}': classification={classification} — {reason}")


def get_blocked_levels() -> set[str]:
    """Get the set of classification levels that block AI processing."""
    levels_str = os.environ.get("AI_BLOCKED_LEVELS", DEFAULT_BLOCKED_LEVELS)
    return {level.strip().upper() for level in levels_str.split(",") if level.strip()}


def get_file_classification(
    file_key: str,
    table_name: Optional[str] = None,
) -> Optional[str]:
    """Look up a file's classification from DynamoDB.

    Args:
        file_key: S3 object key (file path)
        table_name: DynamoDB table name (default: env CLASSIFICATION_TABLE_NAME)

    Returns:
        Classification level string (e.g., "INTERNAL", "CONFIDENTIAL") or None if not found.
        Returns None for unclassified files (treated as allowed by default).
    """
    table_name = table_name or os.environ.get("CLASSIFICATION_TABLE_NAME", "")
    if not table_name:
        # No classification table configured — allow by default
        return None

    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(table_name)
        response = table.get_item(Key={"file_key": file_key})
        item = response.get("Item")
        if item:
            return item.get("classification", "").upper()

        # Check folder-level classification (walk up the path)
        parts = file_key.rsplit("/", 1)
        while len(parts) == 2 and parts[0]:
            folder_key = parts[0] + "/"
            response = table.get_item(Key={"file_key": folder_key})
            item = response.get("Item")
            if item:
                return item.get("classification", "").upper()
            parts = parts[0].rsplit("/", 1)

        return None
    except ClientError as e:
        logger.warning(f"Failed to lookup classification for {file_key}: {e}")
        return None


def check_ai_allowed(
    file_key: str,
    table_name: Optional[str] = None,
) -> str:
    """Check if AI processing is allowed for a file.

    Args:
        file_key: S3 object key
        table_name: DynamoDB table name (optional, uses env var)

    Returns:
        The file's classification level (or "UNCLASSIFIED" if not found)

    Raises:
        AiGuardrailDenied: If the file's classification blocks AI processing
    """
    classification = get_file_classification(file_key, table_name)

    if classification is None:
        # No classification found — default: allow
        return "UNCLASSIFIED"

    blocked_levels = get_blocked_levels()

    if classification in blocked_levels:
        raise AiGuardrailDenied(
            file_key=file_key,
            classification=classification,
            reason=(
                f"Files classified as {classification} cannot be processed by AI services. "
                f"Blocked levels: {', '.join(sorted(blocked_levels))}. "
                "Contact your administrator to reclassify or use a different processing method."
            ),
        )

    return classification


def classify_file(
    file_key: str,
    classification: str,
    table_name: Optional[str] = None,
    classified_by: str = "system",
) -> None:
    """Set or update a file's classification in DynamoDB.

    Args:
        file_key: S3 object key
        classification: Classification level (e.g., "INTERNAL", "CONFIDENTIAL")
        table_name: DynamoDB table name (optional)
        classified_by: Who/what set this classification
    """
    table_name = table_name or os.environ.get("CLASSIFICATION_TABLE_NAME", "")
    if not table_name:
        logger.warning("CLASSIFICATION_TABLE_NAME not set — cannot store classification")
        return

    from datetime import datetime, timezone

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)
    table.put_item(
        Item={
            "file_key": file_key,
            "classification": classification.upper(),
            "classified_by": classified_by,
            "classified_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    logger.info(f"Classified {file_key} as {classification} by {classified_by}")
