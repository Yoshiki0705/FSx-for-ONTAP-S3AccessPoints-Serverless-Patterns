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
import os
import re
import logging
from typing import Any

import boto3
from botocore.config import Config

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

s3 = boto3.client(
    "s3",
    region_name=REGION,
    endpoint_url=f"https://s3.{REGION}.amazonaws.com",
    config=Config(signature_version="s3v4"),
)
bedrock = boto3.client("bedrock-runtime", region_name=REGION)
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION) if BEDROCK_KB_ID else None

# --- PHI Guardrail ---
PHI_PATTERN = re.compile(
    r"/(dicom|phi|pii|hipaa|protected-health)[/\-]", re.IGNORECASE
)


def is_phi_path(path: str) -> bool:
    """Check if path is PHI-protected (same logic as frontend isPhiPath)."""
    lower = path.lower()
    return bool(PHI_PATTERN.search(f"/{lower}")) or any(
        lower.startswith(p) for p in ("dicom/", "phi/", "pii/")
    )


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
        folders = [
            cp["Prefix"] for cp in resp.get("CommonPrefixes", [])
        ]
        files = [
            {
                "key": obj["Key"],
                "size": obj["Size"],
                "modified": obj["LastModified"].isoformat() if obj.get("LastModified") else None,
            }
            for obj in resp.get("Contents", [])
            if not obj["Key"].endswith("/")
        ]
        return json.dumps({
            "folders": folders,
            "files": files,
            "total": len(folders) + len(files),
            "truncated": resp.get("IsTruncated", False),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_read_file(params: dict[str, Any]) -> str:
    """Read file content via S3 AP GetObject."""
    key = params.get("key", "")
    if not key:
        return json.dumps({"error": "File key is required"})

    # PHI guardrail
    if is_phi_path(key):
        return json.dumps({
            "error": f"PHI guardrail: cannot read files in protected path. "
                     f"File '{key}' is in a PHI/PII protected directory.",
            "blocked": True,
        })

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
                    matches.append({
                        "key": obj["Key"],
                        "size": obj["Size"],
                        "modified": obj["LastModified"].isoformat() if obj.get("LastModified") else None,
                    })
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
        return json.dumps({
            "top_level_folders": folders,
            "root_file_count": root_files,
            "folder_count": len(folders),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def _tool_kb_search(params: dict[str, Any]) -> str:
    """Semantic search via Bedrock Knowledge Base (RAG retrieval).

    Searches file CONTENT (not just file names) using vector similarity.
    Requires BEDROCK_KB_ID to be configured.
    """
    query = params.get("query", "")
    max_results = min(params.get("max_results", 5), 10)

    if not query:
        return json.dumps({"error": "Query is required for KB search"})

    if not BEDROCK_KB_ID or not bedrock_agent_runtime:
        return json.dumps({
            "error": "Knowledge Base not configured. Set BEDROCK_KB_ID to enable semantic search over file contents.",
            "results": [],
        })

    try:
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=BEDROCK_KB_ID,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": max_results,
                }
            },
        )

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

            results.append({
                "fileKey": file_key,
                "snippet": content[:300],
                "score": round(score, 4),
            })

        return json.dumps({"results": results, "count": len(results), "query": query})

    except Exception as e:
        logger.error(f"KB search error: {e}")
        return json.dumps({"error": str(e), "results": []})


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
    return json.dumps({
        "top_level_folders": ["engineering/", "contracts/", "simulation/", "reports/"],
        "root_file_count": 2,
        "folder_count": 4,
    })


# --- Tool Execution Router ---

TOOL_HANDLERS = {
    "list_files": _tool_list_files,
    "read_file": _tool_read_file,
    "search_files": _tool_search_files,
    "get_volume_summary": _tool_get_volume_summary,
    "kb_search": _tool_kb_search,
    "request_action_approval": lambda params: json.dumps({
        "approval_required": True,
        "action_type": params.get("action_type", "unknown"),
        "target": params.get("target", ""),
        "reason": params.get("reason", ""),
        "is_reversible": params.get("is_reversible", True),
    }),
}


def execute_tool(name: str, tool_input: dict[str, Any]) -> tuple[str, str]:
    """Execute a tool by name, return (result_json, agent_label)."""
    handler_fn = TOOL_HANDLERS.get(name)
    agent_label = TOOL_AGENT_MAP.get(name, "general")
    if not handler_fn:
        return json.dumps({"error": f"Unknown tool: {name}"}), agent_label
    try:
        return handler_fn(tool_input), agent_label
    except Exception as e:
        logger.error(f"Tool execution error ({name}): {e}")
        return json.dumps({"error": f"Tool execution failed: {e}"}), agent_label


# --- Agent Loop ---

SYSTEM_PROMPT = """You are an AI assistant embedded in a file portal for FSx for ONTAP.
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

Available tools:
- list_files: Browse directories
- read_file: Read file content (blocked for PHI paths like /dicom/, /phi/, /pii/)
- search_files: Find files by name pattern
- get_volume_summary: Overview of the volume structure
- kb_search: Semantic search over file contents via Knowledge Base (RAG)
- request_action_approval: Request human approval before dangerous actions

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


def run_agent_loop(
    message: str,
    history: list[dict[str, str]],
) -> dict[str, Any]:
    """Run the multi-agent Bedrock Converse loop with tool_use.

    Architecture: Supervisor (single LLM call) dispatches to specialist agents
    via tool_use. Each tool is associated with a specialist agent role.
    The trace shows which specialist handled each step.

    Multi-Agent Roles:
      - Supervisor: Orchestrates the overall task, decides which tools to use
      - file-explorer: Browses, reads, searches files via S3 AP
      - knowledge-analyst: Performs semantic search via Bedrock KB (RAG)
      - safety-controller: Gates dangerous operations with HITL approval

    Returns: { answer, toolCalls, model, error, guardrailApplied, approvalRequired }
    """
    # Build messages from history + new message
    messages = []
    for h in history:
        messages.append({
            "role": h["role"],
            "content": [{"text": h["content"]}],
        })
    messages.append({
        "role": "user",
        "content": [{"text": message}],
    })

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
                "system": [{"text": SYSTEM_PROMPT}],
                "toolConfig": TOOL_CONFIG,
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
            return {"answer": "", "toolCalls": tool_calls_trace, "model": MODEL_ID, "error": str(e), "guardrailApplied": False}

        stop_reason = response.get("stopReason", "")
        output_message = response.get("output", {}).get("message", {})

        # Check if model wants to use tools
        if stop_reason == "tool_use":
            # Process tool use blocks
            tool_use_blocks = [
                block for block in output_message.get("content", [])
                if "toolUse" in block
            ]

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
                    tool_calls_trace.append({
                        "name": tool_name,
                        "input": tool_input,
                        "output": result[:500],
                        "status": "approval_required",
                        "agent": agent_label,
                    })
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
                tool_calls_trace.append({
                    "name": tool_name,
                    "input": tool_input,
                    "output": result[:500],  # Truncate for frontend
                    "status": "completed" if "error" not in result else "error",
                    "agent": agent_label,
                })

                tool_results.append({
                    "toolResult": {
                        "toolUseId": tool_use_id,
                        "content": [{"json": result_data if result_data else {"text": result}}],
                    }
                })

            # Append tool results as user message
            messages.append({
                "role": "user",
                "content": tool_results,
            })

            # Continue loop for next Bedrock call
            continue

        # Final response (end_turn or max_tokens or guardrail)
        # Check for guardrail intervention
        if stop_reason == "guardrail":
            guardrail_applied = True
            logger.info("Guardrail intervened on response")

        text_blocks = [
            block["text"]
            for block in output_message.get("content", [])
            if "text" in block
        ]
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
    """
    action = event.get("action", "")
    params = event.get("params", {})
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except (json.JSONDecodeError, TypeError):
            params = {}

    if action == "chat":
        message = params.get("message", "")
        history = params.get("history", [])

        if not message:
            return {"answer": "", "error": "Message is required", "toolCalls": []}

        result = run_agent_loop(message, history)
        return result

    return {"error": f"Unknown action: {action}"}
