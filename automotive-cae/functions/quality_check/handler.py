"""Automotive CAE Quality Check Lambda

Bedrock を使用してシミュレーション結果の品質チェックを行う。
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

bedrock_client = boto3.client("bedrock-runtime")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Quality Check ハンドラー"""
    key = event.get("key", "")
    metadata = event.get("parsed", {}).get("metadata", {})
    model_id = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")

    logger.info("Quality check for: %s", key)

    # メタデータに基づく品質チェック
    quality_issues = _check_quality(metadata)

    # Bedrock による高度な分析（メタデータが十分な場合）
    ai_analysis = ""
    if metadata and not quality_issues:
        ai_analysis = _bedrock_analysis(metadata, model_id)

    result = {
        "key": key,
        "status": "completed",
        "quality_score": _calculate_score(quality_issues),
        "issues": quality_issues,
        "ai_analysis": ai_analysis[:500] if ai_analysis else "",
        "timestamp": int(time.time()),
    }

    logger.info("Quality check completed: score=%s, issues=%d", result["quality_score"], len(quality_issues))
    return result


def _check_quality(metadata: dict) -> list[str]:
    """メタデータに基づく品質チェック"""
    issues = []

    file_size = metadata.get("file_size", 0)
    if file_size == 0:
        issues.append("File size is 0 bytes - possible empty output")
    elif file_size < 1024:
        issues.append("File size < 1KB - possibly incomplete simulation")

    category = metadata.get("category", "")
    if category == "solver_output":
        solver = metadata.get("solver_type", "unknown")
        if solver == "unknown":
            issues.append("Unable to identify solver type")

    if category == "mesh":
        nodes = metadata.get("estimated_nodes", 0)
        if nodes == 0:
            issues.append("No mesh nodes detected - possible format issue")

    return issues


def _calculate_score(issues: list[str]) -> str:
    """品質スコアを計算"""
    if not issues:
        return "PASS"
    elif len(issues) <= 1:
        return "WARNING"
    else:
        return "FAIL"


def _bedrock_analysis(metadata: dict, model_id: str) -> str:
    """Bedrock による分析"""
    try:
        prompt = (
            f"Analyze this CAE simulation metadata and provide a brief quality assessment:\n"
            f"Solver: {metadata.get('solver_type', 'unknown')}\n"
            f"Category: {metadata.get('category', 'unknown')}\n"
            f"File size: {metadata.get('file_size', 0)} bytes\n"
            f"Provide 2-3 sentences about data quality and completeness."
        )

        body = json.dumps({
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 200, "temperature": 0.3},
        })

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
