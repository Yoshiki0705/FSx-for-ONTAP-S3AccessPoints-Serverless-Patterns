"""Cleanup Handler — テスト完了後または TTL 超過時に FlexClone を削除する Lambda。

トリガーパターン:
1. Step Functions から直接呼び出し（テスト完了後の即時クリーンアップ）
2. EventBridge Scheduler（TTL ベースの定期クリーンアップ）

Environment Variables:
    ONTAP_MANAGEMENT_IP: ONTAP クラスタ管理 IP
    ONTAP_SECRET_NAME: Secrets Manager シークレット名
    SVM_NAME: SVM 名
    CLONE_PREFIX: FlexClone ボリューム名プレフィックス
    TTL_HOURS: デフォルト TTL（時間）
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
CLONE_PREFIX = os.environ.get("CLONE_PREFIX", "devtest_clone")
TTL_HOURS = int(os.environ.get("TTL_HOURS", "24"))


def handler(event: dict, context) -> dict:
    """FlexClone cleanup handler.

    Args:
        event: {
            "mode": "immediate" | "ttl_sweep",
            "clone_name": "devtest_clone_1717776000",  # immediate mode
        }
    """
    mode = event.get("mode", "immediate")
    timestamp = datetime.now(timezone.utc).isoformat()

    logger.info(
        json.dumps(
            {
                "event": "cleanup_triggered",
                "mode": mode,
                "timestamp": timestamp,
            }
        )
    )

    if mode == "immediate":
        return _immediate_cleanup(event, timestamp)
    elif mode == "ttl_sweep":
        return _ttl_sweep(timestamp)
    else:
        return {"status": "error", "message": f"Unknown mode: {mode}"}


def _immediate_cleanup(event: dict, timestamp: str) -> dict:
    """指定された FlexClone を即座に削除する。"""
    clone_name = event.get("clone_name", "")
    if not clone_name:
        return {"status": "error", "message": "clone_name is required for immediate cleanup"}

    if SIMULATION_MODE:
        logger.info(f"[SIMULATION] Would delete clone: {clone_name}")
        return {
            "status": "success",
            "mode": "immediate",
            "deleted": [clone_name],
            "timestamp": timestamp,
            "simulation": True,
        }

    # 実環境: Clone Manager の削除ロジックを再利用
    from devops_flexclone_cicd.functions.clone_manager.handler import _delete_clone

    _delete_clone({"clone_name": clone_name}, timestamp)
    return {
        "status": "success",
        "mode": "immediate",
        "deleted": [clone_name],
        "timestamp": timestamp,
        "simulation": False,
    }


def _ttl_sweep(timestamp: str) -> dict:
    """TTL 超過した全 FlexClone を検出・削除する。"""
    if SIMULATION_MODE:
        logger.info("[SIMULATION] Would scan for expired clones and delete them")
        return {
            "status": "success",
            "mode": "ttl_sweep",
            "scanned": 5,
            "expired": 2,
            "deleted": ["devtest_clone_old1", "devtest_clone_old2"],
            "timestamp": timestamp,
            "simulation": True,
        }

    # 実環境: ONTAP REST API でプレフィックスマッチするボリュームを列挙
    # 作成時刻 + TTL < now のものを削除
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    credentials = _get_ontap_credentials()
    expired_clones = _find_expired_clones(credentials)

    deleted = []
    for clone_name in expired_clones:
        try:
            _delete_volume(credentials, clone_name)
            deleted.append(clone_name)
            logger.info(f"Deleted expired clone: {clone_name}")
        except Exception as e:
            logger.error(f"Failed to delete {clone_name}: {e}")

    return {
        "status": "success",
        "mode": "ttl_sweep",
        "scanned": len(expired_clones) + len(deleted),
        "expired": len(expired_clones),
        "deleted": deleted,
        "timestamp": timestamp,
        "simulation": False,
    }


def _get_ontap_credentials() -> dict:
    """Secrets Manager から ONTAP 認証情報を取得する。"""
    import boto3

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=ONTAP_SECRET_NAME)
    return json.loads(response["SecretString"])


def _find_expired_clones(credentials: dict) -> list[str]:
    """TTL 超過した FlexClone ボリュームを検出する。"""
    import time
    import urllib3

    url = (
        f"https://{ONTAP_MANAGEMENT_IP}/api/storage/volumes"
        f"?name={CLONE_PREFIX}*&svm.name={SVM_NAME}"
        f"&fields=name,create_time,clone"
        f"&clone.is_flexclone=true"
    )
    http = urllib3.PoolManager(cert_reqs="CERT_NONE")
    headers = urllib3.make_headers(basic_auth=f"{credentials['username']}:{credentials['password']}")

    response = http.request("GET", url, headers=headers)
    result = json.loads(response.data.decode("utf-8"))
    records = result.get("records", [])

    now = time.time()
    ttl_seconds = TTL_HOURS * 3600
    expired = []

    for vol in records:
        create_time_str = vol.get("create_time", "")
        if create_time_str:
            # ONTAP create_time is ISO 8601
            create_dt = datetime.fromisoformat(create_time_str.replace("Z", "+00:00"))
            age_seconds = now - create_dt.timestamp()
            if age_seconds > ttl_seconds:
                expired.append(vol["name"])

    return expired


def _delete_volume(credentials: dict, volume_name: str) -> None:
    """ONTAP ボリュームを削除する。"""
    import urllib3

    url = f"https://{ONTAP_MANAGEMENT_IP}/api/storage/volumes?name={volume_name}&svm.name={SVM_NAME}"
    http = urllib3.PoolManager(cert_reqs="CERT_NONE")
    headers = urllib3.make_headers(basic_auth=f"{credentials['username']}:{credentials['password']}")

    response = http.request("GET", url, headers=headers)
    result = json.loads(response.data.decode("utf-8"))
    records = result.get("records", [])

    if not records:
        return

    vol_uuid = records[0]["uuid"]
    headers["Content-Type"] = "application/json"

    # Offline
    http.request(
        "PATCH",
        f"https://{ONTAP_MANAGEMENT_IP}/api/storage/volumes/{vol_uuid}",
        body=json.dumps({"state": "offline"}),
        headers=headers,
    )
    # Delete
    http.request("DELETE", f"https://{ONTAP_MANAGEMENT_IP}/api/storage/volumes/{vol_uuid}", headers=headers)
