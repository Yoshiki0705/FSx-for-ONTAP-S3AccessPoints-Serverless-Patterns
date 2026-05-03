"""ONTAP REST API テスト用 Lambda ハンドラ

VPC 内から ONTAP REST API に接続してボリューム情報を取得するテスト。
S3 AP アクセスは行わない（VPC 内 S3 アクセスの問題を切り分けるため）。
"""
import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    """ONTAP REST API テスト"""
    import sys
    sys.path.insert(0, '/var/task')
    
    from shared.ontap_client import OntapClient, OntapClientConfig
    
    management_ip = os.environ.get("ONTAP_MANAGEMENT_IP", "")
    secret_name = os.environ.get("ONTAP_SECRET_NAME", "fsxn-ontap-credentials")
    svm_uuid = os.environ.get("SVM_UUID", "")
    verify_ssl = os.environ.get("VERIFY_SSL", "true").lower() != "false"
    
    results = {"tests": []}
    
    # Test 1: OntapClient 初期化
    try:
        config = OntapClientConfig(
            management_ip=management_ip,
            secret_name=secret_name,
            verify_ssl=verify_ssl,
        )
        client = OntapClient(config)
        results["tests"].append({"name": "OntapClient init", "status": "PASSED"})
    except Exception as e:
        results["tests"].append({"name": "OntapClient init", "status": "FAILED", "error": str(e)})
        return results
    
    # Test 2: list_volumes
    try:
        volumes = client.list_volumes(svm_uuid=svm_uuid)
        results["tests"].append({
            "name": "list_volumes",
            "status": "PASSED",
            "count": len(volumes),
            "volumes": [{"name": v.get("name"), "uuid": v.get("uuid", "")[:12]} for v in volumes[:5]]
        })
    except Exception as e:
        results["tests"].append({"name": "list_volumes", "status": "FAILED", "error": str(e)})
    
    # Test 3: list_nfs_exports
    try:
        exports = client.list_nfs_exports(svm_uuid)
        results["tests"].append({
            "name": "list_nfs_exports",
            "status": "PASSED",
            "count": len(exports),
        })
    except Exception as e:
        results["tests"].append({"name": "list_nfs_exports", "status": "FAILED", "error": str(e)})
    
    # Test 4: list_cifs_shares
    try:
        shares = client.list_cifs_shares(svm_uuid)
        results["tests"].append({
            "name": "list_cifs_shares",
            "status": "PASSED",
            "count": len(shares),
        })
    except Exception as e:
        results["tests"].append({"name": "list_cifs_shares", "status": "FAILED", "error": str(e)})
    
    # Test 5: get_svm
    try:
        svm = client.get_svm(svm_uuid)
        results["tests"].append({
            "name": "get_svm",
            "status": "PASSED",
            "svm_name": svm.get("name", "unknown"),
        })
    except Exception as e:
        results["tests"].append({"name": "get_svm", "status": "FAILED", "error": str(e)})
    
    return results
