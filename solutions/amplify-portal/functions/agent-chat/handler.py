"""Agent Chat — Multi-tool AI agent using Bedrock Converse with tool_use.

Architecture:
  AppSync → this Lambda → Bedrock Converse (tool_use loop)
  Tools available:
    - list_files: Browse directory contents via S3 AP
    - read_file: Read file content via S3 AP (with PHI guardrail)
    - search_files: Pattern-match search across S3 AP
    - analyze_content: Summarize/analyze file content with AI

The agent loop:
  1. Send user message + tool definitions to Bedrock
  2. If Bedrock requests tool_use → execute tool → append result → repeat
  3. When Bedrock returns final text → return to frontend with tool trace

Supports DemoMode: when S3_AP_ALIAS is empty, tools return mock data.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from decimal import Decimal
from typing import Any

import boto3
from botocore.config import Config

from shared.portal_external_policy import ai_denial_reason
from shared.portal_path_scope import allowed_prefixes as _shared_allowed_prefixes
from shared.portal_regulated_path import is_regulated_path

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Configuration ---
REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
S3_AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")
MODEL_ID = os.environ.get("AGENT_MODEL_ID", "amazon.nova-lite-v1:0")
MAX_TOOL_ITERATIONS = int(os.environ.get("MAX_TOOL_ITERATIONS", "8"))
MAX_FILE_READ_BYTES = 50 * 1024  # 50KB per file read
GUARDRAIL_ID = os.environ.get("BEDROCK_GUARDRAIL_ID", "")
GUARDRAIL_VERSION = os.environ.get("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
BEDROCK_KB_ID = os.environ.get("BEDROCK_KB_ID", "")

CHAT_HISTORY_TABLE = os.environ.get("CHAT_HISTORY_TABLE", "")
AGENT_DIRECTORY_TABLE = os.environ.get("AGENT_DIRECTORY_TABLE", "")
AGENT_TEAMS_TABLE = os.environ.get("AGENT_TEAMS_TABLE", "")
# Smart Routing: JSON mapping of Cognito group → allowed path prefixes
# Example: {"engineering": ["engineering/", "shared/"], "finance": ["finance/", "shared/"]}
GROUP_PATH_PREFIXES = json.loads(os.environ.get("GROUP_PATH_PREFIXES", "{}"))
# Whether callers from outside the organisation may run the agent. Off unless set:
# the conversation reaches a model, and the agent's tools read file content.
EXTERNAL_AI_ENABLED = os.environ.get("EXTERNAL_AI_ENABLED", "") == "true"

# Distinguishes "the caller did not send this field" from "the caller sent an
# empty value". `None` cannot: clearing a description is a legitimate edit.
_MISSING = object()

s3 = boto3.client(
    "s3",
    region_name=REGION,
    endpoint_url=f"https://s3.{REGION}.amazonaws.com",
    config=Config(signature_version="s3v4"),
)
bedrock = boto3.client("bedrock-runtime", region_name=REGION)
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION) if BEDROCK_KB_ID else None

# --- PHI Guardrail ---
# The predicate used to be a second copy of the browser's, written separately and able to
# drift from it. It now comes from `shared.portal_regulated_path`, which the other AI
# endpoints import as well, so the boundary has one definition per language.
is_phi_path = is_regulated_path


# --- Tool Definitions (Bedrock Converse format) ---
TOOL_CONFIG = {
    "tools": [
        {
            "toolSpec": {
                "name": "list_files",
                "description": (
                    "List files and folders in a directory on the NAS volume. "
                    "Returns file names, sizes, and last modified dates. "
                    "Use prefix='' for root, or prefix='folder/' for subdirectories."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "prefix": {
                                "type": "string",
                                "description": "Directory path prefix (e.g., 'engineering/' or '')",
                            },
                            "max_keys": {
                                "type": "integer",
                                "description": "Maximum number of items to return (default: 20)",
                            },
                        },
                        "required": ["prefix"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "read_file",
                "description": (
                    "Read the content of a specific file from the NAS volume. "
                    "Returns the text content (up to 50KB). "
                    "Cannot read files in PHI-protected paths (/dicom/, /phi/, /pii/)."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string",
                                "description": "Full file path/key (e.g., 'engineering/spec-v3.pdf')",
                            },
                        },
                        "required": ["key"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "search_files",
                "description": (
                    "Search for files matching a pattern in file names. "
                    "Returns matching file paths with sizes. "
                    "Searches across the entire volume."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "Search pattern to match in file names (case-insensitive)",
                            },
                            "prefix": {
                                "type": "string",
                                "description": "Optional: limit search to a subdirectory",
                            },
                        },
                        "required": ["pattern"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "get_volume_summary",
                "description": (
                    "Get a high-level summary of the NAS volume: "
                    "total file count, top-level folders, and storage usage."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {},
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "request_action_approval",
                "description": (
                    "Request human approval for a dangerous or irreversible action. "
                    "Use this BEFORE executing any destructive operation like deleting files, "
                    "locking snapshots, blocking users, or modifying retention periods. "
                    "The user must explicitly approve before the action can proceed."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "action_type": {
                                "type": "string",
                                "description": "Type of action (e.g., 'delete', 'lock', 'block_user', 'enable_snaplock')",
                            },
                            "target": {
                                "type": "string",
                                "description": "What the action targets (e.g., volume name, file path, user)",
                            },
                            "reason": {
                                "type": "string",
                                "description": "Why this action is being proposed",
                            },
                            "is_reversible": {
                                "type": "boolean",
                                "description": "Whether this action can be undone (false for SnapLock, true for block/unblock)",
                            },
                        },
                        "required": ["action_type", "target", "reason"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "kb_search",
                "description": (
                    "Semantic search over file CONTENTS using Bedrock Knowledge Base (RAG). "
                    "Unlike search_files (which matches file names), kb_search finds relevant "
                    "passages INSIDE files based on meaning. Use when the user asks about "
                    "specific content, topics, or information within documents. "
                    "Returns relevant text snippets with source file paths and relevance scores."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Natural language query to search file contents (e.g., 'thermal design temperature limits')",
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of results to return (default: 5, max: 10)",
                            },
                        },
                        "required": ["query"],
                    }
                },
            }
        },
    ]
}

# --- Agent specialization labels (for multi-agent trace visualization) ---
TOOL_AGENT_MAP = {
    "list_files": "file-explorer",
    "read_file": "file-explorer",
    "search_files": "file-explorer",
    "get_volume_summary": "file-explorer",
    "kb_search": "knowledge-analyst",
    "request_action_approval": "safety-controller",
}

# --- Tool Implementations ---


def _tool_list_files(params: dict[str, Any]) -> str:
    """List files via S3 AP ListObjectsV2."""
    prefix = params.get("prefix", "")
    max_keys = min(params.get("max_keys", 20), 50)

    if not S3_AP_ALIAS:
        return _mock_list_files(prefix, max_keys)

    try:
        resp = s3.list_objects_v2(
            Bucket=S3_AP_ALIAS,
            Prefix=prefix,
            Delimiter="/",
            MaxKeys=max_keys,
        )
        folders = [cp["Prefix"] for cp in resp.get("CommonPrefixes", [])]
        files = [
            {
                "key": obj["Key"],
                "size": obj["Size"],
                "modified": obj["LastModified"].isoformat() if obj.get("LastModified") else None,
            }
            for obj in resp.get("Contents", [])
            if not obj["Key"].endswith("/")
        ]
        return json.dumps(
            {
                "folders": folders,
                "files": files,
                "total": len(folders) + len(files),
                "truncated": resp.get("IsTruncated", False),
            }
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_read_file(params: dict[str, Any]) -> str:
    """Read file content via S3 AP GetObject."""
    key = params.get("key", "")
    if not key:
        return json.dumps({"error": "File key is required"})

    # PHI guardrail
    if is_phi_path(key):
        return json.dumps(
            {
                "error": f"PHI guardrail: cannot read files in protected path. "
                f"File '{key}' is in a PHI/PII protected directory.",
                "blocked": True,
            }
        )

    if not S3_AP_ALIAS:
        return _mock_read_file(key)

    try:
        obj = s3.get_object(Bucket=S3_AP_ALIAS, Key=key)
        content_length = obj.get("ContentLength", 0)
        body = obj["Body"].read(MAX_FILE_READ_BYTES).decode("utf-8", errors="replace")
        if content_length > MAX_FILE_READ_BYTES:
            body += f"\n\n[Truncated: file is {content_length} bytes, showing first {MAX_FILE_READ_BYTES} bytes]"
        return json.dumps({"content": body, "size": content_length, "key": key})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_search_files(params: dict[str, Any]) -> str:
    """Search files by name pattern via S3 AP ListObjectsV2 + filter."""
    pattern = params.get("pattern", "").lower()
    prefix = params.get("prefix", "")

    if not pattern:
        return json.dumps({"error": "Search pattern is required"})

    if not S3_AP_ALIAS:
        return _mock_search_files(pattern, prefix)

    try:
        matches = []
        paginator = s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(
            Bucket=S3_AP_ALIAS,
            Prefix=prefix,
            PaginationConfig={"MaxItems": 200},
        )
        for page in pages:
            for obj in page.get("Contents", []):
                if pattern in obj["Key"].lower():
                    matches.append(
                        {
                            "key": obj["Key"],
                            "size": obj["Size"],
                            "modified": obj["LastModified"].isoformat() if obj.get("LastModified") else None,
                        }
                    )
                    if len(matches) >= 20:
                        break
            if len(matches) >= 20:
                break

        return json.dumps({"matches": matches, "count": len(matches), "pattern": pattern})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_get_volume_summary(params: dict[str, Any]) -> str:
    """Get volume summary: top-level folders and file count."""
    if not S3_AP_ALIAS:
        return _mock_volume_summary()

    try:
        resp = s3.list_objects_v2(
            Bucket=S3_AP_ALIAS,
            Prefix="",
            Delimiter="/",
            MaxKeys=100,
        )
        folders = [cp["Prefix"] for cp in resp.get("CommonPrefixes", [])]
        root_files = len(resp.get("Contents", []))
        return json.dumps(
            {
                "top_level_folders": folders,
                "root_file_count": root_files,
                "folder_count": len(folders),
            }
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_kb_search(params: dict[str, Any], user_groups: list[str] | None = None) -> str:
    """Semantic search via Bedrock Knowledge Base (RAG retrieval).

    Searches file CONTENT (not just file names) using vector similarity.
    Requires BEDROCK_KB_ID to be configured.

    Smart Routing: When GROUP_PATH_PREFIXES is configured and user belongs to
    a group with path restrictions, results are filtered to only include files
    within the user's allowed paths.
    """
    query = params.get("query", "")
    max_results = min(params.get("max_results", 5), 10)

    if not query:
        return json.dumps({"error": "Query is required for KB search"})

    if not BEDROCK_KB_ID or not bedrock_agent_runtime:
        return json.dumps(
            {
                "error": "Knowledge Base not configured. Set BEDROCK_KB_ID to enable semantic search over file contents.",
                "results": [],
            }
        )

    try:
        retrieve_params: dict[str, Any] = {
            "knowledgeBaseId": BEDROCK_KB_ID,
            "retrievalQuery": {"text": query},
            "retrievalConfiguration": {
                "vectorSearchConfiguration": {
                    "numberOfResults": max_results,
                }
            },
        }

        # Smart Routing: Build filter from user's group path prefixes
        allowed_prefixes = _get_allowed_prefixes(user_groups)
        if allowed_prefixes:
            # Use Bedrock KB filter: startsWith on file URI
            # Note: filter syntax depends on KB metadata configuration
            # Using OR filter across allowed prefixes
            filter_conditions = []
            for prefix in allowed_prefixes:
                filter_conditions.append({"startsWith": {"key": "x-amz-bedrock-kb-source-uri", "value": prefix}})
            if len(filter_conditions) == 1:
                retrieve_params["retrievalConfiguration"]["vectorSearchConfiguration"]["filter"] = filter_conditions[0]
            elif len(filter_conditions) > 1:
                retrieve_params["retrievalConfiguration"]["vectorSearchConfiguration"]["filter"] = {
                    "orAll": filter_conditions
                }

        response = bedrock_agent_runtime.retrieve(**retrieve_params)

        results = []
        for item in response.get("retrievalResults", []):
            content = item.get("content", {}).get("text", "")
            location = item.get("location", {})
            s3_uri = location.get("s3Location", {}).get("uri", "")
            score = item.get("score", 0)

            # Extract file key from S3 URI
            file_key = ""
            if s3_uri:
                parts = s3_uri.replace("s3://", "").split("/", 1)
                file_key = parts[1] if len(parts) > 1 else ""

            # Post-filter: if smart routing is active, verify file matches allowed paths
            if allowed_prefixes and file_key:
                if not any(file_key.startswith(p) for p in allowed_prefixes):
                    continue

            results.append(
                {
                    "fileKey": file_key,
                    "snippet": content[:300],
                    "score": round(score, 4),
                }
            )

        return json.dumps(
            {"results": results, "count": len(results), "query": query, "smartRouting": bool(allowed_prefixes)}
        )

    except Exception as e:
        logger.error(f"KB search error: {e}")
        return json.dumps({"error": str(e), "results": []})


def _get_allowed_prefixes(user_groups: list[str] | None) -> list[str]:
    """Get allowed file path prefixes based on user's Cognito groups.

    Returns empty list if smart routing is disabled (no restrictions).

    Binds this function's environment to the shared boundary. This was the second of
    three copies; the rule now has one definition in `shared.portal_path_scope`. The
    two copies agreed, but by luck rather than by construction -- this one returned
    `list(set(...))` after an extra early return that no caller could distinguish
    from the other's `sorted(set(...))`. The order is now defined.
    """
    return _shared_allowed_prefixes(user_groups, GROUP_PATH_PREFIXES)


# --- DemoMode Mock Data ---


def _mock_list_files(prefix: str, max_keys: int) -> str:
    """Mock response for DemoMode."""
    mock_data = {
        "": {"folders": ["engineering/", "contracts/", "simulation/", "reports/"], "files": []},
        "engineering/": {
            "folders": ["engineering/cae-results/", "engineering/designs/"],
            "files": [
                {"key": "engineering/thermal-spec-v3.pdf", "size": 245000, "modified": "2026-07-20T10:00:00Z"},
                {"key": "engineering/requirements.md", "size": 12000, "modified": "2026-07-18T14:30:00Z"},
            ],
        },
        "simulation/": {
            "folders": [],
            "files": [
                {"key": "simulation/JOB_00001.log", "size": 8500, "modified": "2026-07-25T09:15:00Z"},
                {"key": "simulation/JOB_00002.log", "size": 12300, "modified": "2026-07-25T09:30:00Z"},
                {"key": "simulation/JOB_00003.log", "size": 9800, "modified": "2026-07-25T10:00:00Z"},
                {"key": "simulation/JOB_00004.log", "size": 15600, "modified": "2026-07-25T10:15:00Z"},
                {"key": "simulation/JOB_00005.log", "size": 22100, "modified": "2026-07-25T10:30:00Z"},
            ],
        },
    }
    data = mock_data.get(prefix, {"folders": [], "files": []})
    return json.dumps({**data, "total": len(data["folders"]) + len(data["files"]), "truncated": False})


def _mock_read_file(key: str) -> str:
    """Mock file read for DemoMode."""
    mock_contents = {
        "engineering/thermal-spec-v3.pdf": (
            "Thermal Design Specification v3.0\n"
            "Maximum operating temperature: 85°C\n"
            "Thermal throttling threshold: 75°C\n"
            "Heat dissipation requirement: 45W TDP\n"
            "Cooling solution: Active (fan-based)\n"
            "Change from v2: Reduced max temp from 90°C to 85°C based on reliability testing."
        ),
        "simulation/JOB_00005.log": (
            "=== Simulation Job JOB_00005 ===\n"
            "Start: 2026-07-25 10:30:00 UTC\n"
            "Status: FAIL\n"
            "UVM_FATAL: Timing violation detected at 2.3ns\n"
            "Expected: setup_time >= 1.5ns\n"
            "Actual: setup_time = 1.2ns (violation by 0.3ns)\n"
            "Module: chip_top.cpu_core.alu_unit\n"
            "Recommendation: Increase clock period or optimize critical path."
        ),
        "engineering/requirements.md": (
            "# Product Requirements\n"
            "## Performance\n"
            "- Throughput: >= 10 Gbps sustained\n"
            "- Latency: p99 < 2ms\n"
            "## Reliability\n"
            "- MTBF: > 100,000 hours\n"
            "- Operating temperature range: -20°C to 85°C\n"
        ),
    }
    content = mock_contents.get(key, f"[DemoMode] File content for: {key}\nThis is simulated content.")
    return json.dumps({"content": content, "size": len(content), "key": key})


def _mock_search_files(pattern: str, prefix: str) -> str:
    """Mock search for DemoMode."""
    all_files = [
        {"key": "simulation/JOB_00001.log", "size": 8500},
        {"key": "simulation/JOB_00002.log", "size": 12300},
        {"key": "simulation/JOB_00003.log", "size": 9800},
        {"key": "simulation/JOB_00004.log", "size": 15600},
        {"key": "simulation/JOB_00005.log", "size": 22100},
        {"key": "engineering/thermal-spec-v3.pdf", "size": 245000},
        {"key": "engineering/requirements.md", "size": 12000},
        {"key": "contracts/nda-2026.pdf", "size": 89000},
        {"key": "reports/quarterly-q2-2026.xlsx", "size": 156000},
    ]
    matches = [f for f in all_files if pattern in f["key"].lower()]
    if prefix:
        matches = [f for f in matches if f["key"].startswith(prefix)]
    return json.dumps({"matches": matches, "count": len(matches), "pattern": pattern})


def _mock_volume_summary() -> str:
    """Mock volume summary for DemoMode."""
    return json.dumps(
        {
            "top_level_folders": ["engineering/", "contracts/", "simulation/", "reports/"],
            "root_file_count": 2,
            "folder_count": 4,
        }
    )


# --- Tool Execution Router ---

# Per-request context (set by run_agent_loop, read by tool handlers)
_request_context: dict[str, Any] = {"user_groups": []}

TOOL_HANDLERS = {
    "list_files": _tool_list_files,
    "read_file": _tool_read_file,
    "search_files": _tool_search_files,
    "get_volume_summary": _tool_get_volume_summary,
    "kb_search": _tool_kb_search,
    "request_action_approval": lambda params: json.dumps(
        {
            "approval_required": True,
            "action_type": params.get("action_type", "unknown"),
            "target": params.get("target", ""),
            "reason": params.get("reason", ""),
            "is_reversible": params.get("is_reversible", True),
        }
    ),
}


def execute_tool(name: str, tool_input: dict[str, Any]) -> tuple[str, str]:
    """Execute a tool by name, return (result_json, agent_label)."""
    handler_fn = TOOL_HANDLERS.get(name)
    agent_label = TOOL_AGENT_MAP.get(name, "general")
    if not handler_fn:
        return json.dumps({"error": f"Unknown tool: {name}"}), agent_label
    try:
        # kb_search gets user_groups for smart routing
        if name == "kb_search":
            return handler_fn(tool_input, user_groups=_request_context.get("user_groups")), agent_label
        return handler_fn(tool_input), agent_label
    except Exception as e:
        logger.error(f"Tool execution error ({name}): {e}")
        return json.dumps({"error": f"Tool execution failed: {e}"}), agent_label


# --- Agent Loop ---

SYSTEM_PROMPT_MULTI = """You are an AI assistant embedded in a file portal for FSx for ONTAP.
You help users navigate, search, read, and analyze files stored on NAS volumes.

