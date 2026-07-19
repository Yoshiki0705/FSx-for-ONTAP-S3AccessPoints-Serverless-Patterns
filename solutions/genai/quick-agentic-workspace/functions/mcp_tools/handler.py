"""AgentCore MCP Tools Lambda - FSx for ONTAP S3 AP operations.

Provides list_files, read_file, and search_files tools for AgentCore Gateway.
Enables Quick Suite to browse and read EDA logs in real-time via MCP.

Input format (AgentCore Lambda target):
  - event: Flat dict of inputSchema property values (e.g., {"path": "eda-regression/"})
  - context.client_context.custom['bedrockAgentCoreToolName']: "${target_name}___${tool_name}"

Output format:
  - Plain JSON dict (Gateway wraps it into MCP response format)

Reference:
  - https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-add-target-lambda.html
  - Workshop Module 09: https://catalog.us-east-1.prod.workshops.aws/workshops/9cd82e0b-8348-456b-932a-818b9e5825a1/en-US/09-agentcore
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")

# Delimiter used by AgentCore to prefix tool names with target name
TOOL_NAME_DELIMITER = "___"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entrypoint - routes MCP tool calls from AgentCore Gateway.

    AgentCore passes:
      - event: the tool's input parameters as a flat dict
      - context.client_context.custom: metadata including tool name
    """
    logger.info("Event: %s", json.dumps(event, default=str)[:2000])

    # Extract tool name from context (AgentCore format: targetName___toolName)
    tool_name = _extract_tool_name(context)

    # Fallback: if called directly (testing), check event for tool name
    if not tool_name:
        tool_name = event.pop("toolName", event.pop("name", ""))
        params = event.pop("input", event)
    else:
        params = event  # event IS the params in AgentCore format

    logger.info("Tool: %s, Params: %s", tool_name, json.dumps(params, default=str)[:500])

    handlers = {
        "list_files": _list_files,
        "read_file": _read_file,
        "search_files": _search_files,
    }

    if tool_name not in handlers:
        return {"error": f"Unknown tool: {tool_name}. Available: {list(handlers.keys())}"}

    try:
        return handlers[tool_name](params)
    except Exception as e:
        logger.exception("Tool execution failed: %s", tool_name)
        return {"error": str(e)}


def _extract_tool_name(context: Any) -> str:
    """Extract tool name from AgentCore context metadata."""
    try:
        custom = context.client_context.custom
        full_name = custom.get("bedrockAgentCoreToolName", "")
        if TOOL_NAME_DELIMITER in full_name:
            return full_name.split(TOOL_NAME_DELIMITER, 1)[1]
        return full_name
    except (AttributeError, TypeError):
        return ""


def _list_files(params: dict[str, Any]) -> dict[str, Any]:
    """List files at specified path via S3 AP."""
    prefix = params.get("path", "")
    max_results = min(int(params.get("max_results", 100)), 1000)
    file_extension = params.get("file_extension", "")

    response = s3.list_objects_v2(
        Bucket=AP_ALIAS,
        Prefix=prefix,
        MaxKeys=max_results,
    )

    files = []
    for obj in response.get("Contents", []):
        key = obj["Key"]
        if file_extension and not key.endswith(file_extension):
            continue
        files.append(
            {
                "path": key,
                "size": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
            }
        )

    return {
        "files": files,
        "count": len(files),
        "truncated": response.get("IsTruncated", False),
        "prefix": prefix,
    }


def _read_file(params: dict[str, Any]) -> dict[str, Any]:
    """Read file content via S3 AP."""
    path = params.get("path", "")
    if not path:
        return {"error": "path is required"}

    max_bytes = min(int(params.get("max_bytes", 65536)), 1048576)
    encoding = params.get("encoding", "utf-8")

    response = s3.get_object(
        Bucket=AP_ALIAS,
        Key=path,
        Range=f"bytes=0-{max_bytes - 1}",
    )

    content = response["Body"].read().decode(encoding, errors="replace")
    content_length = response.get("ContentLength", len(content))

    return {
        "path": path,
        "content": content,
        "size": content_length,
        "truncated": content_length > max_bytes,
    }


def _search_files(params: dict[str, Any]) -> dict[str, Any]:
    """Search files matching a pattern."""
    pattern = params.get("pattern", "")
    if not pattern:
        return {"error": "pattern is required"}

    prefix = params.get("path", "")
    file_extension = params.get("file_extension", "")
    max_results = min(int(params.get("max_results", 20)), 100)
    include_preview = params.get("include_content_preview", False)
    if isinstance(include_preview, str):
        include_preview = include_preview.lower() == "true"

    paginator = s3.get_paginator("list_objects_v2")
    matches = []

    for page in paginator.paginate(
        Bucket=AP_ALIAS,
        Prefix=prefix,
        PaginationConfig={"MaxItems": 500},
    ):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if file_extension and not key.endswith(file_extension):
                continue
            if re.search(pattern, key, re.IGNORECASE):
                match = {
                    "path": key,
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                }
                if include_preview:
                    try:
                        resp = s3.get_object(Bucket=AP_ALIAS, Key=key, Range="bytes=0-1023")
                        match["preview"] = resp["Body"].read().decode("utf-8", errors="replace")
                    except Exception:
                        match["preview"] = "(read error)"
                matches.append(match)
                if len(matches) >= max_results:
                    break
        if len(matches) >= max_results:
            break

    return {
        "pattern": pattern,
        "matches": matches,
        "count": len(matches),
    }
