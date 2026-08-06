"""医療 DICOM Discovery Lambda ハンドラ

S3 Access Point から DICOM ファイル（.dcm）を検出し、
Manifest JSON を生成して S3 AP に書き出す。

Step Functions ワークフローの最初のステップとして実行され、
後続の Map ステート（DICOM Parse → PII Detection → Anonymization）に
ファイル一覧を渡す。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用、省略時は S3_ACCESS_POINT を使用)
    PREFIX_FILTER: プレフィックスフィルタ (optional)
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

# DICOM ファイルのサフィックス
DICOM_SUFFIX = ".dcm"


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Healthcare DICOM Discovery Lambda

    S3 AP からオブジェクト一覧を取得し、.dcm ファイルのみを
    フィルタリングして Manifest JSON を生成・S3 に書き出す。

    Returns:
        dict: manifest_bucket, manifest_key, total_objects, objects
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"]))
    prefix = os.environ.get("PREFIX_FILTER", "")

    logger.info(
        "Healthcare DICOM Discovery started: access_point=%s, prefix=%r",
        os.environ["S3_ACCESS_POINT"],
        prefix,
    )

    # S3 AP から対象ファイル一覧取得（サフィックスフィルタ適用）
    #
    # 変数名を dicom_objects のまま保つのは意図的。この下のメトリクスと戻り値が
    # これを参照しているため、ループ内の一時変数を別名で持つと「最後の 1 種の件数」
    # を報告する取り違えが起きる（他の 11 パターンで実際に起きていた）。
    suffixes = allowed_suffixes((DICOM_SUFFIX,))
    seen_keys: set[str] = set()
    dicom_objects: list[dict] = []
    for suffix in suffixes:
        for obj in s3ap.list_objects(prefix=prefix, suffix=suffix):
            if obj["Key"] not in seen_keys:
                seen_keys.add(obj["Key"])
                dicom_objects.append(obj)

    logger.info(
        "DICOM files found: total=%d",
        len(dicom_objects),
    )

    # Manifest 生成
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_objects": len(dicom_objects),
        "objects": dicom_objects,
    }

    # Manifest を S3 AP に書き出し
    manifest_key = f"manifests/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{context.aws_request_id}.json"

    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    logger.info(
        "Healthcare DICOM Discovery completed: total_objects=%d, manifest=%s",
        len(dicom_objects),
        manifest_key,
    )

    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "healthcare-dicom"))
    metrics.put_metric("FilesProcessed", float(len(dicom_objects)), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(dicom_objects),
        "objects": dicom_objects,
    }
