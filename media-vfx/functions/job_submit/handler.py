"""メディア VFX Job Submit Lambda ハンドラ

Map ステートからアセット情報を受け取り、S3ApHelper でアセットを取得し、
AWS Deadline Cloud にレンダリングジョブを送信する。
ジョブ ID とステータスを返す。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    DEADLINE_FARM_ID: AWS Deadline Cloud Farm ID
    DEADLINE_QUEUE_ID: AWS Deadline Cloud Queue ID
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

import boto3

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)


def _build_job_template(asset_key: str, output_bucket: str) -> dict:
    """Deadline Cloud ジョブテンプレートを構築する

    Args:
        asset_key: レンダリング対象アセットの S3 キー
        output_bucket: レンダリング出力先 S3 バケット名

    Returns:
        dict: Deadline Cloud CreateJob API 用のテンプレート
    """
    asset_name = asset_key.rsplit("/", 1)[-1]
    job_name = f"render-{asset_name}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    return {
        "name": job_name,
        "priority": 50,
        "parameters": {
            "asset_key": {"string": asset_key},
            "output_bucket": {"string": output_bucket},
            "asset_name": {"string": asset_name},
        },
    }


@lambda_error_handler
def handler(event, context):
    """Job Submit Lambda

    Map ステートからアセット情報を受け取り、S3ApHelper でアセットの
    メタデータを確認し、AWS Deadline Cloud にレンダリングジョブを送信する。

    Args:
        event: Map ステートからの入力。以下のキーを含む:
            - Key (str): アセットファイルの S3 キー
            - Size (int): ファイルサイズ

    Returns:
        dict: job_id, job_name, asset_key, status
    """
    asset_key = event["Key"]
    asset_size = event.get("Size", 0)

    logger.info(
        "Job Submit started: asset_key=%s, size=%d",
        asset_key,
        asset_size,
    )

    # S3 AP からアセットのメタデータを確認
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    head_response = s3ap.head_object(asset_key)

    logger.info(
        "Asset metadata confirmed: key=%s, content_length=%d, content_type=%s",
        asset_key,
        head_response.get("ContentLength", 0),
        head_response.get("ContentType", "unknown"),
    )

    # Deadline Cloud ジョブテンプレート構築
    output_ap = os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"])
    job_template = _build_job_template(asset_key, output_ap)

    # AWS Deadline Cloud にジョブ送信
    deadline_client = boto3.client("deadline")
    farm_id = os.environ["DEADLINE_FARM_ID"]
    queue_id = os.environ["DEADLINE_QUEUE_ID"]

    create_response = deadline_client.create_job(
        farmId=farm_id,
        queueId=queue_id,
        template=json.dumps(job_template),
        templateType="JSON",
        priority=job_template["priority"],
    )

    job_id = create_response["jobId"]

    logger.info(
        "Rendering job submitted: job_id=%s, farm_id=%s, queue_id=%s, asset=%s",
        job_id,
        farm_id,
        queue_id,
        asset_key,
    )

    return {
        "job_id": job_id,
        "job_name": job_template["name"],
        "asset_key": asset_key,
        "output_ap": output_ap,
        "farm_id": farm_id,
        "queue_id": queue_id,
        "submitted_at": datetime.utcnow().isoformat(),
        "status": "SUBMITTED",
    }
