"""Gaming Build Pipeline Log Analysis Lambda

ビルドログ、シェーダーコンパイルログを Bedrock で分析し、
エラーパターン・警告・最適化提案を抽出する。
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
bedrock_client = boto3.client("bedrock-runtime")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Log Analysis Lambda ハンドラー"""
    key = event.get("key", "")
    category = event.get("category", "")
    s3ap_alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")
    model_id = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")

    logger.info("Log analysis: %s", key)

    # ログファイルのみ分析
    if category != "log":
        return {
            "key": key,
            "status": "skipped",
            "reason": f"Not a log file (category: {category})",
            "timestamp": int(time.time()),
        }

    try:
        # ログファイル読み取り（先頭 32KB）
        response = s3_client.get_object(
            Bucket=s3ap_alias,
            Key=key,
            Range="bytes=0-32767",
        )
        log_content = response["Body"].read().decode("utf-8", errors="replace")
        response["Body"].close()

        # 基本的なログ分析
        analysis = _analyze_log(log_content)

        # Bedrock による高度な分析（エラーが含まれる場合）
        if analysis["error_count"] > 0:
            ai_summary = _bedrock_log_analysis(log_content, model_id)
            analysis["ai_summary"] = ai_summary

        return {
            "key": key,
            "status": "completed",
            "analysis": analysis,
            "timestamp": int(time.time()),
        }

    except Exception as e:
        logger.error("Log analysis failed for %s: %s", key, str(e))
        return {
            "key": key,
            "status": "error",
            "error": str(e),
            "timestamp": int(time.time()),
        }


def _analyze_log(content: str) -> dict[str, Any]:
    """ログの基本分析"""
    lines = content.split("\n")
    total_lines = len(lines)

    error_lines = [line for line in lines if "error" in line.lower() or "fatal" in line.lower()]
    warning_lines = [line for line in lines if "warning" in line.lower() or "warn" in line.lower()]

    return {
        "total_lines": total_lines,
        "error_count": len(error_lines),
        "warning_count": len(warning_lines),
        "error_samples": error_lines[:5],
        "warning_samples": warning_lines[:5],
        "severity": _determine_severity(len(error_lines), len(warning_lines)),
    }


def _determine_severity(errors: int, warnings: int) -> str:
    """重要度判定"""
    if errors > 0:
        return "critical" if errors > 10 else "error"
    elif warnings > 10:
        return "warning"
    return "info"


def _bedrock_log_analysis(content: str, model_id: str) -> str:
    """Bedrock によるログ分析"""
    try:
        prompt = (
            "Analyze the following build/shader compilation log and provide:\n"
            "1. Root cause of errors (if any)\n"
            "2. Suggested fixes\n"
            "3. Performance optimization opportunities\n\n"
            f"Log content (first 2000 chars):\n{content[:2000]}"
        )

        body = json.dumps(
            {
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": {"maxTokens": 300, "temperature": 0.3},
            }
        )

        response = bedrock_client.invoke_model(
            modelId=model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )

        result = json.loads(response["body"].read())
        return result.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "")

    except Exception as e:
        logger.warning("Bedrock analysis failed: %s", str(e))
        return ""
