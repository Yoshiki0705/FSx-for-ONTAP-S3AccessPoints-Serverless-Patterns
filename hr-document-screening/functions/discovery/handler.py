"""HR (UC27) Discovery Lambda ハンドラ

S3 Access Point から履歴書・職務経歴書 (PDF/Word/Excel) を検出し、
職種タイプ + 提出日で分類した Manifest を生成する。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    RESUME_PREFIX: 履歴書プレフィックス (default: "hr/resumes/")
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

# 履歴書の対応拡張子
RESUME_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".doc", ".docx", ".xls", ".xlsx"})

# ファイルタイプ定数
FILE_TYPE_RESUME = "resume"

# 職種タイプ分類キーワード
POSITION_TYPE_KEYWORDS: dict[str, str] = {
    "engineer": "engineering",
    "エンジニア": "engineering",
    "開発": "engineering",
    "developer": "engineering",
    "sales": "sales",
    "営業": "sales",
    "marketing": "marketing",
    "マーケティング": "marketing",
    "admin": "administration",
    "事務": "administration",
    "管理": "administration",
    "design": "design",
    "デザイン": "design",
}

# 日付パターン
DATE_PATTERN = re.compile(r"(\d{4})[-/]?(\d{2})[-/]?(\d{2})")


def classify_file(key: str, resume_prefix: str) -> str | None:
    """ファイルキーを分類する。

    Args:
        key: S3 オブジェクトキー
        resume_prefix: 履歴書プレフィックス

    Returns:
        "resume" | None
    """
    if not key:
        return None

    dot_index = key.rfind(".")
    if dot_index == -1:
        return None

    extension = key[dot_index:].lower()

    if resume_prefix and key.startswith(resume_prefix):
        if extension in RESUME_EXTENSIONS:
            return FILE_TYPE_RESUME
        return None

    return None


def detect_position_type(key: str) -> str:
    """ファイルパスから職種タイプを推定する。

    Args:
        key: S3 オブジェクトキー

    Returns:
        str: 職種タイプ
    """
    key_lower = key.lower()
    for keyword, position_type in POSITION_TYPE_KEYWORDS.items():
        if keyword in key_lower:
            return position_type
    return "general"


def extract_submission_date(key: str) -> str | None:
    """ファイルパスから提出日を抽出する。

    Args:
        key: S3 オブジェクトキー

    Returns:
        str | None: ISO 日付文字列 (YYYY-MM-DD) or None
    """
    match = DATE_PATTERN.search(key)
    if match:
        year, month, day = match.group(1), match.group(2), match.group(3)
        try:
            datetime(int(year), int(month), int(day))
            return f"{year}-{month}-{day}"
        except ValueError:
            pass
    return None


def validate_s3ap_connectivity(s3ap: S3ApHelper) -> dict | None:
    """S3 Access Point への接続性を検証する。"""
    try:
        s3ap.list_objects(prefix="", suffix="", max_keys=1)
        return None
    except S3ApHelperError as e:
        logger.error("S3 AP connectivity failed: %s", str(e))
        return {
            "statusCode": 503,
            "body": json.dumps(
                {
                    "error": "S3 Access Point unreachable",
                    "error_type": "ConnectivityError",
                    "error_code": e.error_code or "Unknown",
                    "access_point": s3ap.bucket_param,
                    "message": str(e),
                }
            ),
        }
    except Exception as e:
        logger.error("Unexpected S3 AP error: %s", str(e))
        return {
            "statusCode": 503,
            "body": json.dumps(
                {
                    "error": "S3 Access Point unreachable",
                    "error_type": "ConnectivityError",
                    "error_code": "UnexpectedError",
                    "access_point": s3ap.bucket_param,
                    "message": str(e),
                }
            ),
        }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """HR Document Screening Discovery Lambda

    Returns:
        dict: manifest_key, total_objects, resumes
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"]))
    resume_prefix = os.environ.get("RESUME_PREFIX", "hr/resumes/")

    logger.info(
        "HR Discovery started: access_point=%s, prefix=%r",
        os.environ["S3_ACCESS_POINT"],
        resume_prefix,
    )

    # S3 AP 接続性バリデーション
    with xray_subsegment(
        name="s3ap_connectivity_validation",
        annotations={"use_case": "hr-document-screening"},
    ):
        connectivity_error = validate_s3ap_connectivity(s3ap)
        if connectivity_error is not None:
            return connectivity_error

    # オブジェクト一覧取得
    resumes: list[dict] = []

    with xray_subsegment(
        name="s3ap_list_resumes",
        annotations={"prefix": resume_prefix},
    ):
        objects = s3ap.list_objects(prefix=resume_prefix, suffix="")

    for obj in objects:
        key = obj.get("Key", "")
        file_type = classify_file(key, resume_prefix)
        if file_type == FILE_TYPE_RESUME:
            obj["file_type"] = file_type
            obj["position_type"] = detect_position_type(key)
            obj["submission_date"] = extract_submission_date(key)
            resumes.append(obj)

    logger.info("HR Discovery: found %d resumes", len(resumes))

    # Manifest 生成
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "use_case": "hr-document-screening",
        "total_objects": len(resumes),
        "total_size_bytes": sum(obj.get("Size", 0) for obj in resumes),
        "resume_count": len(resumes),
        "position_types": list({r.get("position_type", "general") for r in resumes}),
        "resume_prefix": resume_prefix,
        "objects": resumes,
    }

    manifest_key = f"manifests/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{context.aws_request_id}.json"

    # Note: Output bucket enforces SSE-KMS encryption via bucket default encryption policy
    # (configured in template.yaml OutputBucket resource)
    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    # EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", "hr-document-screening")
    metrics.put_metric("FilesProcessed", float(len(resumes)), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(resumes),
        "resumes": resumes,
    }
