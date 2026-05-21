"""shared.lambdas.flexclone_create_clone.handler — Create FlexClone Volume

ONTAP REST API を使用して FlexClone ボリュームを作成する Lambda ハンドラー。
親ボリュームのスナップショットから瞬時に書き込み可能なクローンを作成する。

VPC 内で実行（ONTAP 管理 LIF へのアクセスに必要）。

FlexClone の特徴:
- データコピーなし（メタデータのみ）で瞬時に作成（< 1 秒）
- 親ボリュームと共通ブロックを共有（容量効率）
- 独立した書き込み可能ボリューム（CoW: Copy-on-Write）
- NFS/SMB/S3AP 全プロトコルでアクセス可能

ユースケース:
- レンダリング QC 用即時コピー（メディア/VFX）
- 並列シミュレーション用デザインライブラリ分岐（半導体 EDA）
- 研究者別リファレンスデータセット分岐（ゲノミクス）
- 監査用ポイントインタイムコピー（金融）
- 臨床研究用 DICOM データセット分離（ヘルスケア）

Input:
    {
        "parent_volume_uuid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        "snapshot_name": "render_complete_20260518",
        "clone_name": "render_qc_shot001",
        "junction_path": "/render_qc/shot001",
        "security_style": "unix"
    }

Output:
    {
        "clone_name": "render_qc_shot001",
        "clone_uuid": "zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz",
        "junction_path": "/render_qc/shot001",
        "status": "created"
    }
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3
import urllib3

# TLS 検証を無効化（ONTAP 自己署名証明書対応）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
http = urllib3.PoolManager(cert_reqs="CERT_NONE")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def get_ontap_credentials() -> dict[str, str]:
    """Secrets Manager から ONTAP 認証情報を取得する。

    Returns:
        {"username": str, "password": str}

    Raises:
        RuntimeError: シークレット取得に失敗した場合
    """
    secret_name = os.environ["ONTAP_CREDENTIALS_SECRET"]
    client = boto3.client("secretsmanager")
    try:
        response = client.get_secret_value(SecretId=secret_name)
        return json.loads(response["SecretString"])
    except Exception as e:
        logger.error("Failed to retrieve ONTAP credentials: %s", str(e))
        raise RuntimeError(f"Secrets Manager error: {e}") from e


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """FlexClone ボリュームを作成する。

    Args:
        event: Lambda イベント
            - parent_volume_uuid: クローン元ボリュームの UUID
            - snapshot_name: ベースとなるスナップショット名
            - clone_name: 作成するクローンボリューム名
            - junction_path: NAS ジャンクションパス
            - security_style: セキュリティスタイル（unix|ntfs、デフォルト: unix）
        context: Lambda コンテキスト

    Returns:
        FlexClone 作成結果

    Raises:
        ValueError: 必須パラメータが不足している場合
        RuntimeError: ONTAP API 呼び出しに失敗した場合
    """
    parent_volume_uuid = event.get("parent_volume_uuid")
    snapshot_name = event.get("snapshot_name")
    clone_name = event.get("clone_name")
    junction_path = event.get("junction_path")
    # NOTE: security_style is accepted as input for documentation purposes
    # but NOT passed to ONTAP REST API (FlexClone inherits from parent volume).
    # ONTAP 9.17.1 returns error 918247 if nas.security_style is specified.
    security_style = event.get("security_style", "unix")

    if not parent_volume_uuid:
        raise ValueError("parent_volume_uuid is required")
    if not snapshot_name:
        raise ValueError("snapshot_name is required")
    if not clone_name:
        raise ValueError("clone_name is required")
    if not junction_path:
        raise ValueError("junction_path is required")
    if security_style not in ("unix", "ntfs", "mixed"):
        raise ValueError(
            f"Invalid security_style: {security_style}. "
            "Must be 'unix', 'ntfs', or 'mixed'."
        )

    mgmt_ip = os.environ["ONTAP_MGMT_IP"]
    svm_uuid = os.environ["SVM_UUID"]
    creds = get_ontap_credentials()

    logger.info(
        "Creating FlexClone '%s' from volume %s (snapshot: %s, junction: %s)",
        clone_name,
        parent_volume_uuid,
        snapshot_name,
        junction_path,
    )

    # ONTAP REST API: POST /api/storage/volumes
    headers = urllib3.make_headers(
        basic_auth=f"{creds['username']}:{creds['password']}"
    )
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "application/json"

    body = {
        "name": clone_name,
        "svm": {"uuid": svm_uuid},
        "clone": {
            "parent_volume": {"uuid": parent_volume_uuid},
            "parent_snapshot": {"name": snapshot_name},
            "is_flexclone": True,
        },
        "nas": {
            "path": junction_path,
        },
    }

    url = f"https://{mgmt_ip}/api/storage/volumes"
    resp = http.request(
        "POST",
        url,
        body=json.dumps(body).encode("utf-8"),
        headers=headers,
        timeout=30.0,
    )

    if resp.status >= 400:
        error_detail = resp.data.decode("utf-8", errors="replace")
        logger.error(
            "FlexClone creation failed: status=%d, body=%s",
            resp.status,
            error_detail,
        )
        raise RuntimeError(
            f"ONTAP API error (status {resp.status}): {error_detail}"
        )

    result = json.loads(resp.data.decode("utf-8"))
    clone_uuid = result.get("uuid", "")

    # 非同期ジョブレスポンスの場合
    if not clone_uuid and "job" in result:
        clone_uuid = result["job"].get("uuid", "pending")

    logger.info(
        "FlexClone created: name=%s, uuid=%s, junction_path=%s",
        clone_name,
        clone_uuid,
        junction_path,
    )

    return {
        "clone_name": clone_name,
        "clone_uuid": clone_uuid,
        "junction_path": junction_path,
        "status": "created",
    }
