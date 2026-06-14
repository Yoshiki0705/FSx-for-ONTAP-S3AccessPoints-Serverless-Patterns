"""FlexClone Manager — ONTAP REST API で FlexClone を作成・削除する Lambda。

EBS Volume Clones と同様の即時コピー体験を提供するが、以下の点で差別化:
- スペース効率: 変更ブロックのみ消費（EBS Clone はフルコピー）
- S3 API アクセス: S3 Access Point 経由でサーバーレスアクセス可能
- クロス AZ: EBS Clone は same-AZ 制約あり、S3AP は VPC 外からもアクセス可能

Usage:
    Event Types:
    - CREATE: FlexClone を作成し、S3AP alias を返す
    - DELETE: 指定 FlexClone を削除
    - STATUS: FlexClone の状態を返す

Environment Variables:
    ONTAP_MANAGEMENT_IP: ONTAP クラスタ管理 IP
    ONTAP_SECRET_NAME: Secrets Manager シークレット名
    SVM_NAME: SVM 名
    CLONE_PREFIX: FlexClone ボリューム名プレフィックス
    SIMULATION_MODE: "true" の場合、ONTAP API を呼ばずシミュレーション
"""

import json
import logging
import os
import time
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
    """FlexClone lifecycle management handler.

    Args:
        event: {
            "action": "CREATE" | "DELETE" | "STATUS",
            "source_volume": "production_data",  # CREATE のみ
            "clone_name": "devtest_clone_20260607",  # DELETE/STATUS のみ
            "requester": "ci-pipeline-abc",  # 任意
            "ttl_hours": 24  # CREATE のみ（オプション）
        }
    """
    action = event.get("action", "CREATE").upper()
    timestamp = datetime.now(timezone.utc).isoformat()

    logger.info(json.dumps({
        "event": "flexclone_request",
        "action": action,
        "timestamp": timestamp,
        "simulation_mode": SIMULATION_MODE,
    }))

    if action == "CREATE":
        return _create_clone(event, timestamp)
    elif action == "DELETE":
        return _delete_clone(event, timestamp)
    elif action == "STATUS":
        return _get_status(event, timestamp)
    else:
        return {"status": "error", "message": f"Unknown action: {action}"}


def _create_clone(event: dict, timestamp: str) -> dict:
    """FlexClone を作成する。"""
    source_volume = event.get("source_volume", "")
    if not source_volume:
        return {"status": "error", "message": "source_volume is required for CREATE"}

    ttl_hours = event.get("ttl_hours", TTL_HOURS)
    requester = event.get("requester", "unknown")
    clone_name = f"{CLONE_PREFIX}_{int(time.time())}"

    if SIMULATION_MODE:
        logger.info(f"[SIMULATION] Would create FlexClone: {clone_name} from {source_volume}")
        return {
            "status": "success",
            "action": "CREATE",
            "clone_name": clone_name,
            "source_volume": source_volume,
            "svm": SVM_NAME,
            "junction_path": f"/{clone_name}",
            "ttl_hours": ttl_hours,
            "expires_at": f"(now + {ttl_hours}h)",
            "requester": requester,
            "timestamp": timestamp,
            "simulation": True,
        }

    # 実環境: ONTAP REST API 呼び出し
    credentials = _get_ontap_credentials()
    clone_result = _ontap_create_clone(
        management_ip=ONTAP_MANAGEMENT_IP,
        credentials=credentials,
        svm_name=SVM_NAME,
        source_volume=source_volume,
        clone_name=clone_name,
    )

    return {
        "status": "success",
        "action": "CREATE",
        "clone_name": clone_name,
        "source_volume": source_volume,
        "svm": SVM_NAME,
        "junction_path": f"/{clone_name}",
        "ontap_job_uuid": clone_result.get("job_uuid"),
        "ttl_hours": ttl_hours,
        "requester": requester,
        "timestamp": timestamp,
        "simulation": False,
    }


def _delete_clone(event: dict, timestamp: str) -> dict:
    """FlexClone を削除する。"""
    clone_name = event.get("clone_name", "")
    if not clone_name:
        return {"status": "error", "message": "clone_name is required for DELETE"}

    if SIMULATION_MODE:
        logger.info(f"[SIMULATION] Would delete FlexClone: {clone_name}")
        return {
            "status": "success",
            "action": "DELETE",
            "clone_name": clone_name,
            "timestamp": timestamp,
            "simulation": True,
        }

    credentials = _get_ontap_credentials()
    _ontap_delete_volume(
        management_ip=ONTAP_MANAGEMENT_IP,
        credentials=credentials,
        svm_name=SVM_NAME,
        volume_name=clone_name,
    )

    return {
        "status": "success",
        "action": "DELETE",
        "clone_name": clone_name,
        "timestamp": timestamp,
        "simulation": False,
    }


