#!/usr/bin/env python3
"""共通モジュール AWS 環境動作検証スクリプト

OntapClient, FsxHelper, S3ApHelper の AWS 環境での動作を検証する。
実行前に環境変数を設定すること。

環境変数:
    S3_ACCESS_POINT: S3 AP Alias (例: vol-name-xxxxx-ext-s3alias)
    ONTAP_SECRET_NAME: Secrets Manager シークレット名
    ONTAP_MANAGEMENT_IP: ONTAP 管理 IP
    FSX_FILESYSTEM_ID: FSx ファイルシステム ID (例: fs-0123456789abcdef0)

使用方法:
    export S3_ACCESS_POINT=<your-ap-alias>
    export ONTAP_SECRET_NAME=<your-secret-name>
    export ONTAP_MANAGEMENT_IP=<your-ontap-ip>
    export FSX_FILESYSTEM_ID=<your-fs-id>
    python3 scripts/verify_shared_modules.py
"""
import os
import sys
import json
import logging

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared import OntapClient, OntapClientConfig, FsxHelper, S3ApHelper

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def verify_s3ap_helper():
    """S3ApHelper: ListObjectsV2, HeadObject テスト"""
    ap = os.environ["S3_ACCESS_POINT"]
    logger.info("=== S3ApHelper Verification ===")
    helper = S3ApHelper(ap)
    objects = helper.list_objects(max_keys=5)
    logger.info(f"ListObjectsV2: {len(objects)} objects found")
    for obj in objects[:3]:
        logger.info(f"  Key={obj['Key']}, Size={obj['Size']}")
    if objects:
        head = helper.head_object(objects[0]["Key"])
        logger.info(
            f"HeadObject: ContentLength={head.get('ContentLength')}, "
            f"ContentType={head.get('ContentType')}"
        )
    logger.info("S3ApHelper: PASSED")


def verify_fsx_helper():
    """FsxHelper: describe_file_systems, describe_volumes テスト"""
    fs_id = os.environ.get("FSX_FILESYSTEM_ID")
    logger.info("=== FsxHelper Verification ===")
    helper = FsxHelper()
    if fs_id:
        filesystems = helper.describe_file_systems(filesystem_ids=[fs_id])
        logger.info(f"describe_file_systems: {len(filesystems)} filesystem(s)")
        volumes = helper.describe_volumes(
            filters=[{"Name": "file-system-id", "Values": [fs_id]}]
        )
        logger.info(f"describe_volumes: {len(volumes)} volume(s)")
    else:
        filesystems = helper.describe_file_systems()
        logger.info(f"describe_file_systems (all): {len(filesystems)} filesystem(s)")
    logger.info("FsxHelper: PASSED")


def verify_ontap_client():
    """OntapClient: Secrets Manager 認証, list_volumes テスト"""
    logger.info("=== OntapClient Verification ===")
    config = OntapClientConfig(
        management_ip=os.environ["ONTAP_MANAGEMENT_IP"],
        secret_name=os.environ["ONTAP_SECRET_NAME"],
    )
    client = OntapClient(config)
    volumes = client.list_volumes()
    logger.info(f"list_volumes: {len(volumes)} volume(s)")
    for vol in volumes[:3]:
        logger.info(f"  Name={vol.get('name')}, UUID={vol.get('uuid')}")
    logger.info("OntapClient: PASSED")


if __name__ == "__main__":
    results = {}
    for name, func in [
        ("S3ApHelper", verify_s3ap_helper),
        ("FsxHelper", verify_fsx_helper),
        ("OntapClient", verify_ontap_client),
    ]:
        try:
            func()
            results[name] = "PASSED"
        except Exception as e:
            logger.error(f"{name}: FAILED - {e}")
            results[name] = f"FAILED: {e}"

    logger.info("=== Verification Summary ===")
    for name, status in results.items():
        logger.info(f"  {name}: {status}")