You operate as a MULTI-AGENT SYSTEM with specialist roles:
- **file-explorer** (Tools: list_files, read_file, search_files, get_volume_summary)
  Handles file browsing, reading, and name-based pattern search.
- **knowledge-analyst** (Tool: kb_search)
  Handles semantic search over file CONTENTS using RAG (Knowledge Base).
  Use kb_search when users ask about topics, concepts, or information INSIDE files.
- **safety-controller** (Tool: request_action_approval)
  Gates dangerous/irreversible operations. Always request approval first.

TOOL SELECTION STRATEGY:
- User asks "what files are in X folder?" → list_files (file-explorer)
- User asks "find files named X" → search_files (file-explorer)
- User asks "what does the spec say about X?" → kb_search (knowledge-analyst)
- User asks "summarize this file" → read_file then analyze (file-explorer)
- User asks to delete/lock/block → request_action_approval (safety-controller)

Guidelines:
- Be concise and helpful
- When asked about file contents, prefer kb_search for questions about topics/meaning
- Use read_file only when the user specifies a particular file to read
- If a tool returns an error, explain it clearly to the user
- Never fabricate file contents — only report what the tools return
- Respect PHI guardrails: if read_file is blocked, explain why
- Answer in the same language the user uses
- When citing information from kb_search, mention the source file path

