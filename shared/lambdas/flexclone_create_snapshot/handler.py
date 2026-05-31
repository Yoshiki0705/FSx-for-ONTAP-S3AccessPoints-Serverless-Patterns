"""shared.lambdas.flexclone_create_snapshot.handler — Create ONTAP Snapshot

ONTAP REST API を使用してボリュームスナップショットを作成する Lambda ハンドラー。
FlexClone 作成の前段として、一貫性のあるポイントインタイムコピーを確保する。

VPC 内で実行（ONTAP 管理 LIF へのアクセスに必要）。

ユースケース:
- レンダリング完了後のフレームスナップショット（メディア/VFX）
- シミュレーション前のデザインライブラリ保存（半導体 EDA）
- 四半期監査用ポイントインタイムコピー（金融）
- 臨床研究用リファレンスデータセット保存（ヘルスケア）

Input:
    {
        "volume_uuid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        "snapshot_name": "render_complete_20260518"
    }

Output:
    {
        "snapshot_name": "render_complete_20260518",
        "snapshot_uuid": "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy",
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
    """ONTAP ボリュームスナップショットを作成する。

    Args:
        event: Lambda イベント
            - volume_uuid: スナップショット対象ボリュームの UUID
            - snapshot_name: 作成するスナップショット名
        context: Lambda コンテキスト

    Returns:
        スナップショット作成結果

    Raises:
        ValueError: 必須パラメータが不足している場合
        RuntimeError: ONTAP API 呼び出しに失敗した場合
    """
    volume_uuid = event.get("volume_uuid")
    snapshot_name = event.get("snapshot_name")

    if not volume_uuid:
        raise ValueError("volume_uuid is required")
    if not snapshot_name:
        raise ValueError("snapshot_name is required")

    mgmt_ip = os.environ["ONTAP_MGMT_IP"]
    creds = get_ontap_credentials()

    logger.info(
        "Creating snapshot '%s' on volume %s",
        snapshot_name,
        volume_uuid,
    )

    # ONTAP REST API: POST /api/storage/volumes/{uuid}/snapshots
    headers = urllib3.make_headers(basic_auth=f"{creds['username']}:{creds['password']}")
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "application/json"

    body = {"name": snapshot_name}

    url = f"https://{mgmt_ip}/api/storage/volumes/{volume_uuid}/snapshots"
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
            "Snapshot creation failed: status=%d, body=%s",
            resp.status,
            error_detail,
        )
        raise RuntimeError(f"ONTAP API error (status {resp.status}): {error_detail}")

    result = json.loads(resp.data.decode("utf-8"))
    snapshot_uuid = result.get("uuid", "")

    # ONTAP の非同期ジョブの場合、records から UUID を取得
    if not snapshot_uuid and "records" in result:
        records = result["records"]
        if records:
            snapshot_uuid = records[0].get("uuid", "")

    # job レスポンスの場合
    if not snapshot_uuid and "job" in result:
        snapshot_uuid = result["job"].get("uuid", "pending")

    logger.info(
        "Snapshot created: name=%s, uuid=%s",
        snapshot_name,
        snapshot_uuid,
    )

    return {
        "snapshot_name": snapshot_name,
        "snapshot_uuid": snapshot_uuid,
        "status": "created",
    }
