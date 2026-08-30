"""AI-derived metadata for a batch of object keys.

The records here are summaries of file contents -- a classification, a Bedrock
summary, entity and label counts -- so answering for a key is close to answering
about the file. The keys arrive from the client, and nothing checked them, which made
another team's summaries reachable by naming their paths even though the listing that
produced those paths is filtered.

Keys outside the caller's boundary are dropped rather than refused. The explorer asks
for a whole page at once, so refusing the batch because one key does not belong would
turn a boundary into a broken folder view; a dropped key simply carries no badge.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3

from shared.portal_path_scope import allowed_prefixes, key_is_visible

logger = logging.getLogger()
logger.setLevel(logging.INFO)

METADATA_TABLE = os.environ.get("AI_METADATA_TABLE_NAME", "")
GROUP_PATH_PREFIXES = json.loads(os.environ.get("GROUP_PATH_PREFIXES", "{}"))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Batch-fetch AI processing metadata for a list of file keys.

    Args:
        event: `fileKeys`, plus `groups` injected by the resolver from the Cognito
            identity.
        context: Lambda context, unused.

    Returns:
        `metadata`, one record per key the caller may see, or `error`.
    """
    file_keys = event.get("fileKeys", [])
    groups = event.get("groups") if isinstance(event.get("groups"), list) else []

    allowed = allowed_prefixes(groups, GROUP_PATH_PREFIXES)
    file_keys = [k for k in file_keys if key_is_visible(k, allowed)]

    if not METADATA_TABLE:
        return {
            "metadata": [],
            "error": "AI metadata table not configured (set AI_METADATA_TABLE_NAME)",
        }

    if not file_keys:
        return {"metadata": [], "error": None}

    # Limit to 100 keys per batch (DynamoDB BatchGetItem limit)
    file_keys = file_keys[:100]

    try:
        dynamodb = boto3.resource("dynamodb")

        # One BatchGetItem rather than a get_item per key. The previous loop said
        # "use batch_get_item for efficiency" above a sequential read of up to 100
        # items, which is 100 round trips. That was survivable while nothing called
        # this; it now runs on every folder the explorer opens.
        results = []
        unprocessed = {METADATA_TABLE: {"Keys": [{"file_key": k} for k in dict.fromkeys(file_keys)]}}
        # BatchGetItem may return some keys unread when it hits its response size
        # limit; those come back as UnprocessedKeys rather than as an error.
        while unprocessed:
            response = dynamodb.batch_get_item(RequestItems=unprocessed)
            for item in response.get("Responses", {}).get(METADATA_TABLE, []):
                results.append(
                    {
                        "fileKey": item.get("file_key", ""),
                        "classification": item.get("classification"),
                        "rekognitionLabels": item.get("rekognition_labels"),
                        "comprehendEntities": item.get("comprehend_entities_count"),
                        "textractLength": item.get("textract_text_length"),
                        "bedrockSummary": item.get("bedrock_summary"),
                        "processedAt": item.get("processed_at"),
                        "pattern": item.get("processing_pattern"),
                    }
                )
            unprocessed = response.get("UnprocessedKeys") or {}

        return {"metadata": results, "error": None}

    except Exception as e:
        logger.exception("Metadata fetch failed for %d key(s)", len(file_keys))
        return {"metadata": [], "error": str(e)}