CRITICAL — Human-in-the-Loop (HITL) Rules:
- DELETE files/volumes/snapshots → request_action_approval FIRST
- LOCK snapshots (SnapLock/tamperproof) → request_action_approval FIRST
- BLOCK users or IPs → request_action_approval FIRST
- ENABLE SnapLock Compliance (irreversible) → request_action_approval FIRST
- Modify retention periods → request_action_approval FIRST
"""

SYSTEM_PROMPT_KB = """You are a knowledge assistant for files stored on FSx for ONTAP.
You answer questions by searching the Knowledge Base (semantic vector search over file contents).

When a user asks a question:
1. Use kb_search to find relevant information from the indexed files
2. Synthesize a clear, concise answer based on the search results
3. Always cite the source file path for each piece of information

Guidelines:
- Be concise and factual
- Always cite sources (file paths) when answering
- If kb_search returns no results, say so clearly — do not fabricate answers
- Answer in the same language the user uses
"""

SYSTEM_PROMPT_AGENT = """You are a file assistant for NAS volumes on FSx for ONTAP.
You help users browse directories, read files, and search by file name.

Available tools:
- list_files: Browse directory contents
- read_file: Read file content (blocked for PHI-protected paths)
- search_files: Find files by name pattern
- get_volume_summary: Overview of volume structure

