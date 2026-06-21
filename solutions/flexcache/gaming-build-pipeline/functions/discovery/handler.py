"""Gaming Build Pipeline Discovery Lambda

S3 AP 経由でゲームビルド成果物・アセット・ログを検出する。
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

GAMING_EXTENSIONS = {
    # テクスチャ
    ".png",
    ".tga",
    ".dds",
    ".exr",
    ".hdr",
    ".psd",
    # 3D モデル
    ".fbx",
    ".obj",
    ".usd",
    ".usda",
    ".usdz",
    ".gltf",
    ".glb",
    # シェーダー
    ".hlsl",
    ".glsl",
    ".shader",
    ".cginc",
    # ビルド成果物
    ".pak",
    ".bundle",
    ".asset",
    # ログ
    ".log",
    ".json",
    ".csv",
    ".txt",
    # アニメーション
    ".anim",
    ".clip",
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Discovery Lambda ハンドラー"""
    logger.info("Gaming Build Pipeline Discovery started")

    s3ap_alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")
    prefix = event.get("prefix", "builds/")
    max_keys = event.get("max_keys", 500)

    objects = []
    continuation_token = None

    try:
        while len(objects) < max_keys:
            kwargs = {
                "Bucket": s3ap_alias,
                "Prefix": prefix,
                "MaxKeys": min(1000, max_keys - len(objects)),
            }
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token

            response = s3_client.list_objects_v2(**kwargs)

            for obj in response.get("Contents", []):
                key = obj["Key"]
                ext = os.path.splitext(key)[1].lower()
                if ext in GAMING_EXTENSIONS:
                    objects.append(
                        {
                            "key": key,
                            "size": obj["Size"],
                            "last_modified": obj["LastModified"].isoformat(),
                            "extension": ext,
                            "category": _categorize(ext),
                        }
                    )

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")

    except Exception as e:
        logger.error("Discovery failed: %s", str(e))
        return {"status": "error", "error": str(e), "objects": []}

    logger.info("Discovered %d gaming assets/artifacts", len(objects))
    return {
        "status": "completed",
        "object_count": len(objects),
        "objects": objects,
        "timestamp": int(time.time()),
    }


def _categorize(ext: str) -> str:
    """拡張子からカテゴリを判定"""
    textures = {".png", ".tga", ".dds", ".exr", ".hdr", ".psd"}
    models = {".fbx", ".obj", ".usd", ".usda", ".usdz", ".gltf", ".glb"}
    shaders = {".hlsl", ".glsl", ".shader", ".cginc"}
    builds = {".pak", ".bundle", ".asset"}
    logs = {".log", ".json", ".csv", ".txt"}
    animations = {".anim", ".clip"}

    if ext in textures:
        return "texture"
    elif ext in models:
        return "3d_model"
    elif ext in shaders:
        return "shader"
    elif ext in builds:
        return "build_artifact"
    elif ext in logs:
        return "log"
    elif ext in animations:
        return "animation"
    return "other"
