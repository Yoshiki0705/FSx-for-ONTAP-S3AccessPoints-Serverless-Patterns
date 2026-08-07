import os

import boto3

METADATA_TABLE = os.environ.get("AI_METADATA_TABLE_NAME", "")


def handler(event, context):
    """Batch-fetch AI processing metadata for a list of file keys.

    Returns metadata records from DynamoDB keyed by file path.
    Each record may contain: classification, rekognition_labels,
    comprehend_entities_count, textract_text_length, bedrock_summary,
    processed_at, processing_pattern.

    Used by FileExplorer to display inline badges (e.g., "INTERNAL",
    "5 labels", "12 entities") next to each file in the listing.
    """
    file_keys = event.get("fileKeys", [])

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
        print(f"Error fetching metadata: {e}")
        return {"metadata": [], "error": str(e)}