Guidelines:
- Be concise and helpful
- If a tool returns an error, explain it clearly
- Never fabricate file contents
- Respect PHI guardrails
- Answer in the same language the user uses

CRITICAL — for any destructive action (delete, lock, block), use request_action_approval FIRST.
"""

# Mode-to-tools mapping
TOOLS_KB_ONLY = ["kb_search"]
TOOLS_AGENT_ONLY = ["list_files", "read_file", "search_files", "get_volume_summary", "request_action_approval"]
TOOLS_ALL = ["list_files", "read_file", "search_files", "get_volume_summary", "kb_search", "request_action_approval"]

SYSTEM_PROMPTS = {
    "multi": SYSTEM_PROMPT_MULTI,
    "kb": SYSTEM_PROMPT_KB,
    "agent": SYSTEM_PROMPT_AGENT,
}

TOOLS_BY_MODE = {
    "multi": TOOLS_ALL,
    "kb": TOOLS_KB_ONLY,
    "agent": TOOLS_AGENT_ONLY,
}


def run_agent_loop(
    message: str,
    history: list[dict[str, str]],
    image: dict | None = None,
    mode: str = "multi",
    user_groups: list[str] | None = None,
    system_prompt: str | None = None,
    allowed_tools: list[str] | None = None,
) -> dict[str, Any]:
    """Run the multi-agent Bedrock Converse loop with tool_use.

    Architecture: Supervisor (single LLM call) dispatches to specialist agents
    via tool_use. Each tool is associated with a specialist agent role.
    The trace shows which specialist handled each step.

    Modes:
      - "multi": Full multi-agent (all tools + KB)
      - "kb": Knowledge Base only (semantic search Q&A)
      - "agent": File operations only (no KB)

    Args:
      image: Optional dict with { data: base64_string, mediaType: "image/jpeg" }
      mode: Agent mode ("multi", "kb", "agent")
      user_groups: Cognito groups for KB smart routing

    Returns: { answer, toolCalls, model, error, guardrailApplied, approvalRequired }
    """
    import base64

    # A stored agent or team supplies its own prompt and tool set; otherwise the
    # mode presets apply. The caller has already narrowed the tools to ones that
    # exist, so nothing here can name a capability the portal does not have.
    system_prompt = system_prompt or SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPT_MULTI)
    allowed_tools = allowed_tools or TOOLS_BY_MODE.get(mode, TOOLS_ALL)

    # Filter tool config to only include allowed tools
    filtered_tools = {"tools": [t for t in TOOL_CONFIG["tools"] if t["toolSpec"]["name"] in allowed_tools]}

    # Store user_groups for smart routing in kb_search
    _request_context["user_groups"] = user_groups or []

    # Build messages from history + new message
    messages = []
    for h in history:
        messages.append(
            {
                "role": h["role"],
                "content": [{"text": h["content"]}],
            }
        )

    # Build user message content blocks (text + optional image)
    user_content = [{"text": message}]
    if image and image.get("data"):
        try:
            media_type = image.get("mediaType", "image/jpeg")
            fmt = media_type.split("/")[-1]  # jpeg, png, gif, webp
            if fmt == "jpg":
                fmt = "jpeg"
            image_bytes = base64.b64decode(image["data"])
            user_content.append(
                {
                    "image": {
                        "format": fmt,
                        "source": {"bytes": image_bytes},
                    }
                }
            )
            logger.info(f"Image attached: {fmt}, {len(image_bytes)} bytes")
        except Exception as e:
            logger.warning(f"Failed to decode image: {e}")

    messages.append(
        {
            "role": "user",
            "content": user_content,
        }
    )

    tool_calls_trace: list[dict[str, Any]] = []
    guardrail_applied = False

    # Build guardrail config (only if configured)
    guardrail_config = {}
    if GUARDRAIL_ID:
        guardrail_config = {
            "guardrailIdentifier": GUARDRAIL_ID,
            "guardrailVersion": GUARDRAIL_VERSION,
        }

    for iteration in range(MAX_TOOL_ITERATIONS):
        try:
            converse_params = {
                "modelId": MODEL_ID,
                "messages": messages,
                "system": [{"text": system_prompt}],
                "toolConfig": filtered_tools,
                "inferenceConfig": {
                    "maxTokens": 2048,
                    "temperature": 0.3,
                    "topP": 0.9,
                },
            }
            if guardrail_config:
                converse_params["guardrailConfig"] = guardrail_config

            response = bedrock.converse(**converse_params)
        except Exception as e:
            logger.error(f"Bedrock converse error: {e}")
            return {
                "answer": "",
                "toolCalls": tool_calls_trace,
                "model": MODEL_ID,
                "error": str(e),
                "guardrailApplied": False,
            }

        stop_reason = response.get("stopReason", "")
        output_message = response.get("output", {}).get("message", {})

        # Check if model wants to use tools
        if stop_reason == "tool_use":
            # Process tool use blocks
            tool_use_blocks = [block for block in output_message.get("content", []) if "toolUse" in block]

            # Append assistant message (with tool requests)
            messages.append(output_message)

            # Execute each tool and build result message
            tool_results = []
            for block in tool_use_blocks:
                tool_use = block["toolUse"]
                tool_name = tool_use["name"]
                tool_input = tool_use.get("input", {})
                tool_use_id = tool_use["toolUseId"]

                logger.info(f"Tool call: {tool_name}({json.dumps(tool_input)[:100]})")

                # Execute tool
                result, agent_label = execute_tool(tool_name, tool_input)

                # Check for HITL approval request
                try:
                    result_data = json.loads(result)
                except (json.JSONDecodeError, TypeError):
                    result_data = {}

                if result_data.get("approval_required"):
                    # Stop the loop and return approval request to frontend
                    tool_calls_trace.append(
                        {
                            "name": tool_name,
                            "input": tool_input,
                            "output": result[:500],
                            "status": "approval_required",
                            "agent": agent_label,
                        }
                    )
                    return {
                        "answer": "",
                        "toolCalls": tool_calls_trace,
                        "model": MODEL_ID,
                        "error": None,
                        "guardrailApplied": guardrail_applied,
                        "approvalRequired": {
                            "actionType": result_data.get("action_type", ""),
                            "target": result_data.get("target", ""),
                            "reason": result_data.get("reason", ""),
                            "isReversible": result_data.get("is_reversible", True),
                        },
                    }

                # Record for trace
                tool_calls_trace.append(
                    {
                        "name": tool_name,
                        "input": tool_input,
                        "output": result[:500],  # Truncate for frontend
                        "status": "completed" if "error" not in result else "error",
                        "agent": agent_label,
                    }
                )

                tool_results.append(
                    {
                        "toolResult": {
                            "toolUseId": tool_use_id,
                            "content": [{"json": result_data if result_data else {"text": result}}],
                        }
                    }
                )

            # Append tool results as user message
            messages.append(
                {
                    "role": "user",
                    "content": tool_results,
                }
            )

            # Continue loop for next Bedrock call
            continue

        # Final response (end_turn or max_tokens or guardrail)
        # Check for guardrail intervention
        if stop_reason == "guardrail":
            guardrail_applied = True
            logger.info("Guardrail intervened on response")

        text_blocks = [block["text"] for block in output_message.get("content", []) if "text" in block]
        answer = "\n".join(text_blocks) if text_blocks else ""

        # Strip <thinking> tags (Nova models include reasoning in these)
        answer = re.sub(r"<thinking>[\s\S]*?</thinking>", "", answer).strip()

        # If guardrail blocked entirely and no text, use a user-friendly message
        if guardrail_applied and not answer:
            answer = ""

        return {
            "answer": answer,
            "toolCalls": tool_calls_trace,
            "model": MODEL_ID,
            "error": None,
            "guardrailApplied": guardrail_applied,
        }

    # Max iterations reached
    return {
        "answer": "I reached the maximum number of tool calls. Here's what I found so far based on the tools I used.",
        "toolCalls": tool_calls_trace,
        "model": MODEL_ID,
        "error": None,
        "guardrailApplied": guardrail_applied,
    }


# --- Lambda Handler ---


def handler(event, context):
    """Generic dispatch handler for agent chat.

    Actions:
      - chat: Run agent conversation loop
      - saveSession: Save chat session to DynamoDB
      - loadSession: Load a specific chat session
      - listSessions: List user's chat sessions
      - deleteSession: Delete a chat session
    """
    action = event.get("action", "")
    params = event.get("params", {})
    user_id = event.get("userId", "anonymous")
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except (json.JSONDecodeError, TypeError):
            params = {}

    if action == "chat":
        message = params.get("message", "")
        history = params.get("history", [])
        image = params.get("image", None)
        mode = params.get("mode", "multi")
        user_groups = event.get("userGroups", [])

        # Only the `chat` action. The session actions below store and retrieve the
        # caller's own transcripts and reach no model, so denying those as well would
        # break the screen without withholding anything.
        denied = ai_denial_reason(user_groups, ai_enabled=EXTERNAL_AI_ENABLED)
        if denied:
            logger.info("Agent chat refused for an external caller: %s", denied)
            return {"answer": "", "error": denied, "toolCalls": []}

        if not message and not image:
            return {"answer": "", "error": "Message is required", "toolCalls": []}

        # A stored agent or team replaces the mode presets. Resolved before the
        # model call so a definition that cannot run says so instead of silently
        # falling back to a general assistant the caller did not ask for.
        target, target_error = _resolve_run_target(user_id, params)
        if target_error:
            return {"answer": "", "error": target_error["error"], "toolCalls": []}

        result = run_agent_loop(
            message,
            history,
            image=image,
            mode=mode,
            user_groups=user_groups,
            system_prompt=target["systemPrompt"] if target else None,
            allowed_tools=target["tools"] if target else None,
        )
        if target:
            # Named in the response so the transcript records which definition ran,
            # not merely that the agent screen was used.
            result["ranAs"] = target["name"]
            if target.get("unavailable"):
                result["unavailableMembers"] = target["unavailable"]
        return result

    # --- Chat History Actions ---
    if action == "saveSession":
        return _save_session(user_id, params)
    elif action == "loadSession":
        return _load_session(user_id, params)
    elif action == "listSessions":
        return _list_sessions(user_id, params)
    elif action == "deleteSession":
        return _delete_session(user_id, params)

    # --- Agent Directory Actions ---
    elif action == "listAgents":
        return _list_agents(user_id, params)
    elif action == "getAgent":
        return _get_agent(params)
    elif action == "createAgent":
        return _create_agent(user_id, params)
    elif action == "updateAgent":
        return _update_agent(user_id, params)
    elif action == "deleteAgent":
        return _delete_agent(user_id, params)

    # --- Agent Teams Actions ---
    elif action == "listTeams":
        return _list_teams(user_id, params)
    elif action == "createTeam":
        return _create_team(user_id, params)
    elif action == "deleteTeam":
        return _delete_team(user_id, params)

    return {"error": f"Unknown action: {action}"}


# ─── Chat History Persistence (DynamoDB) ──────────────────────────────────────


def _save_session(user_id: str, params: dict) -> dict:
    """Save or update a chat session.

    Params: { sessionId, title, messages: [...] }
    """
    if not CHAT_HISTORY_TABLE:
        return {"error": "Chat history not configured"}

    session_id = params.get("sessionId", "")
    title = params.get("title", "Untitled")
    messages = params.get("messages", [])

    if not session_id:
        session_id = f"sess-{int(time.time() * 1000)}"

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(CHAT_HISTORY_TABLE)

    now = int(time.time())
    # TTL: 90 days from last update
    ttl = now + (90 * 24 * 60 * 60)

    try:
        table.put_item(
            Item={
                "userId": user_id,
                "sessionId": session_id,
                "title": title,
                "messages": json.dumps(messages, ensure_ascii=False),
                "messageCount": len(messages),
                "createdAt": Decimal(str(params.get("createdAt", now))),
                "updatedAt": Decimal(str(now)),
                "ttl": ttl,
            }
        )
        return {"success": True, "sessionId": session_id}
    except Exception as e:
        logger.error(f"Save session error: {e}")
        return {"error": str(e)}


def _load_session(user_id: str, params: dict) -> dict:
    """Load a specific chat session.

    Params: { sessionId }
    """
    if not CHAT_HISTORY_TABLE:
        return {"error": "Chat history not configured"}

    session_id = params.get("sessionId", "")
    if not session_id:
        return {"error": "sessionId is required"}

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(CHAT_HISTORY_TABLE)

    try:
        response = table.get_item(Key={"userId": user_id, "sessionId": session_id})
        item = response.get("Item")
        if not item:
            return {"error": "Session not found"}

        messages = json.loads(item.get("messages", "[]"))
        return {
            "sessionId": item["sessionId"],
            "title": item.get("title", ""),
            "messages": messages,
            "messageCount": int(item.get("messageCount", 0)),
            "createdAt": int(item.get("createdAt", 0)),
            "updatedAt": int(item.get("updatedAt", 0)),
        }
    except Exception as e:
        logger.error(f"Load session error: {e}")
        return {"error": str(e)}


def _list_sessions(user_id: str, params: dict) -> dict:
    """List chat sessions for a user (most recent first).

    Params: { limit? }
    """
    if not CHAT_HISTORY_TABLE:
        return {"sessions": []}

    limit = int(params.get("limit", 20))

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(CHAT_HISTORY_TABLE)

    try:
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("userId").eq(user_id),
            ScanIndexForward=False,
            Limit=limit,
            ProjectionExpression="sessionId, title, messageCount, createdAt, updatedAt",
        )
        sessions = []
        for item in response.get("Items", []):
            sessions.append(
                {
                    "sessionId": item["sessionId"],
                    "title": item.get("title", ""),
                    "messageCount": int(item.get("messageCount", 0)),
                    "createdAt": int(item.get("createdAt", 0)),
                    "updatedAt": int(item.get("updatedAt", 0)),
                }
            )
        return {"sessions": sessions}
    except Exception as e:
        logger.error(f"List sessions error: {e}")
        return {"sessions": [], "error": str(e)}


def _delete_session(user_id: str, params: dict) -> dict:
    """Delete a chat session.

    Params: { sessionId }
    """
    if not CHAT_HISTORY_TABLE:
        return {"error": "Chat history not configured"}

    session_id = params.get("sessionId", "")
    if not session_id:
        return {"error": "sessionId is required"}

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(CHAT_HISTORY_TABLE)

    try:
        table.delete_item(Key={"userId": user_id, "sessionId": session_id})
        return {"success": True}
    except Exception as e:
        logger.error(f"Delete session error: {e}")
        return {"error": str(e)}


# ─── Running a stored agent or team ───────────────────────────────────────────
#
# The directory and the team wizard could save a definition and nothing could run
# it: `chat` took a message, a history and one of three built-in modes, and had no
# parameter for a stored agent. An agent is a system prompt plus a tool selection,
# which is exactly what the loop already takes — so running one is a matter of
# handing it those two values instead of a mode's presets.


def _runnable_tools(requested: list[str] | None) -> list[str]:
    """The subset of `requested` this deployment can actually run.

    Intersected with the implemented tools rather than trusted, so a stored
    definition — which anyone who can reach the creator form can write — cannot
    name a capability that does not exist, or one added later by a rename.

    `request_action_approval` is always included. It is the HITL gate the built-in
    prompts route destructive intent through, and an agent saved without it would
    otherwise be an agent with no way to ask.
    """
    known = set(TOOL_HANDLERS)
    tools = [name for name in (requested or []) if name in known]
    if "request_action_approval" not in tools:
        tools.append("request_action_approval")
    return tools


def _may_use(item: dict, user_id: str) -> bool:
    """Whether `user_id` may run this stored definition.

    The same rule the listings use: your own, or one its author shared. `_get_agent`
    does not check this — it is a detail view keyed by an id the caller already
    has — but running one executes its author's instructions, so the check belongs
    on this path.
    """
    return item.get("createdBy") == user_id or bool(item.get("isShared", False))


def _agent_runtime(user_id: str, agent_id: str) -> tuple[dict | None, dict | None]:
    """A stored agent's prompt and tools, or an error payload."""
    if not AGENT_DIRECTORY_TABLE:
        return None, {"error": "Agent directory not configured"}
    ddb = boto3.resource("dynamodb")
    item = ddb.Table(AGENT_DIRECTORY_TABLE).get_item(Key={"agentId": agent_id}).get("Item")
    if not item:
        return None, {"error": f"Agent '{agent_id}' not found"}
    if not _may_use(item, user_id):
        return None, {"error": "This agent is not shared with you"}
    prompt = (item.get("systemPrompt") or "").strip()
    if not prompt:
        return None, {"error": "This agent has no system prompt, so there is nothing to run"}
    return {
        "name": item.get("name", agent_id),
        "systemPrompt": prompt,
        "tools": _runnable_tools(list(item.get("tools") or [])),
    }, None


