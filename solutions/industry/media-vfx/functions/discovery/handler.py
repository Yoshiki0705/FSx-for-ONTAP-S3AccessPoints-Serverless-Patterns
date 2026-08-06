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


def _parse_suffix_filter(raw: str) -> tuple[str, ...]:
    """`SUFFIX_FILTER` の値を拡張子タプルに変換する

    運用者が編集する値なので、書き方の揺れを吸収する。ドットの有無・大文字・
    余分な空白のいずれかで無言の不一致（何も検出しない、あるいは一部だけ検出する）
    が起きると、原因の分かりにくい取りこぼしになる。

    Args:
        raw: カンマ区切りの拡張子。例: ".exr, .dpx" / "exr,DPX"

    Returns:
        tuple[str, ...]: 正規化した拡張子。有効な項目が無ければ空タプル
    """
    extensions = []
    for token in raw.split(","):
        ext = token.strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = f".{ext}"
        if ext not in extensions:
            extensions.append(ext)
    return tuple(extensions)


def _allowed_extensions() -> tuple[str, ...]:
    """検出対象の拡張子を決める

    `SUFFIX_FILTER` が設定されていればそれを使い、未設定または実質空なら
    `RENDER_ASSET_EXTENSIONS` を使う。

    フォールバックを残すのは、環境変数の欠落や打ち間違いで空になったときに
    「1 件も検出せず成功を返す」状態にしないため。対象を絞りたい場合は
    `SUFFIX_FILTER` に明示的に列挙する。

    Returns:
        tuple[str, ...]: 検出対象の拡張子
    """
    configured = _parse_suffix_filter(os.environ.get("SUFFIX_FILTER", ""))
    return configured or RENDER_ASSET_EXTENSIONS


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
