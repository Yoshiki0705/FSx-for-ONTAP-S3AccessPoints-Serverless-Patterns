"""UC15 Defense/Space Discovery Lambda

FSx ONTAP S3 Access Point から衛星画像ファイル（GeoTIFF/NITF/HDF5）の
一覧を取得し、Manifest JSON を生成・S3 に書き出す。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    PREFIX_FILTER: プレフィックスフィルタ (optional、デフォルト: "satellite/")
    SUFFIX_FILTER: サフィックスフィルタ (default: ".tif,.tiff,.ntf,.nitf,.hdf,.h5")
    ONTAP_SECRET_NAME: ONTAP Secret 名 (optional)
    ONTAP_MANAGEMENT_IP: ONTAP 管理 IP (optional)
    SVM_UUID: SVM UUID (optional)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)

# サポート対象の衛星画像フォーマット
SUPPORTED_FORMATS = frozenset({".tif", ".tiff", ".ntf", ".nitf", ".hdf", ".h5"})


def _classify_image_type(key: str) -> str:
    """ファイル拡張子から画像タイプを分類する。

    Args:
        key: S3 オブジェクトキー

    Returns:
        str: "optical" (GeoTIFF/NITF) | "sar" (HDF5) | "unknown"
    """
    lower = key.lower()
    if lower.endswith((".tif", ".tiff", ".ntf", ".nitf")):
        return "optical"
    if lower.endswith((".hdf", ".h5")):
        return "sar"
    return "unknown"


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC15 Discovery Lambda ハンドラ。

    Returns:
        dict: manifest_key, total_objects, objects, image_types (分類別カウント)
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"])
    )
    prefix = os.environ.get("PREFIX_FILTER", "satellite/")
    suffix_filter = os.environ.get(
        "SUFFIX_FILTER", ",".join(sorted(SUPPORTED_FORMATS))
    )

    logger.info(
        "UC15 Discovery started: access_point=%s, prefix=%r, suffix=%r",
        os.environ["S3_ACCESS_POINT"],
        prefix,
        suffix_filter,
    )

    with xray_subsegment(
        name="s3ap_list_objects",
        annotations={
            "service_name": "s3",
            "operation": "ListObjectsV2",
            "use_case": "defense-satellite",
        },
    ):
        # S3ApHelper.list_objects は単一 suffix しか受け付けないので複数形式を取得
        all_objects = []
        for single_suffix in suffix_filter.split(","):
            single_suffix = single_suffix.strip()
            if single_suffix:
                all_objects.extend(
                    s3ap.list_objects(prefix=prefix, suffix=single_suffix)
                )

    # 重複除外（同じキーが複数回マッチする場合のため）
    seen_keys = set()
    objects = []
    for obj in all_objects:
        if obj["Key"] not in seen_keys:
            seen_keys.add(obj["Key"])
            obj["ImageType"] = _classify_image_type(obj["Key"])
            objects.append(obj)

    # 画像タイプ別のカウント
    image_types = {"optical": 0, "sar": 0, "unknown": 0}
    for obj in objects:
        image_types[obj["ImageType"]] += 1

    # Manifest 生成
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.utcnow().isoformat(),
        "total_objects": len(objects),
        "objects": objects,
        "image_types": image_types,
    }

    # S3 AP に書き出し
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
        "UC15 Discovery completed: total_objects=%d, optical=%d, sar=%d, manifest=%s",
        len(objects),
        image_types["optical"],
        image_types["sar"],
        manifest_key,
    )

    # EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", "defense-satellite")
    metrics.put_metric("FilesProcessed", float(len(objects)), "Count")
    metrics.put_metric("OpticalImages", float(image_types["optical"]), "Count")
    metrics.put_metric("SarImages", float(image_types["sar"]), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(objects),
        "objects": objects,
        "image_types": image_types,
    }