def _team_runtime(user_id: str, team_id: str) -> tuple[dict | None, dict | None]:
    """A stored team's composed prompt and pooled tools, or an error payload.

    One supervisor turn, told who is on the team and what each member is for, with
    the union of their tools available. That is what the loop can do: it is a single
    Converse conversation, and the "multi-agent" trace labels tool calls by role
    rather than running separate sessions. Presenting it as concurrent agents would
    describe a system this is not — the members are instructions the supervisor is
    told to follow, and the timeline attributes each tool call to the member whose
    selection includes that tool.
    """
    if not AGENT_TEAMS_TABLE:
        return None, {"error": "Agent teams not configured"}
    ddb = boto3.resource("dynamodb")
    item = ddb.Table(AGENT_TEAMS_TABLE).get_item(Key={"teamId": team_id}).get("Item")
    if not item:
        return None, {"error": f"Team '{team_id}' not found"}
    if not _may_use(item, user_id):
        return None, {"error": "This team is not shared with you"}

    members = item.get("agents")
    if isinstance(members, str):
        members = json.loads(members)
    members = members or []
    if len(members) < 2:
        return None, {"error": "A team needs at least 2 members to run"}

    sections: list[str] = []
    pooled: list[str] = []
    unavailable: list[str] = []
    for member in members:
        member_id = member.get("agentId", "")
        runtime, error = _agent_runtime(user_id, member_id) if member_id else (None, {"error": "missing agentId"})
        if error:
            # One unreachable member does not stop the team: the others still have
            # something to contribute, and naming the gap is more use than failing
            # the whole run over a member that was deleted or never shared.
            unavailable.append(f"{member.get('name', member_id)} ({error['error']})")
            continue
        sections.append(
            f"### {member.get('name', runtime['name'])} — role: {member.get('role', 'collaborator')}\n"
            f"Tools: {', '.join(runtime['tools'])}\n"
            f"{runtime['systemPrompt']}"
        )
        pooled.extend(runtime["tools"])

    if not sections:
        return None, {"error": "No member of this team could be run: " + "; ".join(unavailable)}

    header = (
        f"You are the supervisor of the '{item.get('name', team_id)}' team working in a file "
        "portal for FSx for ONTAP.\n"
        f"{item.get('description', '')}\n\n"
        "You act as every member below in one conversation. For each step, choose the member "
        "whose role and instructions fit the request, follow that member's instructions, and use "
        "only the tools listed for them. Say which member you are acting as when it changes.\n\n"
        "Team members:\n\n"
    )
    footer = ""
    if unavailable:
        footer = "\n\nMembers unavailable for this run: " + "; ".join(unavailable)

    return {
        "name": item.get("name", team_id),
        "systemPrompt": header + "\n\n".join(sections) + footer,
        "tools": _runnable_tools(pooled),
        "unavailable": unavailable,
    }, None


