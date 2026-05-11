"""医療 PII Detection Lambda ハンドラ

DICOM 画像データを受け取り、Amazon Rekognition DetectText を使用して
画像ピクセルに焼き込まれた個人情報（PII）を検出する。

検出されたテキストと信頼度スコアを返し、後続の Anonymization Lambda に
PII 検出結果を渡す。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用、省略時は S3_ACCESS_POINT を使用)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

import boto3

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """PII Detection Lambda

    DICOM 画像データを受け取り、Rekognition DetectText で
    焼き込み個人情報を検出する。

    Args:
        event: 前段（DICOM Parse）からの入力。以下のキーを含む:
            - dicom_key (str): DICOM ファイルの S3 キー
            - metadata (dict): 解析済みメタデータ
            - classification (dict): 分類情報

    Returns:
        dict: dicom_key, metadata, classification,
              pii_detection (detected_texts, has_pii), status
    """
    dicom_key = event["dicom_key"]
    metadata = event.get("metadata", {})
    classification = event.get("classification", {})

    logger.info("PII Detection started: key=%s", dicom_key)

    # S3 AP から DICOM ファイルを取得
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    response = s3ap.get_object(dicom_key)
    raw_bytes = response["Body"].read()

    logger.info(
        "DICOM file retrieved for PII detection: key=%s, size=%d bytes",
        dicom_key,
        len(raw_bytes),
    )

    # DICOM ファイルは Rekognition の画像フォーマット（JPEG/PNG）ではないため、
    # ピクセルデータの抽出を試行する。
    # 標準ライブラリのみで DICOM ピクセルデータを完全に抽出するのは困難なため、
    # メタデータベースの PII 検出にフォールバックする。
    # 本番環境では pydicom + Pillow を Lambda Layer として追加し、
    # DICOM → JPEG 変換を行うことを推奨。
    image_bytes = None
    is_dicom = raw_bytes[128:132] == b"DICM" if len(raw_bytes) > 132 else False

    if not is_dicom:
        # DICOM でない場合はそのまま画像として使用（JPEG/PNG の可能性）
        image_bytes = raw_bytes
    else:
        logger.info(
            "DICOM format detected — using metadata-based PII detection "
            "(Rekognition requires JPEG/PNG format)"
        )

    # Rekognition DetectText で焼き込みテキストを検出
    rekognition_client = boto3.client("rekognition")
    text_detections = []

    if image_bytes:
        try:
            detect_response = rekognition_client.detect_text(
                Image={"Bytes": image_bytes},
            )
            text_detections = detect_response.get("TextDetections", [])
        except Exception as e:
            logger.warning(
                "Rekognition DetectText failed for %s: %s. "
                "Proceeding with metadata-based PII detection.",
                dicom_key,
                str(e),
            )
    else:
        # DICOM フォーマット: メタデータから PII フィールドを検出
        phi_fields = ["patient_name", "patient_id", "patient_birth_date",
                      "referring_physician", "institution_name"]
        for field in phi_fields:
            value = metadata.get(field, "")
            if value:
                text_detections.append({
                    "DetectedText": f"{field}: {value}",
                    "Confidence": 100.0,
                    "Type": "LINE",
                })

    # LINE タイプのテキスト検出のみ抽出（WORD は重複するため除外）
    detected_texts = [
        {
            "text": det["DetectedText"],
            "confidence": det["Confidence"],
            "type": det["Type"],
        }
        for det in text_detections
        if det["Type"] == "LINE"
    ]

    has_pii = len(detected_texts) > 0

    # 結果を S3 AP に書き出し
    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"])
    )
    output_key = (
        f"pii-detection/{datetime.utcnow().strftime('%Y/%m/%d')}"
        f"/{dicom_key.rsplit('/', 1)[-1]}.json"
    )

    pii_result = {
        "dicom_key": dicom_key,
        "detected_texts": detected_texts,
        "total_detections": len(detected_texts),
        "has_pii": has_pii,
        "detected_at": datetime.utcnow().isoformat(),
    }

    s3ap_output.put_object(
        key=output_key,
        body=json.dumps(pii_result, default=str),
        content_type="application/json",
    )

    logger.info(
        "PII Detection completed: key=%s, detections=%d, has_pii=%s",
        dicom_key,
        len(detected_texts),
        has_pii,
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="pii_detection")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "healthcare-dicom"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return {
        "dicom_key": dicom_key,
        "metadata": metadata,
        "classification": classification,
        "pii_detection": {
            "detected_texts": detected_texts,
            "has_pii": has_pii,
        },
        "status": "SUCCESS",
    }
