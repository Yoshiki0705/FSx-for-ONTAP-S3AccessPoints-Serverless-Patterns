"""医療 DICOM Parse Lambda ハンドラ

Map ステートから DICOM ファイル情報を受け取り、S3ApHelper で
ファイルを取得してメタデータを解析する。

pydicom が Lambda 環境で利用できない場合を考慮し、
イベントからメタデータを受け取るフォールバックと
簡易バイナリヘッダーパーサーを提供する。

テスト可能なヘルパー関数:
    anonymize_metadata(metadata) — PHI フィールドを除去し分類情報を付与する

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用、省略時は S3_ACCESS_POINT を使用)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)

# PHI（保護対象医療情報）フィールド一覧
PHI_FIELDS = [
    "patient_name",
    "patient_id",
    "patient_birth_date",
    "patient_address",
    "patient_phone",
    "referring_physician",
    "institution_name",
    "institution_address",
]

# 分類に使用するモダリティマッピング
MODALITY_CATEGORIES = {
    "CT": "computed_tomography",
    "MR": "magnetic_resonance",
    "US": "ultrasound",
    "XR": "x_ray",
    "CR": "computed_radiography",
    "MG": "mammography",
    "NM": "nuclear_medicine",
    "PT": "positron_emission",
    "DX": "digital_radiography",
    "OT": "other",
}


def anonymize_metadata(metadata: dict) -> dict:
    """DICOM メタデータから PHI フィールドを除去し分類情報を付与する

    テスト可能なヘルパー関数。PHI フィールドを除去し、
    モダリティと部位に基づく分類メタデータを追加する。

    Args:
        metadata: DICOM メタデータ辞書。以下のキーを含む可能性がある:
            - patient_name, patient_id 等の PHI フィールド
            - modality: モダリティコード (例: "CT", "MR")
            - body_part: 撮影部位 (例: "CHEST", "HEAD")
            - study_date: 検査日

    Returns:
        dict: PHI を除去し分類情報を付与したメタデータ。
            - modality, body_part は保持
            - classification カテゴリを追加
            - PHI フィールドは除去済み
    """
    # 元のメタデータをコピー（元データを変更しない）
    result = dict(metadata)

    # PHI フィールドを除去
    for field in PHI_FIELDS:
        result.pop(field, None)

    # モダリティに基づく分類を追加
    modality = result.get("modality", "OT")
    body_part = result.get("body_part", "UNKNOWN")

    result["classification"] = {
        "modality_category": MODALITY_CATEGORIES.get(modality, "other"),
        "body_part": body_part,
        "modality_code": modality,
    }

    return result


def _parse_dicom_header(data: bytes) -> dict | None:
    """DICOM バイナリヘッダーから基本メタデータを抽出する簡易パーサー

    pydicom が利用できない環境向けのフォールバック。
    DICOM ファイルの先頭 132 バイト（プリアンブル + マジックナンバー）を
    検証し、基本的なメタデータを返す。

    Args:
        data: DICOM ファイルのバイナリデータ

    Returns:
        dict | None: 基本メタデータ。パース失敗時は None。
    """
    # DICOM ファイルは 128 バイトのプリアンブル + "DICM" マジックナンバー
    if len(data) < 132:
        return None

    magic = data[128:132]
    if magic != b"DICM":
        return None

    # 簡易パーサーでは詳細なタグ解析は行わず、
    # 有効な DICOM ファイルであることのみ確認する
    return {
        "valid_dicom": True,
        "file_size": len(data),
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """DICOM Parse Lambda

    Map ステートから DICOM ファイル情報を受け取り、
    メタデータを解析・分類する。

    Args:
        event: Map ステートからの入力。以下のキーを含む:
            - Key (str): DICOM ファイルの S3 キー
            - Size (int): ファイルサイズ
            - metadata (dict, optional): 事前解析済みメタデータ

    Returns:
        dict: dicom_key, metadata, classification, status
    """
    dicom_key = event["Key"]

    logger.info("DICOM Parse started: key=%s", dicom_key)

    # イベントに事前解析済みメタデータがある場合はそれを使用
    metadata = event.get("metadata")

    if metadata is None:
        # S3 AP から DICOM ファイルを取得
        try:
            s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
            response = s3ap.get_object(dicom_key)
            dicom_data = response["Body"].read()

            logger.info(
                "DICOM file retrieved: key=%s, size=%d bytes",
                dicom_key,
                len(dicom_data),
            )

            # DICOM ヘッダーを簡易パース
            header_info = _parse_dicom_header(dicom_data)
            if header_info is None:
                logger.error(
                    "Invalid DICOM file: key=%s", dicom_key
                )
                return {
                    "dicom_key": dicom_key,
                    "status": "INVALID",
                    "error": "Invalid DICOM file format",
                }

            # 簡易パーサーではメタデータ抽出が限定的なため、
            # デフォルト値を設定
            metadata = {
                "patient_name": "",
                "patient_id": "",
                "study_date": "",
                "modality": "OT",
                "body_part": "UNKNOWN",
                "file_size": header_info["file_size"],
            }

        except Exception as e:
            logger.error(
                "Failed to parse DICOM file: key=%s, error=%s",
                dicom_key,
                str(e),
            )
            return {
                "dicom_key": dicom_key,
                "status": "INVALID",
                "error": str(e),
            }

    # メタデータを匿名化・分類
    anonymized = anonymize_metadata(metadata)

    # 結果を S3 AP に書き出し
    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"])
    )
    output_key = (
        f"dicom-metadata/{datetime.utcnow().strftime('%Y/%m/%d')}"
        f"/{dicom_key.rsplit('/', 1)[-1]}.json"
    )

    result = {
        "dicom_key": dicom_key,
        "metadata": anonymized,
        "classification": anonymized.get("classification", {}),
        "parsed_at": datetime.utcnow().isoformat(),
        "status": "SUCCESS",
    }

    s3ap_output.put_object(
        key=output_key,
        body=json.dumps(result, default=str),
        content_type="application/json",
    )

    logger.info(
        "DICOM Parse completed: key=%s, modality=%s, body_part=%s",
        dicom_key,
        anonymized.get("modality", "OT"),
        anonymized.get("body_part", "UNKNOWN"),
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="dicom_parse")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "healthcare-dicom"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return {
        "dicom_key": dicom_key,
        "metadata": anonymized,
        "classification": anonymized.get("classification", {}),
        "output_key": output_key,
        "status": "SUCCESS",
    }