def _resolve_run_target(user_id: str, params: dict) -> tuple[dict | None, dict | None]:
    """The stored agent or team this request names, if it names one.

    Returns `(None, None)` when neither is given, which is the built-in-mode path.
    A request naming both is refused rather than resolved by precedence: guessing
    which the caller meant would run instructions they did not ask for.
    """
    agent_id = params.get("agentId") or ""
    team_id = params.get("teamId") or ""
    if agent_id and team_id:
        return None, {"error": "Name either agentId or teamId, not both"}
    if agent_id:
        return _agent_runtime(user_id, agent_id)
    if team_id:
        return _team_runtime(user_id, team_id)
    return None, None


# ─── Agent Directory (DynamoDB) ───────────────────────────────────────────────


def _list_agents(user_id: str, params: dict) -> dict:
    """List agents: user's own + shared agents."""
    if not AGENT_DIRECTORY_TABLE:
        return {"agents": [], "error": "Agent directory not configured"}

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(AGENT_DIRECTORY_TABLE)

    try:
        response = table.scan()
        agents = []
        for item in response.get("Items", []):
            # Show user's own agents + shared agents
            if item.get("createdBy") == user_id or item.get("isShared", False):
                agents.append(
                    {
                        "agentId": item["agentId"],
                        "name": item.get("name", ""),
                        "description": item.get("description", ""),
                        "icon": item.get("icon", "🤖"),
                        "category": item.get("category", "custom"),
                        "tools": item.get("tools", []),
                        "isShared": item.get("isShared", False),
                        "createdBy": item.get("createdBy", ""),
                        "createdAt": int(item.get("createdAt", 0)),
                    }
                )
        # Sort by createdAt desc
        agents.sort(key=lambda a: a["createdAt"], reverse=True)
        return {"agents": agents}
    except Exception as e:
        logger.error(f"List agents error: {e}")
        return {"agents": [], "error": str(e)}


