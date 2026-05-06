"""法務・コンプライアンス Discovery Lambda ハンドラ

共通 Discovery Lambda パターンを拡張し、ONTAP メタデータ
（security style, export policies, CIFS share ACLs）の収集を追加する。

S3 Access Point からオブジェクト一覧を取得し、ONTAP REST API から
ボリューム・共有メタデータを収集して、Manifest JSON を生成する。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用、省略時は S3_ACCESS_POINT を使用)
    PREFIX_FILTER: プレフィックスフィルタ (optional)
    SUFFIX_FILTER: サフィックスフィルタ (optional)
    ONTAP_SECRET_NAME: ONTAP 認証情報の Secret 名
    ONTAP_MANAGEMENT_IP: ONTAP 管理 IP
    SVM_UUID: SVM UUID
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from shared.exceptions import lambda_error_handler
from shared.ontap_client import OntapClient, OntapClientConfig
from shared.s3ap_helper import S3ApHelper
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


def _collect_ontap_metadata(ontap_client: OntapClient, svm_uuid: str) -> dict:
    """ONTAP メタデータを収集する

    Args:
        ontap_client: OntapClient インスタンス
        svm_uuid: SVM UUID

    Returns:
        dict: ONTAP メタデータ（security_style, export_policies, cifs_shares, volume_info）
    """
    metadata: dict = {}

    try:
        # ボリューム情報取得
        volumes = ontap_client.list_volumes(svm_uuid=svm_uuid)
        metadata["volume_info"] = volumes

        # セキュリティスタイル取得（最初のボリュームから）
        if volumes:
            nas_info = volumes[0].get("nas", {})
            metadata["security_style"] = nas_info.get("security_style", "unknown")
        else:
            metadata["security_style"] = "unknown"

    except Exception as e:
        logger.warning("Failed to collect volume info: %s", e)
        metadata["volume_info"] = []
        metadata["security_style"] = "unknown"

    try:
        # NFS エクスポートポリシー取得
        export_policies = ontap_client.list_nfs_exports(svm_uuid)
        metadata["export_policies"] = export_policies
    except Exception as e:
        logger.warning("Failed to collect export policies: %s", e)
        metadata["export_policies"] = []

    try:
        # CIFS 共有 ACL 取得
        cifs_shares = ontap_client.list_cifs_shares(svm_uuid)
        metadata["cifs_shares"] = cifs_shares
    except Exception as e:
        logger.warning("Failed to collect CIFS shares: %s", e)
        metadata["cifs_shares"] = []

    return metadata


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Legal Compliance Discovery Lambda

    S3 AP からオブジェクト一覧を取得し、ONTAP メタデータを収集して
    Manifest JSON を生成・S3 に書き出す。

    Returns:
        dict: manifest_bucket, manifest_key, total_objects, metadata
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"])
    )
    prefix = os.environ.get("PREFIX_FILTER", "")
    suffix = os.environ.get("SUFFIX_FILTER", "")

    logger.info(
        "Legal Compliance Discovery started: access_point=%s, prefix=%r, suffix=%r",
        os.environ["S3_ACCESS_POINT"],
        prefix,
        suffix,
    )

    # S3 AP からオブジェクト一覧取得
    with xray_subsegment(

        name="s3ap_list_objects",

        annotations={"service_name": "s3", "operation": "ListObjectsV2", "use_case": "legal-compliance"},

    ):

        objects = s3ap.list_objects(prefix=prefix, suffix=suffix)

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
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.utcnow().isoformat(),
        "total_objects": len(objects),
        "objects": objects,
        "metadata": metadata,
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
        "Legal Compliance Discovery completed: total_objects=%d, manifest=%s",
        len(objects),
        manifest_key,
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "legal-compliance"))
    metrics.put_metric("FilesProcessed", float(len(objects)), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(objects),
        "objects": objects,
        "metadata": metadata,
    }
