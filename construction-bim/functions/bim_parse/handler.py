"""建設 / AEC BIM パース Lambda ハンドラ

IFC ファイルからメタデータ（project_name, building_elements_count, floor_count,
coordinate_system, ifc_schema_version）を抽出する。
前バージョンとの差分検出（element additions, deletions, modifications）を実行する。
パース失敗時は status: "INVALID" で返却しワークフロー継続する。

IFC (Industry Foundation Classes) は ISO-10303-21 (STEP) ベースのテキスト形式。
HEADER セクションから FILE_SCHEMA（IFC バージョン）、DATA セクションから
IFCPROJECT（プロジェクト名）、IFCBUILDINGSTOREY（階数）、エンティティ数を抽出する。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    OUTPUT_BUCKET: S3 出力バケット名
    PREVIOUS_METADATA_PREFIX: 前バージョンメタデータの S3 プレフィックス
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath

import boto3

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


class IfcParseError(Exception):
    """IFC ファイルパースエラー"""

    pass


def parse_ifc_metadata(content: str) -> dict:
    """IFC ファイルからメタデータを抽出する

    IFC (ISO-10303-21) テキスト形式をパースし、以下のメタデータを抽出:
    - project_name: IFCPROJECT エンティティから
    - building_elements_count: 全 IFC エンティティ数
    - floor_count: IFCBUILDINGSTOREY エンティティ数
    - coordinate_system: IFCGEOMETRICREPRESENTATIONCONTEXT から
    - ifc_schema_version: FILE_SCHEMA から

    Args:
        content: IFC ファイルの内容（テキスト）

    Returns:
        dict: 抽出されたメタデータ

    Raises:
        IfcParseError: パースに失敗した場合
    """
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")

    # 基本的な IFC ファイル検証
    if "ISO-10303-21" not in content and "FILE_SCHEMA" not in content:
        raise IfcParseError("Not a valid IFC file: missing ISO-10303-21 header")

    metadata = {
        "project_name": "",
        "building_elements_count": 0,
        "floor_count": 0,
        "coordinate_system": "unknown",
        "ifc_schema_version": "unknown",
    }

    # FILE_SCHEMA からバージョン抽出
    schema_match = re.search(
        r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", content, re.IGNORECASE
    )
    if schema_match:
        metadata["ifc_schema_version"] = schema_match.group(1)

    # DATA セクションの抽出
    data_match = re.search(r"\bDATA\s*;(.*?)(?:\bENDSEC\s*;|$)", content, re.DOTALL)
    data_section = data_match.group(1) if data_match else content

    # エンティティ行のカウント（#N=IFC... パターン）
    entity_pattern = re.compile(r"^#\d+=\s*IFC\w+", re.MULTILINE)
    entities = entity_pattern.findall(data_section)
    metadata["building_elements_count"] = len(entities)

    # IFCBUILDINGSTOREY のカウント
    storey_pattern = re.compile(r"^#\d+=\s*IFCBUILDINGSTOREY\b", re.MULTILINE)
    storeys = storey_pattern.findall(data_section)
    metadata["floor_count"] = len(storeys)

    # IFCPROJECT からプロジェクト名抽出
    project_match = re.search(
        r"#\d+=\s*IFCPROJECT\s*\([^,]*,[^,]*,[^,]*,'([^']*)'",
        data_section,
        re.IGNORECASE,
    )
    if project_match:
        metadata["project_name"] = project_match.group(1)
    else:
        # 代替パターン: IFCPROJECT の 5 番目のパラメータ
        project_alt = re.search(
            r"#\d+=\s*IFCPROJECT\s*\('([^']*)'",
            data_section,
            re.IGNORECASE,
        )
        if project_alt:
            metadata["project_name"] = project_alt.group(1)

    # IFCGEOMETRICREPRESENTATIONCONTEXT から座標系抽出
    # パターン: IFCGEOMETRICREPRESENTATIONCONTEXT('ContextIdentifier', ...)
    coord_match = re.search(
        r"IFCGEOMETRICREPRESENTATIONCONTEXT\s*\(\s*'([^']*)'",
        data_section,
        re.IGNORECASE,
    )
    if coord_match:
        coord_value = coord_match.group(1)
        if coord_value:
            metadata["coordinate_system"] = coord_value

    # EPSG パターンの検索（代替）
    if metadata["coordinate_system"] == "unknown":
        epsg_match = re.search(r"EPSG:\d+", content, re.IGNORECASE)
        if epsg_match:
            metadata["coordinate_system"] = epsg_match.group(0)

    return metadata


def compute_version_diff(current_metadata: dict, previous_metadata: dict | None) -> dict:
    """前バージョンとの差分を計算する

    現在のメタデータと前バージョンのメタデータを比較し、
    要素の追加・削除・変更数を算出する。

    Args:
        current_metadata: 現在のメタデータ
        previous_metadata: 前バージョンのメタデータ（None の場合は初回）

    Returns:
        dict: version_diff (elements_added, elements_deleted, elements_modified)
    """
    if previous_metadata is None:
        return {
            "elements_added": current_metadata.get("building_elements_count", 0),
            "elements_deleted": 0,
            "elements_modified": 0,
        }

    current_count = current_metadata.get("building_elements_count", 0)
    previous_count = previous_metadata.get("building_elements_count", 0)

    # 差分計算ロジック:
    # - 要素数が増加: 追加された要素
    # - 要素数が減少: 削除された要素
    # - フロア数やプロジェクト名の変更: 変更された要素
    diff = current_count - previous_count

    elements_added = max(0, diff)
    elements_deleted = max(0, -diff)

    # 変更検出: メタデータフィールドの差異をカウント
    elements_modified = 0
    compare_fields = ["project_name", "floor_count", "coordinate_system"]
    for field in compare_fields:
        current_val = current_metadata.get(field)
        previous_val = previous_metadata.get(field)
        if current_val != previous_val:
            elements_modified += 1

    return {
        "elements_added": elements_added,
        "elements_deleted": elements_deleted,
        "elements_modified": elements_modified,
    }


def _get_previous_metadata(
    s3_client, output_bucket: str, file_key: str, prefix: str
) -> dict | None:
    """前バージョンのメタデータを S3 から取得する

    Args:
        s3_client: boto3 S3 クライアント
        output_bucket: 出力バケット名
        file_key: ファイルキー
        prefix: メタデータプレフィックス

    Returns:
        dict | None: 前バージョンのメタデータ、または None
    """
    file_stem = PurePosixPath(file_key).stem
    metadata_prefix = f"{prefix}{file_stem}/"

    try:
        response = s3_client.list_objects_v2(
            Bucket=output_bucket,
            Prefix=metadata_prefix,
            MaxKeys=10,
        )
        contents = response.get("Contents", [])
        if not contents:
            return None

        # 最新のメタデータを取得
        latest = sorted(contents, key=lambda x: x["LastModified"], reverse=True)[0]
        with xray_subsegment(

            name="s3_getobject",

            annotations={"service_name": "s3", "operation": "GetObject", "use_case": "construction-bim"},

        ):

            obj = s3_client.get_object(Bucket=output_bucket, Key=latest["Key"])
        data = json.loads(obj["Body"].read().decode("utf-8"))
        return data.get("metadata", None)

    except Exception as e:
        logger.warning("Failed to get previous metadata: %s", e)
        return None


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """IFC ファイルメタデータ抽出 + バージョン差分検出

    Input:
        {"Key": "models/building_A_v3.ifc", "Size": 209715200, ...}

    Output:
        {
            "status": "SUCCESS" | "INVALID",
            "file_key": "...",
            "metadata": {...},
            "version_diff": {...},
            "output_key": "..."
        }
    """
    file_key = event["Key"]
    file_size = event.get("Size", 0)

    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    output_bucket = os.environ["OUTPUT_BUCKET"]
    prev_prefix = os.environ.get("PREVIOUS_METADATA_PREFIX", "metadata/history/")

    logger.info(
        "BIM Parse started: file_key=%s, size=%d",
        file_key,
        file_size,
    )

    # IFC ファイル取得
    try:
        response = s3ap.get_object(file_key)
        body = response["Body"]
        content = body.read().decode("utf-8", errors="replace")
        body.close()
    except Exception as e:
        logger.error("Failed to read IFC file %s: %s", file_key, e)
        return {
            "status": "INVALID",
            "file_key": file_key,
            "error": f"Failed to read file: {e}",
            "metadata": {},
            "version_diff": {},
        }

    # メタデータ抽出
    try:
        metadata = parse_ifc_metadata(content)
    except IfcParseError as e:
        logger.warning("IFC parse failed for %s: %s", file_key, e)
        return {
            "status": "INVALID",
            "file_key": file_key,
            "error": str(e),
            "metadata": {},
            "version_diff": {},
        }

    # 前バージョンとの差分検出
    s3_client = boto3.client("s3")
    previous_metadata = _get_previous_metadata(
        s3_client, output_bucket, file_key, prev_prefix
    )
    version_diff = compute_version_diff(metadata, previous_metadata)

    # 出力キー生成
    now = datetime.now(timezone.utc)
    file_stem = PurePosixPath(file_key).stem
    output_key = f"metadata/{now.strftime('%Y/%m/%d')}/{file_stem}.json"

    # 結果を S3 出力バケットに書き込み
    result = {
        "status": "SUCCESS",
        "file_key": file_key,
        "metadata": metadata,
        "version_diff": version_diff,
        "output_key": output_key,
        "extracted_at": now.isoformat(),
    }

    s3_client.put_object(
        Bucket=output_bucket,
        Key=output_key,
        Body=json.dumps(result, default=str, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
    )

    logger.info(
        "BIM Parse completed: file_key=%s, elements=%d, floors=%d, diff=%s",
        file_key,
        metadata["building_elements_count"],
        metadata["floor_count"],
        version_diff,
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="bim_parse")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "construction-bim"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return result
