"""法務・コンプライアンス ACL Collection Lambda ハンドラ

Step Functions Map ステートからオブジェクト情報を受け取り、
ONTAP REST API 経由で NTFS ACL 情報を取得する。
取得した ACL データを JSON Lines 形式で日付パーティション付き S3 AP に出力する。

ONTAP API 失敗時はエラーをログに記録し、オブジェクトを失敗としてマークする。
ワークフロー全体は停止しない。

Environment Variables:
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    ONTAP_SECRET_NAME: ONTAP 認証情報の Secret 名
    ONTAP_MANAGEMENT_IP: ONTAP 管理 IP
    SVM_UUID: SVM UUID
    VOLUME_UUID: ボリューム UUID
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from shared.exceptions import lambda_error_handler
from shared.ontap_client import OntapClient, OntapClientConfig, OntapClientError
from shared.s3ap_helper import S3ApHelper
from shared.observability import trace_lambda_handler

logger = logging.getLogger(__name__)


def format_acl_record(
    object_key: str,
    volume_uuid: str,
    security_style: str,
    acls: list[dict],
) -> str:
    """ACL データを JSON Lines レコードにフォーマットする

    プロパティテストで直接テスト可能なヘルパー関数。

    Args:
        object_key: S3 オブジェクトキー
        volume_uuid: ONTAP ボリューム UUID
        security_style: セキュリティスタイル (ntfs, unix, mixed)
        acls: ACL エントリのリスト

    Returns:
        str: JSON Lines 形式の1行（改行なし）
    """
    record = {
        "object_key": object_key,
        "volume_uuid": volume_uuid,
        "security_style": security_style,
        "acls": acls,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
    return json.dumps(record, default=str)


def build_s3_key(execution_id: str) -> str:
    """日付パーティション付き S3 キーを生成する

    Args:
        execution_id: Lambda 実行 ID

    Returns:
        str: S3 キー (例: acl-data/2026/01/15/{execution_id}.jsonl)
    """
    now = datetime.now(timezone.utc)
    date_partition = now.strftime("%Y/%m/%d")
    return f"acl-data/{date_partition}/{execution_id}.jsonl"


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """ACL Collection Lambda

    Step Functions Map ステートから呼び出される。
    各オブジェクトの NTFS ACL 情報を ONTAP REST API から取得し、
    JSON Lines 形式で S3 に出力する。

    Args:
        event: Map ステートからのオブジェクト情報
            {"Key": str, "Size": int, "LastModified": str, "ETag": str}

    Returns:
        dict: status, object_key, s3_output_key (成功時)
              status, object_key, error (失敗時)
    """
    object_key = event["Key"]
    svm_uuid = os.environ["SVM_UUID"]
    volume_uuid = os.environ["VOLUME_UUID"]

    logger.info("ACL Collection started for object: %s", object_key)

    # S3 AP 出力ヘルパー初期化
    s3ap_output = S3ApHelper(os.environ["S3_ACCESS_POINT_OUTPUT"])

    # ONTAP クライアント初期化
    verify_ssl = os.environ.get("VERIFY_SSL", "true").lower() != "false"
    ontap_config = OntapClientConfig(
        management_ip=os.environ["ONTAP_MANAGEMENT_IP"],
        secret_name=os.environ["ONTAP_SECRET_NAME"],
        verify_ssl=verify_ssl,
    )
    ontap_client = OntapClient(ontap_config)

    try:
        # NTFS ACL 情報取得
        security_info = ontap_client.get_file_security(
            svm_uuid=svm_uuid,
            volume_uuid=volume_uuid,
            path=object_key,
        )

        security_style = security_info.get("security_style", "unknown")
        acls = security_info.get("acls", [])

        # JSON Lines レコード生成
        record_line = format_acl_record(
            object_key=object_key,
            volume_uuid=volume_uuid,
            security_style=security_style,
            acls=acls,
        )

        # S3 AP に出力（日付パーティション付き）
        s3_key = build_s3_key(context.aws_request_id)

        s3ap_output.put_object(
            key=s3_key,
            body=record_line + "\n",
            content_type="application/x-ndjson",
        )

        logger.info(
            "ACL Collection completed: object=%s, output=%s",
            object_key,
            s3_key,
        )

        return {
            "status": "SUCCESS",
            "object_key": object_key,
            "s3_output_key": s3_key,
        }

    except OntapClientError as e:
        # ONTAP API 失敗: ログ記録し、失敗マーク。ワークフローは停止しない。
        logger.error(
            "ONTAP API failure for object %s: %s (status_code=%s)",
            object_key,
            str(e),
            getattr(e, "status_code", None),
        )
        return {
            "status": "FAILED",
            "object_key": object_key,
            "error": str(e),
        }
