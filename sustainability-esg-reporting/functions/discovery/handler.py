"""サステナビリティ・ESG (UC23) Discovery Lambda ハンドラ

S3 Access Point から ESG 関連文書（サステナビリティ報告書、エネルギー消費記録、
廃棄物マニフェスト）を検出し、ESG カテゴリ（Environmental/Social/Governance）で
分類した Manifest JSON を生成する。

ファイル分類:
    - Environmental: ENVIRONMENTAL_PREFIX 配下の PDF/Excel/CSV
    - Social: SOCIAL_PREFIX 配下の PDF/Excel/CSV
    - Governance: GOVERNANCE_PREFIX 配下の PDF/Excel/CSV

S3 AP 接続性バリデーション (Requirement 13.5):
    処理開始前に S3 AP への接続を検証し、
    到達不可の場合は構造化エラーレスポンスを返す。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    ENVIRONMENTAL_PREFIX: 環境カテゴリプレフィックス (default: "environmental/")
    SOCIAL_PREFIX: 社会カテゴリプレフィックス (default: "social/")
    GOVERNANCE_PREFIX: ガバナンスカテゴリプレフィックス (default: "governance/")
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from shared.exceptions import S3ApHelperError, lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

# ESG 文書の対応拡張子
ESG_DOC_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".xlsx", ".xls", ".csv", ".docx", ".doc"}
)

# ESG カテゴリ定義
ESG_CATEGORIES: tuple[str, ...] = ("environmental", "social", "governance")


def classify_file(
    key: str,
    environmental_prefix: str,
    social_prefix: str,
    governance_prefix: str,
) -> str | None:
    """ファイルキーを ESG カテゴリに分類する。

    パスプレフィックスと拡張子に基づいてファイルを分類する。

    Args:
        key: S3 オブジェクトキー
        environmental_prefix: Environmental カテゴリプレフィックス
        social_prefix: Social カテゴリプレフィックス
        governance_prefix: Governance カテゴリプレフィックス

    Returns:
        "environmental" | "social" | "governance" | None (対象外)
    """
    if not key:
        return None

    dot_index = key.rfind(".")
    if dot_index == -1:
        return None

    extension = key[dot_index:].lower()
    if extension not in ESG_DOC_EXTENSIONS:
        return None

    # プレフィックスに基づいて ESG カテゴリ分類
    if environmental_prefix and key.startswith(environmental_prefix):
        return "environmental"

    if social_prefix and key.startswith(social_prefix):
        return "social"

    if governance_prefix and key.startswith(governance_prefix):
        return "governance"

    return None


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
            "S3 Access Point connectivity validation failed: %s (error_code=%s)",
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
        logger.error(
            "Unexpected error during S3 AP connectivity validation: %s",
            str(e),
        )
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
    """Sustainability ESG Reporting Discovery Lambda

    S3 AP から ESG 関連文書を検出し、E/S/G カテゴリ別に分類した
    Manifest JSON を生成・書き出す。

    Processing Flow:
        1. S3 AP 接続性バリデーション (Req 13.5)
        2. プレフィックス設定の取得
        3. 各プレフィックスでオブジェクト一覧取得
        4. ファイル分類フィルタ適用
        5. Manifest JSON 生成・書き出し
        6. EMF メトリクス出力

    Returns:
        dict: manifest_key, total_objects, environmental_docs, social_docs, governance_docs
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"])
    )
    environmental_prefix = os.environ.get("ENVIRONMENTAL_PREFIX", "environmental/")
    social_prefix = os.environ.get("SOCIAL_PREFIX", "social/")
    governance_prefix = os.environ.get("GOVERNANCE_PREFIX", "governance/")

    logger.info(
        "ESG Discovery started: access_point=%s, "
        "environmental_prefix=%r, social_prefix=%r, governance_prefix=%r",
        os.environ["S3_ACCESS_POINT"],
        environmental_prefix,
        social_prefix,
        governance_prefix,
    )

    # Step 1: S3 AP 接続性バリデーション
    with xray_subsegment(
        name="s3ap_connectivity_validation",
        annotations={
            "service_name": "s3",
            "operation": "ConnectivityCheck",
            "use_case": "sustainability-esg-reporting",
        },
    ):
        connectivity_error = validate_s3ap_connectivity(s3ap)
        if connectivity_error is not None:
            return connectivity_error

    # Step 2-3: 各プレフィックスでオブジェクト一覧取得
    environmental_docs: list[dict] = []
    social_docs: list[dict] = []
    governance_docs: list[dict] = []

    prefixes_map = {
        "environmental": (environmental_prefix, environmental_docs),
        "social": (social_prefix, social_docs),
        "governance": (governance_prefix, governance_docs),
    }

    for category, (prefix, doc_list) in prefixes_map.items():
        with xray_subsegment(
            name=f"s3ap_list_{category}_docs",
            annotations={
                "service_name": "s3",
                "operation": "ListObjectsV2",
                "use_case": "sustainability-esg-reporting",
                "prefix": prefix,
            },
        ):
            objects = s3ap.list_objects(prefix=prefix, suffix="")

        for obj in objects:
            classified = classify_file(
                obj.get("Key", ""),
                environmental_prefix,
                social_prefix,
                governance_prefix,
            )
            if classified == category:
                obj["category"] = category
                doc_list.append(obj)

    all_objects = environmental_docs + social_docs + governance_docs

    logger.info(
        "File classification: environmental=%d, social=%d, governance=%d, total=%d",
        len(environmental_docs),
        len(social_docs),
        len(governance_docs),
        len(all_objects),
    )

    # Step 5: Manifest 生成
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "use_case": "sustainability-esg-reporting",
        "total_objects": len(all_objects),
        "total_size_bytes": sum(obj.get("Size", 0) for obj in all_objects),
        "environmental_count": len(environmental_docs),
        "social_count": len(social_docs),
        "governance_count": len(governance_docs),
        "environmental_prefix": environmental_prefix,
        "social_prefix": social_prefix,
        "governance_prefix": governance_prefix,
        "objects": all_objects,
    }

    manifest_key = (
        f"manifests/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{context.aws_request_id}.json"
    )

    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    logger.info(
        "ESG Discovery completed: total_objects=%d, manifest=%s",
        len(all_objects),
        manifest_key,
    )

    # Step 6: EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", "sustainability-esg-reporting")
    metrics.put_metric("FilesProcessed", float(len(all_objects)), "Count")
    metrics.put_metric("EnvironmentalDocs", float(len(environmental_docs)), "Count")
    metrics.put_metric("SocialDocs", float(len(social_docs)), "Count")
    metrics.put_metric("GovernanceDocs", float(len(governance_docs)), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(all_objects),
        "objects": all_objects,
        "environmental_docs": environmental_docs,
        "social_docs": social_docs,
        "governance_docs": governance_docs,
    }
