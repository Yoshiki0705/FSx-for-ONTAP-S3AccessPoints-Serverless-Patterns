"""shared.lambdas.flexclone_create_cifs_share.handler — Create CIFS Share

ONTAP REST API を使用して FlexClone ボリュームに CIFS（SMB）共有を作成する Lambda ハンドラー。
Windows クライアントからのアクセスを可能にする。

VPC 内で実行（ONTAP 管理 LIF へのアクセスに必要）。

ユースケース:
- 監査チーム向け読み取り専用共有（金融 — NTFS ACL）
- アーティスト向けレビュー共有（メディア/VFX）
- 研究者向けデータセット共有（ヘルスケア）
- 設計レビュー用共有（半導体 EDA）

Input:
    {
        "svm_name": "svm1",
        "share_name": "audit_q2_2026",
        "junction_path": "/audit/q2_2026",
        "comment": "Q2 2026 Audit - Read Only"
    }

Output:
    {
        "share_name": "audit_q2_2026",
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


def _get_svm_uuid(mgmt_ip: str, headers: dict, svm_name: str) -> str:
    """SVM 名から UUID を取得する。

    Args:
        mgmt_ip: ONTAP 管理 IP
        headers: HTTP ヘッダー（認証情報含む）
        svm_name: SVM 名

    Returns:
        SVM UUID

    Raises:
        RuntimeError: SVM が見つからない場合
    """
    url = f"https://{mgmt_ip}/api/svm/svms?name={svm_name}"
    resp = http.request("GET", url, headers=headers, timeout=15.0)

    if resp.status >= 400:
        raise RuntimeError(f"Failed to query SVM: status {resp.status}")

    result = json.loads(resp.data.decode("utf-8"))
    records = result.get("records", [])

    if not records:
        raise RuntimeError(f"SVM '{svm_name}' not found")

    return records[0]["uuid"]


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """CIFS 共有を作成する。

    Args:
        event: Lambda イベント
            - svm_name: SVM 名
            - share_name: 作成する共有名
            - junction_path: 共有のジャンクションパス
            - comment: 共有のコメント（オプション）
        context: Lambda コンテキスト

    Returns:
        CIFS 共有作成結果

    Raises:
        ValueError: 必須パラメータが不足している場合
        RuntimeError: ONTAP API 呼び出しに失敗した場合
    """
    svm_name = event.get("svm_name")
    share_name = event.get("share_name")
    junction_path = event.get("junction_path")
    comment = event.get("comment", "")

    if not svm_name:
        raise ValueError("svm_name is required")
    if not share_name:
        raise ValueError("share_name is required")
    if not junction_path:
        raise ValueError("junction_path is required")

    mgmt_ip = os.environ["ONTAP_MGMT_IP"]
    creds = get_ontap_credentials()

    logger.info(
        "Creating CIFS share '%s' on SVM '%s' (path: %s)",
        share_name,
        svm_name,
        junction_path,
    )

    # HTTP ヘッダー設定
    headers = urllib3.make_headers(
        basic_auth=f"{creds['username']}:{creds['password']}"
    )
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "application/json"

    # SVM UUID を取得
    svm_uuid = _get_svm_uuid(mgmt_ip, headers, svm_name)

    # ONTAP REST API: POST /api/protocols/cifs/shares
    body: dict[str, Any] = {
        "svm": {"uuid": svm_uuid, "name": svm_name},
        "name": share_name,
        "path": junction_path,
    }

    if comment:
        body["comment"] = comment

    url = f"https://{mgmt_ip}/api/protocols/cifs/shares"
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
            "CIFS share creation failed: status=%d, body=%s",
            resp.status,
            error_detail,
        )
        raise RuntimeError(
            f"ONTAP API error (status {resp.status}): {error_detail}"
        )

    logger.info("CIFS share created: %s → %s", share_name, junction_path)

    return {
        "share_name": share_name,
        "status": "created",
    }