def _get_status(event: dict, timestamp: str) -> dict:
    """FlexClone の状態を取得する。"""
    clone_name = event.get("clone_name", "")
    if not clone_name:
        return {"status": "error", "message": "clone_name is required for STATUS"}

    if SIMULATION_MODE:
        return {
            "status": "success",
            "action": "STATUS",
            "clone_name": clone_name,
            "state": "online",
            "used_size_bytes": 0,
            "split_status": "not_split",
            "timestamp": timestamp,
            "simulation": True,
        }

    credentials = _get_ontap_credentials()
    vol_info = _ontap_get_volume(
        management_ip=ONTAP_MANAGEMENT_IP,
        credentials=credentials,
        svm_name=SVM_NAME,
        volume_name=clone_name,
    )

    return {
        "status": "success",
        "action": "STATUS",
        "clone_name": clone_name,
        "state": vol_info.get("state", "unknown"),
        "used_size_bytes": vol_info.get("space", {}).get("used", 0),
        "split_status": vol_info.get("clone", {}).get("split_status", "unknown"),
        "timestamp": timestamp,
        "simulation": False,
    }


def _get_ontap_credentials() -> dict:
    """Secrets Manager から ONTAP 認証情報を取得する。"""
    import boto3
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=ONTAP_SECRET_NAME)
    return json.loads(response["SecretString"])


def _ontap_create_clone(management_ip: str, credentials: dict, svm_name: str,
                        source_volume: str, clone_name: str) -> dict:
    """ONTAP REST API: POST /api/storage/volumes (clone)."""
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    url = f"https://{management_ip}/api/storage/volumes"
    payload = {
        "name": clone_name,
        "svm": {"name": svm_name},
        "clone": {
            "parent_volume": {"name": source_volume},
            "is_flexclone": True,
        },
        "nas": {"path": f"/{clone_name}"},
    }

    http = urllib3.PoolManager(cert_reqs="CERT_NONE")
    headers = urllib3.make_headers(basic_auth=f"{credentials['username']}:{credentials['password']}")
    headers["Content-Type"] = "application/json"

    response = http.request("POST", url, body=json.dumps(payload), headers=headers)
    result = json.loads(response.data.decode("utf-8"))

    if response.status not in (200, 201, 202):
        raise RuntimeError(f"ONTAP clone create failed: {response.status} {result}")

    return {"job_uuid": result.get("job", {}).get("uuid", "")}


def _ontap_delete_volume(management_ip: str, credentials: dict, svm_name: str,
                         volume_name: str) -> None:
    """ONTAP REST API: DELETE /api/storage/volumes/{uuid}."""
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # First get volume UUID
    url = f"https://{management_ip}/api/storage/volumes?name={volume_name}&svm.name={svm_name}"
    http = urllib3.PoolManager(cert_reqs="CERT_NONE")
    headers = urllib3.make_headers(basic_auth=f"{credentials['username']}:{credentials['password']}")

    response = http.request("GET", url, headers=headers)
    result = json.loads(response.data.decode("utf-8"))
    records = result.get("records", [])

    if not records:
        logger.warning(f"Volume {volume_name} not found — may already be deleted")
        return

    vol_uuid = records[0]["uuid"]

    # Offline then delete
    patch_url = f"https://{management_ip}/api/storage/volumes/{vol_uuid}"
    headers["Content-Type"] = "application/json"
    http.request("PATCH", patch_url, body=json.dumps({"state": "offline"}), headers=headers)

    delete_url = f"https://{management_ip}/api/storage/volumes/{vol_uuid}"
    http.request("DELETE", delete_url, headers=headers)


def _ontap_get_volume(management_ip: str, credentials: dict, svm_name: str,
                      volume_name: str) -> dict:
    """ONTAP REST API: GET /api/storage/volumes."""
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    url = (
        f"https://{management_ip}/api/storage/volumes"
        f"?name={volume_name}&svm.name={svm_name}"
        f"&fields=state,space,clone"
    )
    http = urllib3.PoolManager(cert_reqs="CERT_NONE")
    headers = urllib3.make_headers(basic_auth=f"{credentials['username']}:{credentials['password']}")

    response = http.request("GET", url, headers=headers)
    result = json.loads(response.data.decode("utf-8"))
    records = result.get("records", [])

    return records[0] if records else {}