def _get_agent(params: dict) -> dict:
    """Get a specific agent by ID."""
    if not AGENT_DIRECTORY_TABLE:
        return {"error": "Agent directory not configured"}

    agent_id = params.get("agentId", "")
    if not agent_id:
        return {"error": "agentId is required"}

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(AGENT_DIRECTORY_TABLE)

    try:
        response = table.get_item(Key={"agentId": agent_id})
        item = response.get("Item")
        if not item:
            return {"error": "Agent not found"}

        return {
            "agent": {
                "agentId": item["agentId"],
                "name": item.get("name", ""),
                "description": item.get("description", ""),
                "systemPrompt": item.get("systemPrompt", ""),
                "icon": item.get("icon", "🤖"),
                "category": item.get("category", "custom"),
                "tools": item.get("tools", []),
                "isShared": item.get("isShared", False),
                "createdBy": item.get("createdBy", ""),
                "createdAt": int(item.get("createdAt", 0)),
                "updatedAt": int(item.get("updatedAt", 0)),
            }
        }
    except Exception as e:
        logger.error(f"Get agent error: {e}")
        return {"error": str(e)}


def _create_agent(user_id: str, params: dict) -> dict:
    """Create a new custom agent."""
    if not AGENT_DIRECTORY_TABLE:
        return {"error": "Agent directory not configured"}

    name = params.get("name", "").strip()
    if not name:
        return {"error": "Agent name is required"}

    description = params.get("description", "")
    system_prompt = params.get("systemPrompt", "")
    tools = params.get("tools", [])
    icon = params.get("icon", "🤖")
    category = params.get("category", "custom")
    is_shared = params.get("isShared", False)

    # Validate tools against available tool names
    valid_tools = {
        "list_files",
        "read_file",
        "search_files",
        "get_volume_summary",
        "kb_search",
        "request_action_approval",
    }
    invalid = [t for t in tools if t not in valid_tools]
    if invalid:
        return {"error": f"Invalid tools: {invalid}. Valid: {sorted(valid_tools)}"}

    agent_id = str(uuid.uuid4())
    now = int(time.time())

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(AGENT_DIRECTORY_TABLE)

    try:
        table.put_item(
            Item={
                "agentId": agent_id,
                "name": name,
                "description": description,
                "systemPrompt": system_prompt,
                "tools": tools,
                "icon": icon,
                "category": category,
                "isShared": is_shared,
                "createdBy": user_id,
                "createdAt": Decimal(str(now)),
                "updatedAt": Decimal(str(now)),
            }
        )
        return {"success": True, "agentId": agent_id}
    except Exception as e:
        logger.error(f"Create agent error: {e}")
        return {"error": str(e)}


