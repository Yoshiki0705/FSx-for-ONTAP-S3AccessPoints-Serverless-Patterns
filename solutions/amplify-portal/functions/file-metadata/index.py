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
        table = dynamodb.Table(METADATA_TABLE)

        # Use batch_get_item for efficiency
        keys = [{"file_key": k} for k in file_keys]

        # DynamoDB BatchGetItem via resource API
        results = []
        for key in keys:
            try:
                resp = table.get_item(Key=key)
                if resp.get("Item"):
                    item = resp["Item"]
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
            except Exception:
                continue

        return {"metadata": results, "error": None}

    except Exception as e:
        print(f"Error fetching metadata: {e}")
        return {"metadata": [], "error": str(e)}
