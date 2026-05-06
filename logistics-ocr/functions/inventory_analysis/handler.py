"""物流 / サプライチェーン 倉庫在庫画像分析 Lambda ハンドラ

Rekognition で倉庫在庫画像の物体検出・カウント（パレット、箱、棚占有率）を実行する。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    OUTPUT_BUCKET: S3 出力バケット名
    CONFIDENCE_THRESHOLD: 信頼度閾値 (デフォルト: 70)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import PurePosixPath

import boto3

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)

# 在庫関連のラベルカテゴリ
INVENTORY_LABELS = [
    "Box", "Package", "Carton", "Pallet", "Shelf",
    "Warehouse", "Container", "Crate", "Rack",
]


def detect_inventory_objects(
    rekognition_client, image_bytes: bytes, max_labels: int = 50
) -> list[dict]:
    """Rekognition DetectLabels で在庫関連オブジェクトを検出する

    Args:
        rekognition_client: boto3 Rekognition クライアント
        image_bytes: 画像バイナリデータ
        max_labels: 最大ラベル数

    Returns:
        list[dict]: 検出されたラベルのリスト
    """
    with xray_subsegment(

        name="rekognition_detectlabels",

        annotations={"service_name": "rekognition", "operation": "DetectLabels", "use_case": "logistics-ocr"},

    ):

        response = rekognition_client.detect_labels(
        Image={"Bytes": image_bytes},
        MaxLabels=max_labels,
    )

    labels = []
    for label in response.get("Labels", []):
        labels.append({
            "name": label["Name"],
            "confidence": round(label["Confidence"], 2),
            "instances": len(label.get("Instances", [])),
            "parents": [p["Name"] for p in label.get("Parents", [])],
        })

    return labels


def count_inventory_items(labels: list[dict], threshold: float) -> dict:
    """在庫関連アイテムをカウントする

    Args:
        labels: 検出されたラベルのリスト
        threshold: 信頼度閾値

    Returns:
        dict: アイテムカウント結果
    """
    inventory_counts = {}
    total_items = 0

    for label in labels:
        if label["confidence"] < threshold:
            continue
        if label["name"] in INVENTORY_LABELS or any(
            parent in INVENTORY_LABELS for parent in label.get("parents", [])
        ):
            count = max(label.get("instances", 0), 1)
            inventory_counts[label["name"]] = {
                "count": count,
                "confidence": label["confidence"],
            }
            total_items += count

    return {
        "item_counts": inventory_counts,
        "total_items": total_items,
        "categories_detected": len(inventory_counts),
    }


def estimate_shelf_occupancy(labels: list[dict]) -> float:
    """棚占有率を推定する

    Args:
        labels: 検出されたラベルのリスト

    Returns:
        float: 推定占有率 (0.0 - 1.0)
    """
    shelf_detected = any(
        l["name"] in ("Shelf", "Rack") for l in labels
    )
    if not shelf_detected:
        return 0.0

    item_labels = [
        l for l in labels
        if l["name"] in ("Box", "Package", "Carton", "Container", "Crate")
    ]
    total_instances = sum(
        max(l.get("instances", 0), 1) for l in item_labels
    )

    # 簡易推定: インスタンス数に基づく占有率
    occupancy = min(total_instances / 20.0, 1.0)
    return round(occupancy, 2)


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """倉庫在庫画像分析（Rekognition）

    Input:
        {"Key": "warehouse/zone_a_20260115.jpg", "Size": 4194304, ...}

    Output:
        {
            "status": "SUCCESS",
            "file_key": "...",
            "inventory_analysis": {
                "item_counts": {...},
                "total_items": 15,
                "categories_detected": 3,
                "shelf_occupancy": 0.75
            },
            "all_labels": [...],
            "output_key": "..."
        }
    """
    file_key = event["Key"]
    file_size = event.get("Size", 0)

    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_bucket = os.environ["OUTPUT_BUCKET"]
    confidence_threshold = float(os.environ.get("CONFIDENCE_THRESHOLD", "70"))

    logger.info(
        "Inventory analysis started: file_key=%s, size=%d",
        file_key,
        file_size,
    )

    # 画像取得
    response = s3ap.get_object(file_key)
    image_bytes = response["Body"].read()

    # Rekognition で物体検出
    rekognition_client = boto3.client("rekognition")
    labels = detect_inventory_objects(rekognition_client, image_bytes)

    # 在庫アイテムカウント
    inventory_result = count_inventory_items(labels, confidence_threshold)

    # 棚占有率推定
    shelf_occupancy = estimate_shelf_occupancy(labels)
    inventory_result["shelf_occupancy"] = shelf_occupancy

    # 出力キー生成
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    output_key = f"inventory/{now.strftime('%Y/%m/%d')}/{file_stem}_analysis.json"

    # 結果を S3 出力バケットに書き込み
    output_data = {
        "status": "SUCCESS",
        "file_key": file_key,
        "inventory_analysis": inventory_result,
        "all_labels": labels,
        "output_key": output_key,
        "analyzed_at": now.isoformat(),
    }

    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=output_bucket,
        Key=output_key,
        Body=json.dumps(output_data, default=str, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
    )

    logger.info(
        "Inventory analysis completed: file_key=%s, total_items=%d, occupancy=%.2f",
        file_key,
        inventory_result["total_items"],
        shelf_occupancy,
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="inventory_analysis")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "logistics-ocr"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return output_data
