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
from datetime import datetime

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

# DICOM ファイルのサフィックス
DICOM_SUFFIX = ".dcm"


@lambda_error_handler
def handler(event, context):
    """Healthcare DICOM Discovery Lambda

    S3 AP からオブジェクト一覧を取得し、.dcm ファイルのみを
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
        "Healthcare DICOM Discovery started: access_point=%s, prefix=%r",
        os.environ["S3_ACCESS_POINT"],
        prefix,
    )

    # S3 AP から .dcm ファイル一覧取得（サフィックスフィルタ適用）
    dicom_objects = s3ap.list_objects(prefix=prefix, suffix=DICOM_SUFFIX)

    logger.info(
        "DICOM files found: total=%d",
        len(dicom_objects),
    )

    # Manifest 生成
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.utcnow().isoformat(),
        "total_objects": len(dicom_objects),
        "objects": dicom_objects,
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
        "Healthcare DICOM Discovery completed: total_objects=%d, manifest=%s",
        len(dicom_objects),
        manifest_key,
    )

    return {
        "manifest_key": manifest_key,
        "total_objects": len(dicom_objects),
        "objects": dicom_objects,
    }
