"""Search files — dual mode: keyword (S3 AP pattern match) + semantic (Bedrock KB).

Query format from frontend: "mode:actual_query"
  - "keyword:thermal" → S3 ListObjectsV2 pattern search
  - "semantic:thermal design specifications" → Bedrock KB vector search

Auto-fallback: If mode is 'semantic' but BEDROCK_KB_ID is not configured,
returns an informative error (frontend can suggest switching to keyword mode).

DemoMode: When S3_AP_ALIAS is empty, returns mock results for keyword mode.
"""
from __future__ import annotations

import os
import boto3
from botocore.config import Config

BEDROCK_KB_ID = os.environ.get("BEDROCK_KB_ID", "")
S3_AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")
REGION = os.environ.get("AWS_REGION", "ap-northeast-1")

s3 = boto3.client(
    "s3",
    region_name=REGION,
    endpoint_url=f"https://s3.{REGION}.amazonaws.com",
    config=Config(signature_version="s3v4"),
)


def handler(event, context):
    """Search files with mode routing.

    Query string format: "mode:search_term" or plain "search_term" (defaults to keyword).
    """
    raw_query = event.get("query", "")
    max_results = event.get("maxResults", 10)

    # Parse mode prefix
    mode = "keyword"
    query = raw_query

    if ":" in raw_query:
        prefix_part, _, rest = raw_query.partition(":")
        if prefix_part.lower() in ("keyword", "semantic"):
            mode = prefix_part.lower()
            query = rest
        # else: treat the whole thing as the query (e.g., "file:name.txt")

    if not query.strip():
        return {"results": [], "query": query, "error": "Empty query"}

    if mode == "semantic":
        return _search_semantic(query.strip(), max_results)
    else:
        return _search_keyword(query.strip(), max_results)


# --- Semantic Search (Bedrock Knowledge Base) ---


def _search_semantic(query: str, max_results: int) -> dict:
    """Vector search via Bedrock Knowledge Base Retrieve API."""
    if not BEDROCK_KB_ID:
        return {
            "results": [],
            "query": query,
            "error": "Semantic search not configured. Set BEDROCK_KB_ID in portal-config.ts to enable. Try keyword mode instead.",
        }

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
                "snippet": content[:500],
                "score": round(score, 4),
            })

        return {
            "results": results,
            "query": query,
            "error": None,
        }

    except Exception as e:
        print(f"Semantic search error: {e}")
        return {
            "results": [],
            "query": query,
            "error": str(e),
        }


# --- Keyword Search (S3 AP ListObjectsV2 + filter) ---


def _search_keyword(query: str, max_results: int) -> dict:
    """Pattern match search via S3 AP ListObjectsV2."""
    if not S3_AP_ALIAS:
        return _mock_keyword_search(query, max_results)

    try:
        pattern = query.lower()
        matches = []
        paginator = s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(
            Bucket=S3_AP_ALIAS,
            Prefix="",
            PaginationConfig={"MaxItems": 500},
        )

        for page in pages:
            for obj in page.get("Contents", []):
                key = obj.get("Key", "")
                if pattern in key.lower():
                    matches.append({
                        "fileKey": key,
                        "snippet": "",
                        "score": 0,
                        "s3Uri": f"s3://{S3_AP_ALIAS}/{key}",
                    })
                    if len(matches) >= max_results:
                        break
            if len(matches) >= max_results:
                break

        return {
            "results": matches,
            "query": query,
            "error": None,
        }

    except Exception as e:
        print(f"Keyword search error: {e}")
        return {
            "results": [],
            "query": query,
            "error": str(e),
        }


# --- DemoMode Mock ---


def _mock_keyword_search(query: str, max_results: int) -> dict:
    """Mock keyword search for DemoMode."""
    all_files = [
        "engineering/thermal-spec-v3.pdf",
        "engineering/requirements.md",
        "engineering/cae-results/sim-001.vtu",
        "engineering/designs/chip-layout-v2.gds",
        "simulation/JOB_00001.log",
        "simulation/JOB_00002.log",
        "simulation/JOB_00003.log",
        "simulation/JOB_00004.log",
        "simulation/JOB_00005.log",
        "contracts/nda-2026.pdf",
        "contracts/msa-vendor-a.pdf",
        "contracts/sow-project-x.docx",
        "reports/quarterly-q2-2026.xlsx",
        "reports/monthly-june-2026.pdf",
        "reports/annual-2025-review.pptx",
    ]

    pattern = query.lower()
    matches = [
        {"fileKey": f, "snippet": "", "score": 0, "s3Uri": ""}
        for f in all_files
        if pattern in f.lower()
    ][:max_results]

    return {
        "results": matches,
        "query": query,
        "error": None,
    }
