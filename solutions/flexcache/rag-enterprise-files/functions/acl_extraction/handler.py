"""GenAI RAG ACL Extraction Lambda

ONTAP REST API 経由でファイルの ACL/権限情報を取得し、
ベクトルストアのメタデータとして保存する。
Permission-aware RAG の核となる機能。
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "shared"))

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SIMULATION_MODE = os.environ.get("SIMULATION_MODE", "true").lower() == "true"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """ACL Extraction Lambda ハンドラー"""
    key = event.get("key", "")

    logger.info("Extracting ACL for: %s", key)

    if SIMULATION_MODE or not os.environ.get("ONTAP_MANAGEMENT_IP"):
        return _simulate_acl(key)

    return _real_acl_extraction(key)


def _simulate_acl(key: str) -> dict[str, Any]:
    """シミュレーションモードの ACL 取得"""
    # ファイルパスからシミュレーション権限を生成
    if "confidential" in key.lower() or "secret" in key.lower():
        allowed_sids = ["S-1-5-21-DOMAIN-1001"]  # 限定アクセス
    elif "public" in key.lower() or "shared" in key.lower():
        allowed_sids = ["S-1-5-21-DOMAIN-513"]  # Domain Users
    else:
        allowed_sids = ["S-1-5-21-DOMAIN-1001", "S-1-5-21-DOMAIN-1002", "S-1-5-21-DOMAIN-513"]

    return {
        "key": key,
        "status": "completed",
        "acl": {
            "security_style": "ntfs",
            "allowed_sids": allowed_sids,
            "owner_sid": "S-1-5-21-DOMAIN-1001",
            "permissions": "read",
        },
        "simulation": True,
        "timestamp": int(time.time()),
    }


def _real_acl_extraction(key: str) -> dict[str, Any]:
    """実環境の ACL 取得"""
    try:
        from shared.ontap_client import OntapClient, OntapClientConfig

        config = OntapClientConfig(
            management_ip=os.environ["ONTAP_MANAGEMENT_IP"],
            secret_name=os.environ["ONTAP_SECRET_NAME"],
        )
        client = OntapClient(config)

        # ファイルパスから SVM/Volume 情報を解決
        svm_uuid = os.environ.get("SVM_UUID", "")
        volume_uuid = os.environ.get("VOLUME_UUID", "")

        if svm_uuid and volume_uuid:
            security_info = client.get_file_security(svm_uuid, volume_uuid, key)
            acl_data = _parse_security_info(security_info)
        else:
            acl_data = {"security_style": "unknown", "allowed_sids": [], "note": "SVM/Volume UUID not configured"}

        return {
            "key": key,
            "status": "completed",
            "acl": acl_data,
            "simulation": False,
            "timestamp": int(time.time()),
        }

    except Exception as e:
        logger.error("ACL extraction failed for %s: %s", key, str(e))
        return {
            "key": key,
            "status": "error",
            "error": str(e),
            "acl": {"security_style": "unknown", "allowed_sids": []},
            "simulation": False,
            "timestamp": int(time.time()),
        }


def _parse_security_info(security_info: dict) -> dict[str, Any]:
    """ONTAP セキュリティ情報を解析"""
    acls = security_info.get("acls", [])
    allowed_sids = []

    for acl in acls:
        if acl.get("access") == "access_allow":
            user = acl.get("user_or_group", "")
            if user:
                allowed_sids.append(user)

    return {
        "security_style": security_info.get("security_style", "unknown"),
        "allowed_sids": allowed_sids,
        "owner_sid": security_info.get("owner", ""),
        "permissions": "read",
    }
