"""メディア VFX Discovery Lambda ハンドラ

S3 Access Point からレンダリング対象アセット（.exr, .dpx, .tga, .obj,
.fbx, .blend 等）を検出し、Manifest JSON を生成して S3 AP に書き出す。

Step Functions ワークフローの最初のステップとして実行され、
後続の Map ステート（Job Submit → Quality Check）にアセット一覧を渡す。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用、省略時は S3_ACCESS_POINT を使用)
    PREFIX_FILTER: プレフィックスフィルタ (optional)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

# レンダリング対象アセットの拡張子一覧
RENDER_ASSET_EXTENSIONS = (
    ".exr",
    ".dpx",
    ".tga",
    ".obj",
    ".fbx",
    ".blend",
    ".abc",
    ".usd",
    ".usda",
    ".usdc",
    ".usdz",
    ".ma",
    ".mb",
    ".hip",
    ".hda",
)


def _filter_render_assets(objects: list[dict]) -> list[dict]:
    """レンダリング対象アセットのみをフィルタリングする

    Args:
        objects: S3ApHelper.list_objects() の結果リスト

    Returns:
        list[dict]: レンダリング対象拡張子に一致するオブジェクトのみ
    """
    return [
        obj
        for obj in objects
        if any(obj["Key"].lower().endswith(ext) for ext in RENDER_ASSET_EXTENSIONS)
    ]


@lambda_error_handler
def handler(event, context):
    """Media VFX Discovery Lambda

    S3 AP からオブジェクト一覧を取得し、レンダリング対象アセットを
    フィルタリングして Manifest JSON を生成・S3 に書き出す。

    Returns:
        dict: manifest_bucket, manifest_key, total_objects, objects
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"])
    )
    prefix = os.environ.get("PREFIX_FILTER", "")

    logger.info(
        "Media VFX Discovery started: access_point=%s, prefix=%r",
        os.environ["S3_ACCESS_POINT"],
        prefix,
    )

    # S3 AP からオブジェクト一覧取得
    all_objects = s3ap.list_objects(prefix=prefix)

    # レンダリング対象アセットのみフィルタリング
    render_assets = _filter_render_assets(all_objects)

    logger.info(
        "Render assets found: total_scanned=%d, render_assets=%d",
        len(all_objects),
        len(render_assets),
    )

    # Manifest 生成
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.utcnow().isoformat(),
        "total_objects": len(render_assets),
        "objects": render_assets,
    }

    # Manifest を S3 AP に書き出し
    manifest_key = (
        f"manifests/{datetime.utcnow().strftime('%Y/%m/%d')}"
        f"/{context.aws_request_id}.json"
    )

    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    logger.info(
        "Media VFX Discovery completed: total_objects=%d, manifest=%s",
        len(render_assets),
        manifest_key,
    )

    return {
        "manifest_key": manifest_key,
        "total_objects": len(render_assets),
        "objects": render_assets,
    }
