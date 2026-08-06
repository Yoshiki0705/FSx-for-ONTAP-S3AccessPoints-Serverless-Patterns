"""メディア VFX Discovery Lambda ハンドラ

S3 Access Point からレンダリング対象アセット（.exr, .dpx, .tga, .obj,
.fbx, .blend 等）を検出し、Manifest JSON を生成して S3 AP に書き出す。

Step Functions ワークフローの最初のステップとして実行され、
後続の Map ステート（Job Submit → Quality Check）にアセット一覧を渡す。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用、省略時は S3_ACCESS_POINT を使用)
    PREFIX_FILTER: プレフィックスフィルタ (optional)
    SUFFIX_FILTER: 検出対象の拡張子。カンマ区切り (optional)
        未設定または実質空の場合は RENDER_ASSET_EXTENSIONS を使用する。
        ドットの有無・大文字・空白は正規化される（"exr, DPX" は ".exr,.dpx"）。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.suffix_filter import allowed_suffixes

logger = logging.getLogger(__name__)

# レンダリング対象アセットの拡張子一覧
#
# AWS Deadline Cloud が submitter を提供する DCC と、そのシーン/プロジェクト
# ファイル形式を基準に列挙する。対応 DCC の一覧は AWS の公開情報を参照:
# https://aws.amazon.com/deadline-cloud/features/
# https://docs.aws.amazon.com/deadline-cloud/latest/developerguide/code-examples.html
#
# 汎用ラスター形式（.png / .jpg / .jpeg）は意図的に含めない。サムネイルや参考画像
# まで検出対象に入り、レンダリングジョブとして投入されてしまう。プレート形式は
# VFX パイプラインで実際に使われる .exr / .dpx / .tga に限定する。

# DCC のシーン / プロジェクトファイル（Deadline Cloud の submitter 対象）
DCC_SCENE_EXTENSIONS = (
    ".ma",  # Autodesk Maya (ASCII)
    ".mb",  # Autodesk Maya (binary)
    ".max",  # Autodesk 3ds Max
    ".blend",  # Blender
    ".hip",  # SideFX Houdini
    ".hipnc",  # Houdini (non-commercial)
    ".hiplc",  # Houdini (indie)
    ".hda",  # Houdini Digital Asset
    ".c4d",  # Maxon Cinema 4D
    ".nk",  # Foundry Nuke
    ".aep",  # Adobe After Effects
    ".bip",  # Luxion KeyShot
    ".ksp",  # Luxion KeyShot package
    ".uproject",  # Unreal Engine
    ".umap",  # Unreal Engine level
    ".vpb",  # Autodesk VRED
)

# レンダラーのシーン記述ファイル
RENDERER_SCENE_EXTENSIONS = (
    ".ass",  # Autodesk Arnold scene source
    ".vrscene",  # Chaos V-Ray
)

# ジオメトリ / シーン交換形式
INTERCHANGE_EXTENSIONS = (
    ".obj",
    ".fbx",
    ".abc",  # Alembic
    ".usd",
    ".usda",
    ".usdc",
    ".usdz",
)

# プレート / 画像シーケンス形式
PLATE_EXTENSIONS = (
    ".exr",
    ".dpx",
    ".tga",
)

# 映像コンテナ。コンポジット入力や納品素材として Deadline Cloud のワークフローに
# 入るため対象に含める（FPolicy イベント側の起動条件とも揃える）。
VIDEO_EXTENSIONS = (
    ".mov",
    ".mp4",
    ".mxf",
)

RENDER_ASSET_EXTENSIONS = (
    DCC_SCENE_EXTENSIONS + RENDERER_SCENE_EXTENSIONS + INTERCHANGE_EXTENSIONS + PLATE_EXTENSIONS + VIDEO_EXTENSIONS
)


def _allowed_extensions() -> tuple[str, ...]:
    """検出対象の拡張子を決める

    `SUFFIX_FILTER` が設定されていればそれを使い、未設定または実質空なら
    `RENDER_ASSET_EXTENSIONS` を使う。正規化の詳細は
    `shared/suffix_filter.py` を参照。

    Returns:
        tuple[str, ...]: 検出対象の拡張子
    """
    return allowed_suffixes(RENDER_ASSET_EXTENSIONS)


def _filter_render_assets(objects: list[dict], extensions: tuple[str, ...] | None = None) -> list[dict]:
    """レンダリング対象アセットのみをフィルタリングする

    Args:
        objects: S3ApHelper.list_objects() の結果リスト
        extensions: 対象拡張子。省略時は `RENDER_ASSET_EXTENSIONS`

    Returns:
        list[dict]: 対象拡張子に一致するオブジェクトのみ
    """
    allowed = extensions if extensions is not None else RENDER_ASSET_EXTENSIONS
    return [obj for obj in objects if any(obj["Key"].lower().endswith(ext) for ext in allowed)]


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Media VFX Discovery Lambda

    S3 AP からオブジェクト一覧を取得し、レンダリング対象アセットを
    フィルタリングして Manifest JSON を生成・S3 に書き出す。

    Returns:
        dict: manifest_bucket, manifest_key, total_objects, objects
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"]))
    prefix = os.environ.get("PREFIX_FILTER", "")
    extensions = _allowed_extensions()

    logger.info(
        "Media VFX Discovery started: access_point=%s, prefix=%r, extensions=%s",
        os.environ["S3_ACCESS_POINT"],
        prefix,
        ",".join(extensions),
    )

    # S3 AP からオブジェクト一覧取得
    all_objects = s3ap.list_objects(prefix=prefix)

    # レンダリング対象アセットのみフィルタリング
    render_assets = _filter_render_assets(all_objects, extensions)

    logger.info(
        "Render assets found: total_scanned=%d, render_assets=%d",
        len(all_objects),
        len(render_assets),
    )

    # Manifest 生成
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_objects": len(render_assets),
        "objects": render_assets,
    }

    # Manifest を S3 AP に書き出し
    manifest_key = f"manifests/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{context.aws_request_id}.json"

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

    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "media-vfx"))
    metrics.put_metric("FilesProcessed", float(len(render_assets)), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(render_assets),
        "objects": render_assets,
    }
