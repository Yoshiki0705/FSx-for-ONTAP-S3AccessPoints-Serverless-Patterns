"""不動産 (UC26) Discovery Lambda ハンドラ

S3 Access Point から物件画像（内装/外装/間取り図）および
賃貸契約書 PDF を検出し、物件 ID + タイプで分類した Manifest を生成する。

ファイル分類:
    - 物件画像: PROPERTY_IMAGE_PREFIX 配下の画像 (JPEG/PNG/TIFF)
    - 契約書: CONTRACT_PREFIX 配下の PDF

S3 AP 接続性バリデーション (Requirement 13.5):
    処理開始前に S3 AP への接続を検証し、到達不可時は構造化エラーを返す。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    PROPERTY_IMAGE_PREFIX: 物件画像プレフィックス (default: "properties/images/")
    CONTRACT_PREFIX: 契約書プレフィックス (default: "properties/contracts/")
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone

from shared.exceptions import S3ApHelperError, lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler, xray_subsegment
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

# 物件画像の対応拡張子
PROPERTY_IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".tiff", ".tif"}
)

# 契約書の対応拡張子
CONTRACT_EXTENSIONS: frozenset[str] = frozenset({".pdf"})

# ファイルタイプ定数
FILE_TYPE_PROPERTY_IMAGE = "property_image"
FILE_TYPE_CONTRACT = "contract"

# 画像タイプ分類キーワード
IMAGE_TYPE_KEYWORDS: dict[str, str] = {
    "interior": "interior",
    "内装": "interior",
    "room": "interior",
    "exterior": "exterior",
    "外装": "exterior",
    "outside": "exterior",
    "floor_plan": "floor_plan",
    "間取り": "floor_plan",
    "floorplan": "floor_plan",
    "madori": "floor_plan",
}

# 物件 ID パターン: PROP-XXXX, property-XXX, property_XXX
PROPERTY_ID_PATTERN = re.compile(
    r"(?:PROP[-_]|property[-_])([A-Za-z0-9]+)", re.IGNORECASE
)


def classify_file(
    key: str,
    property_image_prefix: str,
    contract_prefix: str,
) -> str | None:
    """ファイルキーをタイプに分類する。

    Args:
        key: S3 オブジェクトキー
        property_image_prefix: 物件画像プレフィックス
        contract_prefix: 契約書プレフィックス

    Returns:
        "property_image" | "contract" | None
    """
    if not key:
        return None

    dot_index = key.rfind(".")
    if dot_index == -1:
        return None

    extension = key[dot_index:].lower()

    if property_image_prefix and key.startswith(property_image_prefix):
        if extension in PROPERTY_IMAGE_EXTENSIONS:
            return FILE_TYPE_PROPERTY_IMAGE
        return None

    if contract_prefix and key.startswith(contract_prefix):
        if extension in CONTRACT_EXTENSIONS:
            return FILE_TYPE_CONTRACT
        return None

    return None


def extract_property_id(key: str) -> str | None:
    """ファイルパスから物件 ID を抽出する。

    例: "properties/images/PROP-12345/interior/img001.jpg" → "12345"

    Args:
        key: S3 オブジェクトキー

    Returns:
        str | None: 物件 ID or None
    """
    match = PROPERTY_ID_PATTERN.search(key)
    if match:
        return match.group(1)
    return None


def detect_image_type(key: str) -> str:
    """画像パスからタイプを推定する。

    Args:
        key: S3 オブジェクトキー

    Returns:
        str: 画像タイプ (interior/exterior/floor_plan/other)
    """
    key_lower = key.lower()
    for keyword, image_type in IMAGE_TYPE_KEYWORDS.items():
        if keyword in key_lower:
            return image_type
    return "other"


def validate_s3ap_connectivity(s3ap: S3ApHelper) -> dict | None:
    """S3 Access Point への接続性を検証する。

    Args:
        s3ap: S3ApHelper インスタンス

    Returns:
        None: 接続成功時
        dict: 接続失敗時の構造化エラーレスポンス
    """
    try:
        s3ap.list_objects(prefix="", suffix="", max_keys=1)
        return None
    except S3ApHelperError as e:
        logger.error(
            "S3 AP connectivity validation failed: %s (error_code=%s)",
            str(e),
            e.error_code,
        )
        return {
            "statusCode": 503,
            "body": json.dumps({
                "error": "S3 Access Point unreachable",
                "error_type": "ConnectivityError",
                "error_code": e.error_code or "Unknown",
                "access_point": s3ap.bucket_param,
                "message": str(e),
            }),
        }
    except Exception as e:
        logger.error("Unexpected error during S3 AP connectivity: %s", str(e))
        return {
            "statusCode": 503,
            "body": json.dumps({
                "error": "S3 Access Point unreachable",
                "error_type": "ConnectivityError",
                "error_code": "UnexpectedError",
                "access_point": s3ap.bucket_param,
                "message": str(e),
            }),
        }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Real Estate Portfolio Discovery Lambda

    物件画像 + 契約書を検出し、物件 ID・画像タイプで分類した Manifest を生成する。

    Returns:
        dict: manifest_key, total_objects, property_images, contracts
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"])
    )
    property_image_prefix = os.environ.get("PROPERTY_IMAGE_PREFIX", "properties/images/")
    contract_prefix = os.environ.get("CONTRACT_PREFIX", "properties/contracts/")

    logger.info(
        "Real Estate Discovery started: access_point=%s, "
        "image_prefix=%r, contract_prefix=%r",
        os.environ["S3_ACCESS_POINT"],
        property_image_prefix,
        contract_prefix,
    )

    # Step 1: S3 AP 接続性バリデーション
    with xray_subsegment(
        name="s3ap_connectivity_validation",
        annotations={
            "service_name": "s3",
            "operation": "ConnectivityCheck",
            "use_case": "real-estate-portfolio",
        },
    ):
        connectivity_error = validate_s3ap_connectivity(s3ap)
        if connectivity_error is not None:
            return connectivity_error

    # Step 2: オブジェクト一覧取得
    property_images: list[dict] = []
    contracts: list[dict] = []

    # 物件画像検出
    with xray_subsegment(
        name="s3ap_list_property_images",
        annotations={
            "service_name": "s3",
            "operation": "ListObjectsV2",
            "use_case": "real-estate-portfolio",
            "prefix": property_image_prefix,
        },
    ):
        image_objects = s3ap.list_objects(prefix=property_image_prefix, suffix="")

    for obj in image_objects:
        key = obj.get("Key", "")
        file_type = classify_file(key, property_image_prefix, contract_prefix)
        if file_type == FILE_TYPE_PROPERTY_IMAGE:
            obj["file_type"] = file_type
            obj["property_id"] = extract_property_id(key)
            obj["image_type"] = detect_image_type(key)
            property_images.append(obj)

    # 契約書検出
    with xray_subsegment(
        name="s3ap_list_contracts",
        annotations={
            "service_name": "s3",
            "operation": "ListObjectsV2",
            "use_case": "real-estate-portfolio",
            "prefix": contract_prefix,
        },
    ):
        contract_objects = s3ap.list_objects(prefix=contract_prefix, suffix="")

    for obj in contract_objects:
        key = obj.get("Key", "")
        file_type = classify_file(key, property_image_prefix, contract_prefix)
        if file_type == FILE_TYPE_CONTRACT:
            obj["file_type"] = file_type
            obj["property_id"] = extract_property_id(key)
            contracts.append(obj)

    all_objects = property_images + contracts

    # 物件 ID 統計
    property_ids: dict[str, int] = {}
    for obj in all_objects:
        pid = obj.get("property_id")
        if pid:
            property_ids[pid] = property_ids.get(pid, 0) + 1

    logger.info(
        "File classification: property_images=%d, contracts=%d, "
        "total=%d, unique_properties=%d",
        len(property_images),
        len(contracts),
        len(all_objects),
        len(property_ids),
    )

    # Manifest 生成
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "use_case": "real-estate-portfolio",
        "total_objects": len(all_objects),
        "total_size_bytes": sum(obj.get("Size", 0) for obj in all_objects),
        "property_image_count": len(property_images),
        "contract_count": len(contracts),
        "unique_property_count": len(property_ids),
        "property_ids": property_ids,
        "property_image_prefix": property_image_prefix,
        "contract_prefix": contract_prefix,
        "objects": all_objects,
    }

    manifest_key = (
        f"manifests/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/"
        f"{context.aws_request_id}.json"
    )

    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    logger.info(
        "Real Estate Discovery completed: total=%d, manifest=%s",
        len(all_objects),
        manifest_key,
    )

    # EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", "real-estate-portfolio")
    metrics.put_metric("FilesProcessed", float(len(all_objects)), "Count")
    metrics.put_metric("PropertyImages", float(len(property_images)), "Count")
    metrics.put_metric("Contracts", float(len(contracts)), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(all_objects),
        "property_images": property_images,
        "contracts": contracts,
    }
