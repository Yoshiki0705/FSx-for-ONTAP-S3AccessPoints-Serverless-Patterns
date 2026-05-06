"""医療 DICOM Anonymization Lambda ハンドラ

DICOM メタデータと PII 検出結果を受け取り、
Amazon Comprehend Medical DetectPHI でメタデータテキスト内の
PHI（保護対象医療情報）を特定・除去する。

匿名化された DICOM メタデータを分類情報付きで S3 AP に書き出す。

テスト可能なヘルパー関数:
    redact_phi_fields(metadata, phi_entities) — PHI 値を除去する

Environment Variables:
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    SNS_TOPIC_ARN: 通知先 SNS トピック ARN
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

import boto3

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)

# PHI として除去対象のフィールド名一覧
PHI_FIELD_NAMES = [
    "patient_name",
    "patient_id",
    "patient_birth_date",
    "patient_address",
    "patient_phone",
    "referring_physician",
    "institution_name",
    "institution_address",
]


def redact_phi_fields(metadata: dict, phi_entities: list) -> dict:
    """メタデータから PHI フィールドの値を除去する

    テスト可能なヘルパー関数。Comprehend Medical が検出した
    PHI エンティティに基づき、メタデータ内の該当フィールドを
    "[REDACTED]" に置換する。

    また、既知の PHI フィールド名に一致するフィールドも
    無条件に除去する。

    Args:
        metadata: DICOM メタデータ辞書
        phi_entities: Comprehend Medical DetectPHI の結果リスト。
            各要素は以下のキーを含む:
            - Text (str): 検出された PHI テキスト
            - Type (str): PHI タイプ (例: "NAME", "DATE", "ID")
            - Score (float): 信頼度スコア

    Returns:
        dict: PHI を除去したメタデータ。
            - 既知の PHI フィールドは "[REDACTED]" に置換
            - phi_entities に含まれるテキストと一致する値も除去
            - modality, body_part, classification は保持
    """
    result = dict(metadata)

    # 既知の PHI フィールド名を "[REDACTED]" に置換
    for field in PHI_FIELD_NAMES:
        if field in result and result[field]:
            result[field] = "[REDACTED]"

    # Comprehend Medical が検出した PHI テキストと一致する値を除去
    phi_texts = {entity.get("Text", "") for entity in phi_entities}
    for key, value in list(result.items()):
        if isinstance(value, str) and value in phi_texts and value:
            result[key] = "[REDACTED]"

    return result


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Anonymization Lambda

    DICOM メタデータと PII 検出結果を受け取り、
    Comprehend Medical で PHI を特定・除去し、
    匿名化メタデータを S3 出力バケットに書き出す。

    Args:
        event: 前段（PII Detection）からの入力。以下のキーを含む:
            - dicom_key (str): DICOM ファイルの S3 キー
            - metadata (dict): 解析済みメタデータ
            - classification (dict): 分類情報
            - pii_detection (dict): PII 検出結果

    Returns:
        dict: dicom_key, anonymized_metadata, classification,
              output_bucket, output_key, status
    """
    dicom_key = event["dicom_key"]
    metadata = event.get("metadata", {})
    classification = event.get("classification", {})
    pii_detection = event.get("pii_detection", {})

    logger.info("Anonymization started: key=%s", dicom_key)

    # メタデータのテキスト値を結合して Comprehend Medical に送信
    text_values = []
    for key, value in metadata.items():
        if isinstance(value, str) and value and key != "classification":
            text_values.append(f"{key}: {value}")

    combined_text = "; ".join(text_values) if text_values else ""

    # Comprehend Medical DetectPHI で PHI を検出
    phi_entities = []
    if combined_text:
        # Comprehend Medical（ap-northeast-1 非対応のため COMPREHEND_MEDICAL_REGION で指定）
        # 参考: https://docs.aws.amazon.com/general/latest/gr/comprehend-med.html
        cm_region = os.environ.get("COMPREHEND_MEDICAL_REGION", "us-east-1")
        comprehend_medical = boto3.client("comprehendmedical", region_name=cm_region)
        try:
            detect_response = comprehend_medical.detect_phi(
                Text=combined_text,
            )
            phi_entities = detect_response.get("Entities", [])
        except Exception as e:
            logger.warning(
                "Comprehend Medical DetectPHI failed for %s: %s. "
                "Proceeding with field-name-based redaction only.",
                dicom_key,
                str(e),
            )

    # PHI フィールドを除去
    anonymized = redact_phi_fields(metadata, phi_entities)

    # 分類メタデータを確保
    if "classification" not in anonymized:
        anonymized["classification"] = classification

    # 匿名化結果を S3 AP に書き出し
    s3ap_output = S3ApHelper(os.environ["S3_ACCESS_POINT_OUTPUT"])
    output_key = (
        f"anonymized/{datetime.utcnow().strftime('%Y/%m/%d')}"
        f"/{dicom_key.rsplit('/', 1)[-1]}.json"
    )

    result = {
        "dicom_key": dicom_key,
        "anonymized_metadata": anonymized,
        "classification": anonymized.get("classification", {}),
        "phi_entities_detected": len(phi_entities),
        "burned_in_pii_detected": pii_detection.get("has_pii", False),
        "anonymized_at": datetime.utcnow().isoformat(),
    }

    s3ap_output.put_object(
        key=output_key,
        body=json.dumps(result, default=str),
        content_type="application/json",
    )

    logger.info(
        "Anonymization completed: key=%s, phi_entities=%d, output=%s",
        dicom_key,
        len(phi_entities),
        output_key,
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="anonymization")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "healthcare-dicom"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return {
        "dicom_key": dicom_key,
        "anonymized_metadata": anonymized,
        "classification": anonymized.get("classification", {}),
        "output_key": output_key,
        "status": "SUCCESS",
    }
