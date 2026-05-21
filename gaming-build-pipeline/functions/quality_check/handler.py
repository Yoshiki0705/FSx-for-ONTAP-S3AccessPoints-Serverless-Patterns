"""Gaming Build Pipeline Quality Check Lambda

テクスチャ品質チェック、アセットバリデーション、ビルド成果物検証を行う。
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Quality Check Lambda ハンドラー"""
    key = event.get("key", "")
    category = event.get("category", "")
    size = event.get("size", 0)
    s3ap_alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")

    logger.info("Quality check: %s (category: %s)", key, category)

    issues = []

    # サイズチェック
    if size == 0:
        issues.append("File is empty (0 bytes)")
    elif category == "texture" and size > 100 * 1024 * 1024:
        issues.append(f"Texture exceeds 100MB limit ({size / 1024 / 1024:.1f}MB)")
    elif category == "texture" and size < 100:
        issues.append("Texture file suspiciously small (<100 bytes)")

    # テクスチャ固有チェック
    if category == "texture":
        issues.extend(_check_texture(key, size))

    # シェーダー固有チェック
    elif category == "shader":
        issues.extend(_check_shader(key, s3ap_alias))

    # ビルド成果物チェック
    elif category == "build_artifact":
        issues.extend(_check_build_artifact(key, size))

    quality_score = "PASS" if not issues else ("WARNING" if len(issues) <= 1 else "FAIL")

    return {
        "key": key,
        "status": "completed",
        "category": category,
        "quality_score": quality_score,
        "issues": issues,
        "file_size_mb": round(size / (1024 * 1024), 2),
        "timestamp": int(time.time()),
    }


def _check_texture(key: str, size: int) -> list[str]:
    """テクスチャ品質チェック"""
    issues = []
    basename = os.path.basename(key).lower()

    # 命名規則チェック
    if " " in basename:
        issues.append("Texture filename contains spaces")
    if not basename.replace(".", "").replace("_", "").replace("-", "").isalnum():
        issues.append("Texture filename contains special characters")

    # Power-of-2 サイズ推定（ファイルサイズから）
    # DDS/TGA は通常 power-of-2 テクスチャ
    ext = os.path.splitext(key)[1].lower()
    if ext == ".dds" and size > 0:
        # DDS ヘッダーは 128 bytes
        data_size = size - 128
        # 一般的な power-of-2 サイズ: 256x256, 512x512, 1024x1024, 2048x2048, 4096x4096
        valid_sizes = [s * s * 4 for s in [256, 512, 1024, 2048, 4096]]
        if data_size > 0 and data_size not in valid_sizes:
            pass  # 圧縮フォーマットでは正確な判定が困難

    return issues


def _check_shader(key: str, s3ap_alias: str) -> list[str]:
    """シェーダー品質チェック"""
    issues = []

    try:
        response = s3_client.get_object(
            Bucket=s3ap_alias,
            Key=key,
            Range="bytes=0-8191",
        )
        content = response["Body"].read().decode("utf-8", errors="replace")
        response["Body"].close()

        # 基本的なシェーダーチェック
        if "#pragma" not in content and "#include" not in content and "void" not in content:
            issues.append("Shader file may be empty or invalid (no pragmas/includes/functions)")

        if "TODO" in content or "FIXME" in content:
            issues.append("Shader contains TODO/FIXME comments")

    except Exception as e:
        issues.append(f"Unable to read shader: {str(e)}")

    return issues


def _check_build_artifact(key: str, size: int) -> list[str]:
    """ビルド成果物チェック"""
    issues = []

    if size < 1024:
        issues.append("Build artifact suspiciously small (<1KB)")

    return issues
