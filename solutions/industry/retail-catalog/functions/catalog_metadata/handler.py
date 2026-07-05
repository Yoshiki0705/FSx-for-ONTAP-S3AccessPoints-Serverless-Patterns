"""小売 / EC カタログメタデータ生成 Lambda ハンドラ

Amazon Bedrock を使用して、Rekognition ラベルから構造化カタログメタデータ
（product_category, color, material, style_attributes）を生成し、
JSON 形式で S3 出力する。

Environment Variables:
    OUTPUT_DESTINATION: `STANDARD_S3` or `FSXN_S3AP` (デフォルト: `STANDARD_S3`)
    OUTPUT_BUCKET: STANDARD_S3 モードの出力バケット名
    OUTPUT_S3AP_ALIAS: FSXN_S3AP モードの S3AP Alias or ARN
    OUTPUT_S3AP_PREFIX: FSXN_S3AP モードの出力プレフィックス (デフォルト: `ai-outputs/`)
    BEDROCK_MODEL_ID: Bedrock モデル ID / 推論プロファイル ID (デフォルト: apac.amazon.nova-lite-v1:0)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import PurePosixPath

import boto3

from shared.bedrock_helper import converse_text, extract_json
from shared.exceptions import lambda_error_handler
from shared.output_writer import OutputWriter
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)

# カタログメタデータの必須フィールド
REQUIRED_METADATA_FIELDS = ["product_category", "color", "material", "style_attributes"]


def generate_catalog_metadata(bedrock_client, model_id: str, file_key: str, labels: list[dict]) -> dict:
    """Bedrock で構造化カタログメタデータを生成する

    Args:
        bedrock_client: boto3 Bedrock Runtime クライアント
        model_id: Bedrock モデル ID
        file_key: 画像ファイルキー
        labels: Rekognition ラベルのリスト

    Returns:
        dict: 構造化カタログメタデータ
    """
    labels_text = ", ".join(f"{label['name']} ({label['confidence']}%)" for label in labels)

    prompt = (
        f"Based on the following image labels detected from a product image, "
        f"generate structured catalog metadata in JSON format.\n\n"
        f"Image file: {file_key}\n"
        f"Detected labels: {labels_text}\n\n"
        f"Generate a JSON object with these exact fields:\n"
        f"- product_category: hierarchical category (e.g., 'Apparel > Tops > Shirts')\n"
        f"- color: primary color of the product\n"
        f"- material: likely material based on visual cues\n"
        f"- style_attributes: list of style descriptors\n"
        f"- suggested_tags: list of search/filter tags\n\n"
        f"Return ONLY the JSON object, no additional text."
    )

    with xray_subsegment(
        name="bedrock_converse",
        annotations={"service_name": "bedrock", "operation": "Converse", "use_case": "retail-catalog"},
    ):
        # モデル非依存の Converse API を使用（Nova / Claude は推論プロファイル ID 必須）。
        # 詳細は docs/bedrock-inference-profiles.md を参照。
        generated_text = converse_text(
            model_id=model_id,
            prompt=prompt,
            max_tokens=1024,
            temperature=0.3,
            client=bedrock_client,
        )

    metadata = extract_json(generated_text)
    if not metadata:
        # パース失敗時はラベルからデフォルトメタデータを生成
        logger.warning("Failed to parse Bedrock response as JSON, using fallback metadata")
        metadata = _generate_fallback_metadata(labels)

    # 必須フィールドの補完
    metadata = _ensure_required_fields(metadata, labels)

    return metadata


def _generate_fallback_metadata(labels: list[dict]) -> dict:
    """ラベルからフォールバックメタデータを生成する

    Args:
        labels: Rekognition ラベルのリスト

    Returns:
        dict: フォールバックメタデータ
    """
    label_names = [label["name"] for label in labels]

    return {
        "product_category": "Uncategorized",
        "color": "Unknown",
        "material": "Unknown",
        "style_attributes": [],
        "suggested_tags": label_names[:10],
    }


def _ensure_required_fields(metadata: dict, labels: list[dict]) -> dict:
    """必須フィールドが存在することを保証する

    Args:
        metadata: 生成されたメタデータ
        labels: Rekognition ラベルのリスト

    Returns:
        dict: 必須フィールドが補完されたメタデータ
    """
    label_names = [label["name"] for label in labels]

    if "product_category" not in metadata or not metadata["product_category"]:
        metadata["product_category"] = "Uncategorized"

    if "color" not in metadata or not metadata["color"]:
        metadata["color"] = "Unknown"

    if "material" not in metadata or not metadata["material"]:
        metadata["material"] = "Unknown"

    if "style_attributes" not in metadata or not isinstance(metadata["style_attributes"], list):
        metadata["style_attributes"] = []

    if "suggested_tags" not in metadata or not isinstance(metadata["suggested_tags"], list):
        metadata["suggested_tags"] = label_names[:10]

    return metadata


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """小売 / EC カタログメタデータ生成 Lambda

    Rekognition ラベルから Bedrock で構造化カタログメタデータを生成し、
    JSON 形式で S3 出力する。

    Args:
        event: 前ステップからの入力
            {"file_key": "...", "labels": [...]}

    Returns:
        dict: status, file_key, catalog_metadata, output_key
    """
    output_writer = OutputWriter.from_env()
    model_id = os.environ.get("BEDROCK_MODEL_ID", "apac.amazon.nova-lite-v1:0")
    file_key = event["file_key"]
    labels = event.get("labels", [])

    logger.info(
        "Catalog metadata generation started: file_key=%s, label_count=%d, output=%s",
        file_key,
        len(labels),
        output_writer.target_description,
    )

    # Bedrock でカタログメタデータ生成
    bedrock_client = boto3.client("bedrock-runtime")
    catalog_metadata = generate_catalog_metadata(bedrock_client, model_id, file_key, labels)

    # 出力キー生成（日付パーティション付き）
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    output_key = f"catalog/{now.strftime('%Y/%m/%d')}/{file_stem}_metadata.json"

    # メタデータ JSON を出力先（標準 S3 または FSx for ONTAP S3 AP）に書き込み
    output_data = {
        "file_key": file_key,
        "catalog_metadata": catalog_metadata,
        "labels_used": labels,
        "model_id": model_id,
        "generated_at": now.isoformat(),
    }

    output_writer.put_json(key=output_key, data=output_data)

    logger.info(
        "Catalog metadata generation completed: file_key=%s, output_uri=%s, category=%s",
        file_key,
        output_writer.build_s3_uri(output_key),
        catalog_metadata.get("product_category", "Unknown"),
    )

    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="catalog_metadata")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "retail-catalog"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return {
        "status": "SUCCESS",
        "file_key": file_key,
        "catalog_metadata": catalog_metadata,
        "output_key": output_key,
    }
