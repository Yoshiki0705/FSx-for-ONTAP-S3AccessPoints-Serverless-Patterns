"""NPO・非営利団体 (UC24) Discovery Lambda ハンドラ

S3 Access Point から助成金申請書（PDF, Word）および活動報告書を検出し、
プログラムエリアと提出日で分類した Manifest JSON を生成する。

ファイル分類:
    - 助成金申請書: GRANT_APPLICATION_PREFIX 配下の PDF/Word ファイル
    - 活動報告書: ACTIVITY_REPORT_PREFIX 配下の PDF/Word ファイル

S3 AP 接続性バリデーション (Requirement 13.5):
    処理開始前に S3 AP への接続を検証し、
    到達不可の場合は構造化エラーレスポンスを返す。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    GRANT_APPLICATION_PREFIX: 助成金申請書プレフィックス (default: "grant-applications/")
    ACTIVITY_REPORT_PREFIX: 活動報告書プレフィックス (default: "activity-reports/")
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone

from shared.exceptions import S3ApHelperError, lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

# 助成金申請書・活動報告書の対応拡張子
GRANT_DOC_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".docx", ".doc"})

# ドキュメントタイプ
DOC_TYPE_APPLICATION = "grant_application"
DOC_TYPE_REPORT = "activity_report"

# 日付パターン (YYYY-MM-DD or YYYY/MM/DD or YYYYMMDD in path)
DATE_PATTERN = re.compile(r"(\d{4})[-/]?(\d{2})[-/]?(\d{2})")


def classify_file(
    key: str,
    grant_application_prefix: str,
    activity_report_prefix: str,
) -> str | None:
    """ファイルキーをドキュメントタイプに分類する。

    パスプレフィックスと拡張子に基づいてファイルを分類する。

    Args:
        key: S3 オブジェクトキー
        grant_application_prefix: 助成金申請書プレフィックス
        activity_report_prefix: 活動報告書プレフィックス

    Returns:
        "grant_application" | "activity_report" | None (対象外)
    """
    if not key:
        return None

    dot_index = key.rfind(".")
    if dot_index == -1:
        return None

    extension = key[dot_index:].lower()
    if extension not in GRANT_DOC_EXTENSIONS:
        return None

    if grant_application_prefix and key.startswith(grant_application_prefix):
        return DOC_TYPE_APPLICATION

    if activity_report_prefix and key.startswith(activity_report_prefix):
        return DOC_TYPE_REPORT

    return None


def extract_program_area(key: str, prefix: str) -> str:
    """ファイルパスからプログラムエリアを抽出する。

    プレフィックス直下の最初のパスセグメントをプログラムエリアとみなす。
    例: "grant-applications/education/2025/proposal.pdf" → "education"

    Args:
        key: S3 オブジェクトキー
        prefix: ドキュメントタイプのプレフィックス

    Returns:
        str: プログラムエリア名 (抽出できない場合は "general")
    """
    if not key.startswith(prefix):
        return "general"

    relative_path = key[len(prefix) :]
    parts = relative_path.split("/")

    if len(parts) > 1 and parts[0]:
        return parts[0]

    return "general"


def extract_submission_date(key: str) -> str | None:
    """ファイルパスから提出日を抽出する。

    パス内の日付パターン (YYYY-MM-DD, YYYY/MM/DD, YYYYMMDD) を探す。

    Args:
        key: S3 オブジェクトキー

    Returns:
        str | None: ISO 日付文字列 (YYYY-MM-DD) または None
    """
    match = DATE_PATTERN.search(key)
    if match:
        year, month, day = match.group(1), match.group(2), match.group(3)
        try:
            # 妥当性チェック
            datetime(int(year), int(month), int(day))
            return f"{year}-{month}-{day}"
        except ValueError:
            pass
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
        logger.error(
            "Unexpected error during S3 AP connectivity validation: %s",
            str(e),
        )
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
    """Nonprofit Grant Management Discovery Lambda

    S3 AP から助成金申請書および活動報告書を検出し、
    プログラムエリア・提出日で分類した Manifest JSON を生成・書き出す。

    Processing Flow:
        1. S3 AP 接続性バリデーション (Req 13.5)
        2. プレフィックス設定の取得
        3. 各プレフィックスでオブジェクト一覧取得
        4. ファイル分類フィルタ適用 + メタデータ抽出
        5. Manifest JSON 生成・書き出し
        6. EMF メトリクス出力

    Returns:
        dict: manifest_key, total_objects, grant_applications, activity_reports
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"]))
    grant_application_prefix = os.environ.get("GRANT_APPLICATION_PREFIX", "grant-applications/")
    activity_report_prefix = os.environ.get("ACTIVITY_REPORT_PREFIX", "activity-reports/")

    logger.info(
        "Nonprofit Grant Discovery started: access_point=%s, grant_prefix=%r, report_prefix=%r",
        os.environ["S3_ACCESS_POINT"],
        grant_application_prefix,
        activity_report_prefix,
    )

    # Step 1: S3 AP 接続性バリデーション
    with xray_subsegment(
        name="s3ap_connectivity_validation",
        annotations={
            "service_name": "s3",
            "operation": "ConnectivityCheck",
            "use_case": "nonprofit-grant-management",
        },
    ):
        connectivity_error = validate_s3ap_connectivity(s3ap)
        if connectivity_error is not None:
            return connectivity_error

    # Step 2-3: 各プレフィックスでオブジェクト一覧取得
    grant_applications: list[dict] = []
    activity_reports: list[dict] = []

    prefixes_map = {
        DOC_TYPE_APPLICATION: (grant_application_prefix, grant_applications),
        DOC_TYPE_REPORT: (activity_report_prefix, activity_reports),
    }

    for doc_type, (prefix, doc_list) in prefixes_map.items():
        with xray_subsegment(
            name=f"s3ap_list_{doc_type}",
            annotations={
                "service_name": "s3",
                "operation": "ListObjectsV2",
                "use_case": "nonprofit-grant-management",
                "prefix": prefix,
            },
        ):
            objects = s3ap.list_objects(prefix=prefix, suffix="")

        for obj in objects:
            key = obj.get("Key", "")
            classified = classify_file(
                key,
                grant_application_prefix,
                activity_report_prefix,
            )
            if classified == doc_type:
                obj["doc_type"] = doc_type
                obj["program_area"] = extract_program_area(key, prefix)
                obj["submission_date"] = extract_submission_date(key)
                doc_list.append(obj)

    all_objects = grant_applications + activity_reports

    # プログラムエリア統計
    program_areas: dict[str, int] = {}
    for obj in grant_applications:
        area = obj.get("program_area", "general")
        program_areas[area] = program_areas.get(area, 0) + 1

    logger.info(
        "File classification: grant_applications=%d, activity_reports=%d, total=%d, program_areas=%s",
        len(grant_applications),
        len(activity_reports),
        len(all_objects),
        program_areas,
    )

    # Step 5: Manifest 生成
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "use_case": "nonprofit-grant-management",
        "total_objects": len(all_objects),
        "total_size_bytes": sum(obj.get("Size", 0) for obj in all_objects),
        "grant_application_count": len(grant_applications),
        "activity_report_count": len(activity_reports),
        "program_areas": program_areas,
        "grant_application_prefix": grant_application_prefix,
        "activity_report_prefix": activity_report_prefix,
        "objects": all_objects,
    }

    manifest_key = f"manifests/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{context.aws_request_id}.json"

    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    logger.info(
        "Nonprofit Grant Discovery completed: total_objects=%d, manifest=%s",
        len(all_objects),
        manifest_key,
    )

    # Step 6: EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="discovery")
    metrics.set_dimension("UseCase", "nonprofit-grant-management")
    metrics.put_metric("FilesProcessed", float(len(all_objects)), "Count")
    metrics.put_metric("GrantApplications", float(len(grant_applications)), "Count")
    metrics.put_metric("ActivityReports", float(len(activity_reports)), "Count")
    metrics.flush()

    return {
        "manifest_key": manifest_key,
        "total_objects": len(all_objects),
        "objects": all_objects,
        "grant_applications": grant_applications,
        "activity_reports": activity_reports,
    }
