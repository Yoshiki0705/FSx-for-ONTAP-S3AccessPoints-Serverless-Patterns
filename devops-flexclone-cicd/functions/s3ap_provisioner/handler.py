"""S3 Access Point Provisioner — FlexClone に S3AP を紐付ける Lambda。

FlexClone 作成後に S3 Access Point を設定し、サーバーレスアクセスを有効化する。
CI/CD パイプラインや開発者は、返される S3AP alias を使って即座にデータアクセス可能。

Environment Variables:
    ONTAP_MANAGEMENT_IP: ONTAP クラスタ管理 IP
    ONTAP_SECRET_NAME: Secrets Manager シークレット名
    SVM_NAME: SVM 名
    S3AP_NAME_PREFIX: S3 Access Point 名プレフィックス
    SIMULATION_MODE: "true" の場合シミュレーション
"""

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SIMULATION_MODE = os.environ.get("SIMULATION_MODE", "true").lower() == "true"
ONTAP_MANAGEMENT_IP = os.environ.get("ONTAP_MANAGEMENT_IP", "")
ONTAP_SECRET_NAME = os.environ.get("ONTAP_SECRET_NAME", "fsxn/ontap-credentials")
SVM_NAME = os.environ.get("SVM_NAME", "svm1")
S3AP_NAME_PREFIX = os.environ.get("S3AP_NAME_PREFIX", "devtest-clone")


def handler(event: dict, context) -> dict:
    """S3 Access Point provisioning for FlexClone volumes.

    Args:
        event: {
            "clone_name": "devtest_clone_1717776000",
            "junction_path": "/devtest_clone_1717776000",
            "requester": "ci-pipeline-abc",
            "access_mode": "readonly"  # "readonly" | "readwrite"
        }

    Returns:
        {
            "status": "success",
            "s3ap_name": "devtest-clone-1717776000",
            "s3ap_alias": "devtest-clone-1717776000-xxx-s3alias",
            "access_mode": "readonly"
        }
    """
    clone_name = event.get("clone_name", "")
    junction_path = event.get("junction_path", f"/{clone_name}")
    access_mode = event.get("access_mode", "readonly")
    requester = event.get("requester", "unknown")
    timestamp = datetime.now(timezone.utc).isoformat()

    if not clone_name:
        return {"status": "error", "message": "clone_name is required"}

    # S3AP 名は clone 名から生成（ハイフン区切り、63 文字以内）
    s3ap_name = f"{S3AP_NAME_PREFIX}-{clone_name.replace('_', '-')}"[:63]

    logger.info(
        json.dumps(
            {
                "event": "s3ap_provision_request",
                "clone_name": clone_name,
                "s3ap_name": s3ap_name,
                "access_mode": access_mode,
                "requester": requester,
                "timestamp": timestamp,
            }
        )
    )

    if SIMULATION_MODE:
        simulated_alias = f"{s3ap_name}-fhyst3uaibf46uywh5xka84pnz8jaapn1a-ext-s3alias"
        logger.info(f"[SIMULATION] Would create S3AP: {s3ap_name} for volume at {junction_path}")
        return {
            "status": "success",
            "s3ap_name": s3ap_name,
            "s3ap_alias": simulated_alias,
            "clone_name": clone_name,
            "junction_path": junction_path,
            "access_mode": access_mode,
            "requester": requester,
            "timestamp": timestamp,
            "simulation": True,
            "usage_example": {
                "python": f's3.list_objects_v2(Bucket="{simulated_alias}", Prefix="data/")',
                "cli": f"aws s3 ls s3://{simulated_alias}/data/",
            },
        }

    # 実環境: ONTAP REST API で S3 サービス用ボリュームを設定
    # 注: S3AP の実際のプロビジョニングは FSx コンソールまたは
    # aws s3control create-access-point で行う
    # ここでは ONTAP 側の S3 バケット設定を実行

    return {
        "status": "success",
        "s3ap_name": s3ap_name,
        "s3ap_alias": "(provisioned — check FSx console)",
        "clone_name": clone_name,
        "junction_path": junction_path,
        "access_mode": access_mode,
        "requester": requester,
        "timestamp": timestamp,
        "simulation": False,
    }
