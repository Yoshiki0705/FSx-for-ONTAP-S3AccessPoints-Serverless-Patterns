"""保険 / 損害査定 Discovery Lambda ハンドラ

共通 Discovery Lambda パターンを継承し、事故写真と見積書を検出する。
S3 Access Point からオブジェクト一覧を取得し、事故写真 (.jpg, .jpeg, .png)
と見積書 (.pdf, .tiff) をサフィックスフィルタで抽出する。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    PREFIX_FILTER: プレフィックスフィルタ (optional)
    SUFFIX_FILTER: サフィックスフィルタ (optional, デフォルト: .jpg,.jpeg,.png,.pdf,.tiff)
    ONTAP_SECRET_NAME: ONTAP 認証情報の Secret 名
    ONTAP_MANAGEMENT_IP: ONTAP 管理 IP
    SVM_UUID: SVM UUID
    LOG_PII_DATA: PII データのログ出力 (デフォルト: false)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from shared.exceptions import lambda_error_handler
from shared.ontap_client import OntapClient, OntapClientConfig
from shared.s3ap_helper import S3ApHelper
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)

DEFAULT_SUFFIXES = [".jpg", ".jpeg", ".png", ".pdf", ".tiff"]
PHOTO_SUFFIXES = [".jpg", ".jpeg", ".png"]
ESTIMATE_SUFFIXES = [".pdf", ".tiff"]


def sanitize_for_logging(data: dict) -> dict:
    """PII データをログ出力用にサニタイズする

    Args:
        data: ログ出力対象のデータ

    Returns:
        dict: サニタイズされたデータ
    """
    log_pii = os.environ.get("LOG_PII_DATA", "false").lower() == "true"
    if log_pii:
        return data

    sanitized = {}
    pii_fields = {"name", "address", "phone", "email", "policy_number", "claimant"}
    for key, value in data.items():
        if any(pii in key.lower() for pii in pii_fields):
            sanitized[key] = "***REDACTED***"
        else:
            sanitized[key] = value
    return sanitized


def _collect_ontap_metadata(ontap_client: OntapClient, svm_uuid: str) -> dict:
    """ONTAP メタデータを収集する"""
    metadata: dict = {}
    try:
        volumes = ontap_client.list_volumes(svm_uuid=svm_uuid)
        metadata["volume_info"] = volumes
        if volumes:
            nas_info = volumes[0].get("nas", {})
            metadata["security_style"] = nas_info.get("security_style", "unknown")
        else:
            metadata["security_style"] = "unknown"
    except Exception as e:
        logger.warning("Failed to collect volume info: %s", e)
        metadata["volume_info"] = []
        metadata["security_style"] = "unknown"
    return metadata


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """保険 / 損害査定 Discovery Lambda

    S3 AP から事故写真 (.jpg, .jpeg, .png) と見積書 (.pdf, .tiff) の一覧を取得し、
    ONTAP メタデータを収集して Manifest JSON を生成・S3 に書き出す。

    Returns:
        dict: manifest_key, total_objects, photo_objects, estimate_objects, metadata
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"])
    )
    prefix = os.environ.get("PREFIX_FILTER", "")
    suffix_env = os.environ.get("SUFFIX_FILTER", "")

    if suffix_env:
        suffixes = [s.strip() for s in suffix_env.split(",") if s.strip()]
    else:
        suffixes = DEFAULT_SUFFIXES

    logger.info(
        "Insurance Claims Discovery started: access_point=%s, prefix=%r",
        os.environ["S3_ACCESS_POINT"],
        prefix,
    )

    # S3 AP からオブジェクト一覧取得
    all_objects: list[dict] = []
    for suffix in suffixes:
        with xray_subsegment(

            name="s3ap_list_objects",

            annotations={"service_name": "s3", "operation": "ListObjectsV2", "use_case": "insurance-claims"},

        ):

            objects = s3ap.list_objects(prefix=prefix, suffix=suffix)
        all_objects.extend(objects)

    # 重複排除
    seen_keys: set[str] = set()
    unique_objects: list[dict] = []
    for obj in all_objects:
        if obj["Key"] not in seen_keys:
            seen_keys.add(obj["Key"])
            unique_objects.append(obj)

    # 事故写真と見積書を分類
    photo_objects = [
        obj for obj in unique_objects
        if obj["Key"].lower().endswith(tuple(PHOTO_SUFFIXES))
    ]
    estimate_objects = [
        obj for obj in unique_objects
        if obj["Key"].lower().endswith(tuple(ESTIMATE_SUFFIXES))
    ]

    # ONTAP メタデータ収集
    verify_ssl = os.environ.get("VERIFY_SSL", "true").lower() != "false"
    ontap_config = OntapClientConfig(
        management_ip=os.environ["ONTAP_MANAGEMENT_IP"],
        secret_name=os.environ["ONTAP_SECRET_NAME"],
        verify_ssl=verify_ssl,
    )
    ontap_client = OntapClient(ontap_config)
    svm_uuid = os.environ["SVM_UUID"]
    metadata = _collect_ontap_metadata(ontap_client, svm_uuid)

    # Manifest 生成
    now = datetime.now(timezone.utc)
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": now.isoformat(),
        "total_objects": len(unique_objects),
        "photo_objects": photo_objects,
        "estimate_objects": estimate_objects,
        "objects": unique_objects,
        "metadata": metadata,
    }

    manifest_key = (
        f"manifests/{now.strftime('%Y/%m/%d')}"
        f"/{context.aws_request_id}.json"
    )

    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    logger.info(
        "Insurance Claims Discovery completed: total=%d, photos=%d, estimates=%d",
        len(unique_objects),
        len(photo_objects),
        len(estimate_objects),
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "insurance-claims"))
    metrics.put_metric("FilesProcessed", float(len(objects)), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(unique_objects),
        "photo_objects": photo_objects,
        "estimate_objects": estimate_objects,
        "objects": unique_objects,
        "metadata": metadata,
    }
