import os
import json
import boto3

BEDROCK_KB_ID = os.environ.get("BEDROCK_KB_ID", "")
REGION = os.environ.get("AWS_REGION", "ap-northeast-1")


def handler(event, context):
    """Search files using Bedrock Knowledge Base Retrieve API.

    Performs semantic search over FSx for ONTAP S3 AP content indexed
    in a Bedrock Knowledge Base. Returns matching passages with source
    file references and relevance scores.
    """
    query = event.get("query", "")
    max_results = event.get("maxResults", 5)

    if not BEDROCK_KB_ID:
        return {
            "results": [],
            "query": query,
            "error": "Search not configured (set BEDROCK_KB_ID environment variable)",
        }

    if not query.strip():
        return {"results": [], "query": query, "error": "Empty query"}

    try:
        client = boto3.client("bedrock-agent-runtime", region_name=REGION)

        response = client.retrieve(
            knowledgeBaseId=BEDROCK_KB_ID,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": min(max_results, 25),
                }
            },
        )

        results = []
        for item in response.get("retrievalResults", []):
            content = item.get("content", {}).get("text", "")
            location = item.get("location", {})
            s3_uri = location.get("s3Location", {}).get("uri", "")
            score = item.get("score", 0)

            # Extract file key from S3 URI (s3://ap-alias/path/to/file)
            file_key = ""
            if s3_uri:
                parts = s3_uri.replace("s3://", "").split("/", 1)
                file_key = parts[1] if len(parts) > 1 else ""

            results.append({
                "fileKey": file_key,
                "s3Uri": s3_uri,
                "snippet": content[:500],  # Truncate long passages
                "score": round(score, 4),
            })

        return {
            "results": results,
            "query": query,
            "error": None,
        }

    except Exception as e:
        print(f"Search error: {e}")
        return {
            "results": [],
            "query": query,
            "error": str(e),
        }