def _update_agent(user_id: str, params: dict) -> dict:
    """Update an existing agent (only creator can update)."""
    if not AGENT_DIRECTORY_TABLE:
        return {"error": "Agent directory not configured"}

    agent_id = params.get("agentId", "")
    if not agent_id:
        return {"error": "agentId is required"}

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(AGENT_DIRECTORY_TABLE)

    # Check ownership
    try:
        existing = table.get_item(Key={"agentId": agent_id}).get("Item")
        if not existing:
            return {"error": "Agent not found"}
        if existing.get("createdBy") != user_id:
            return {"error": "Only the creator can update this agent"}
    except Exception as e:
        return {"error": str(e)}

    # Each field is read by name rather than by looping over a list of keys.
    # The loop worked, but the parameter contract was invisible to anything
    # reading this source — including the dispatch type generator, which
    # therefore told callers `updateAgent` accepted `agentId` and nothing else.
    # A partial update stays possible: `_MISSING` distinguishes "not sent" from
    # "sent as empty", so clearing a description is not the same as omitting it.
    editable = {
        "name": params.get("name", _MISSING),
        "description": params.get("description", _MISSING),
        "systemPrompt": params.get("systemPrompt", _MISSING),
        "tools": params.get("tools", _MISSING),
        "icon": params.get("icon", _MISSING),
        "category": params.get("category", _MISSING),
        "isShared": params.get("isShared", _MISSING),
    }
    updates = {key: value for key, value in editable.items() if value is not _MISSING}
    updates["updatedAt"] = Decimal(str(int(time.time())))

    try:
        expr_parts = []
        expr_values = {}
        expr_names = {}
        for i, (k, v) in enumerate(updates.items()):
            attr_name = f"#k{i}"
            attr_val = f":v{i}"
            expr_parts.append(f"{attr_name} = {attr_val}")
            expr_names[attr_name] = k
            expr_values[attr_val] = v

        table.update_item(
            Key={"agentId": agent_id},
            UpdateExpression="SET " + ", ".join(expr_parts),
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )
        return {"success": True, "agentId": agent_id}
    except Exception as e:
        logger.error(f"Update agent error: {e}")
        return {"error": str(e)}


def _delete_agent(user_id: str, params: dict) -> dict:
    """Delete an agent (only creator can delete)."""
    if not AGENT_DIRECTORY_TABLE:
        return {"error": "Agent directory not configured"}

    agent_id = params.get("agentId", "")
    if not agent_id:
        return {"error": "agentId is required"}

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(AGENT_DIRECTORY_TABLE)

    # Check ownership
    try:
        existing = table.get_item(Key={"agentId": agent_id}).get("Item")
        if not existing:
            return {"error": "Agent not found"}
        if existing.get("createdBy") != user_id:
            return {"error": "Only the creator can delete this agent"}
    except Exception as e:
        return {"error": str(e)}

    try:
        table.delete_item(Key={"agentId": agent_id})
        return {"success": True}
    except Exception as e:
        logger.error(f"Delete agent error: {e}")
        return {"error": str(e)}


# ─── Agent Teams (DynamoDB) ───────────────────────────────────────────────────


def _list_teams(user_id: str, params: dict) -> dict:
    """List teams: user's own + shared."""
    if not AGENT_TEAMS_TABLE:
        return {"teams": [], "error": "Agent teams not configured"}

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(AGENT_TEAMS_TABLE)

    try:
        response = table.scan()
        teams = []
        for item in response.get("Items", []):
            if item.get("createdBy") == user_id or item.get("isShared", False):
                teams.append(
                    {
                        "teamId": item["teamId"],
                        "name": item.get("name", ""),
                        "description": item.get("description", ""),
                        "agents": json.loads(item["agents"])
                        if isinstance(item.get("agents"), str)
                        else item.get("agents", []),
                        "isShared": item.get("isShared", False),
                        "createdBy": item.get("createdBy", ""),
                        "createdAt": int(item.get("createdAt", 0)),
                    }
                )
        teams.sort(key=lambda t: t["createdAt"], reverse=True)
        return {"teams": teams}
    except Exception as e:
        logger.error(f"List teams error: {e}")
        return {"teams": [], "error": str(e)}


def _create_team(user_id: str, params: dict) -> dict:
    """Create a multi-agent team."""
    if not AGENT_TEAMS_TABLE:
        return {"error": "Agent teams not configured"}

    name = params.get("name", "").strip()
    if not name:
        return {"error": "Team name is required"}

    agents = params.get("agents", [])
    if len(agents) < 2:
        return {"error": "A team requires at least 2 agents"}

    description = params.get("description", "")
    is_shared = params.get("isShared", False)
    team_id = str(uuid.uuid4())
    now = int(time.time())

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(AGENT_TEAMS_TABLE)

    try:
        table.put_item(
            Item={
                "teamId": team_id,
                "name": name,
                "description": description,
                "agents": json.dumps(agents, ensure_ascii=False),
                "isShared": is_shared,
                "createdBy": user_id,
                "createdAt": Decimal(str(now)),
            }
        )
        return {"success": True, "teamId": team_id}
    except Exception as e:
        logger.error(f"Create team error: {e}")
        return {"error": str(e)}


def _delete_team(user_id: str, params: dict) -> dict:
    """Delete a team (only creator can delete)."""
    if not AGENT_TEAMS_TABLE:
        return {"error": "Agent teams not configured"}

    team_id = params.get("teamId", "")
    if not team_id:
        return {"error": "teamId is required"}

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(AGENT_TEAMS_TABLE)

    try:
        existing = table.get_item(Key={"teamId": team_id}).get("Item")
        if not existing:
            return {"error": "Team not found"}
        if existing.get("createdBy") != user_id:
            return {"error": "Only the creator can delete this team"}
        table.delete_item(Key={"teamId": team_id})
        return {"success": True}
    except Exception as e:
        logger.error(f"Delete team error: {e}")
        return {"error": str(e)}
