"""Search files — dual mode: keyword (S3 AP pattern match) + semantic (Bedrock KB).

Query format from frontend: "mode:actual_query"
  - "keyword:thermal" → S3 ListObjectsV2 pattern search
  - "semantic:thermal design specifications" → Bedrock KB vector search

Auto-fallback: If mode is 'semantic' but BEDROCK_KB_ID is not configured,
returns an informative error (frontend can suggest switching to keyword mode).

DemoMode: When S3_AP_ALIAS is empty, returns mock results for keyword mode.
"""

from __future__ import annotations

import json
import logging
import os

import boto3
from botocore.config import Config

from shared.portal_external_policy import ai_denial_reason
from shared.portal_path_scope import allowed_prefixes, key_is_visible, resolve_ap_alias

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BEDROCK_KB_ID = os.environ.get("BEDROCK_KB_ID", "")
DEFAULT_AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")
GROUP_AP_MAPPING = json.loads(os.environ.get("GROUP_AP_MAPPING", "{}"))
GROUP_PATH_PREFIXES = json.loads(os.environ.get("GROUP_PATH_PREFIXES", "{}"))
# Whether callers from outside the organisation may use the semantic mode, which
# sends the query to a knowledge base. The keyword mode stays available to them:
# it lists through their own access point and reaches no model.
EXTERNAL_AI_ENABLED = os.environ.get("EXTERNAL_AI_ENABLED", "") == "true"
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

    Search results are object keys, so an unfiltered search is a directory listing by
    another name -- and it bypassed the filter the listing endpoint applies. Both modes
    are now confined: the keyword mode lists through the caller's own access point, and
    every result from either mode is dropped unless the caller may see the key. The
    semantic mode matters as much as the keyword one, because a knowledge base indexes
    whatever it was pointed at, without regard for the portal's groups.
    """
    raw_query = event.get("query", "")
    max_results = event.get("maxResults", 10)
    groups = event.get("groups") if isinstance(event.get("groups"), list) else []
    ap_alias = resolve_ap_alias(groups, GROUP_AP_MAPPING, DEFAULT_AP_ALIAS)
    allowed = allowed_prefixes(groups, GROUP_PATH_PREFIXES)

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
        denied = ai_denial_reason(groups, ai_enabled=EXTERNAL_AI_ENABLED)
        if denied:
            # Only this mode. Refusing the keyword mode too would take away the search
            # that does not involve a model, and the caller can already list the same
            # keys through the file browser.
            logger.info("Semantic search refused for an external caller: %s", denied)
            return {"results": [], "query": query, "error": denied}
        return _search_semantic(query.strip(), max_results, allowed)
    return _search_keyword(query.strip(), max_results, ap_alias, allowed)


# --- Semantic Search (Bedrock Knowledge Base) ---


def _search_semantic(query: str, max_results: int, allowed: list[str]) -> dict:
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

            results.append(
                {
                    "fileKey": file_key,
                    "s3Uri": s3_uri,
                    "snippet": content[:500],
                    "score": round(score, 4),
                }
            )

        return {
            "results": results,
            "query": query,
            "error": None,
        }

    except Exception as e:
        logger.exception("Semantic search failed: %s", e)
        return {
            "results": [],
            "query": query,
            "error": str(e),
        }


# --- Keyword Search (S3 AP ListObjectsV2 + filter) ---


def _search_keyword(query: str, max_results: int, ap_alias: str, allowed: list[str]) -> dict:
    """Pattern match search via S3 AP ListObjectsV2."""
    if not ap_alias:
        return _mock_keyword_search(query, max_results)

    try:
        pattern = query.lower()
        matches = []
        paginator = s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(
            Bucket=ap_alias,
            Prefix="",
            PaginationConfig={"MaxItems": 500},
        )

        for page in pages:
            for obj in page.get("Contents", []):
                key = obj.get("Key", "")
                if pattern in key.lower() and key_is_visible(key, allowed):
                    matches.append(
                        {
                            "fileKey": key,
                            "snippet": "",
                            "score": 0,
                            "s3Uri": f"s3://{ap_alias}/{key}",
                        }
                    )
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
        logger.exception("Keyword search failed: %s", e)
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
    matches = [{"fileKey": f, "snippet": "", "score": 0, "s3Uri": ""} for f in all_files if pattern in f.lower()][
        :max_results
    ]

    return {
        "results": matches,
        "query": query,
        "error": None,
    }
