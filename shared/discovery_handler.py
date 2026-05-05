"""共通 Discovery Lambda ハンドラ

S3 Access Point からオブジェクト一覧を取得し、Manifest JSON を生成する。
各ユースケースの Discovery Lambda はこのモジュールを継承・拡張して使用する。

Manifest JSON スキーマ:
    {
        "execution_id": str,       # Lambda aws_request_id
        "timestamp": str,          # ISO 8601 形式
        "total_objects": int,      # objects 配列の長さ
        "objects": [               # 発見されたオブジェクト一覧
            {"Key": str, "Size": int, "LastModified": str, "ETag": str}
        ]
    }

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用、省略時は S3_ACCESS_POINT を使用)
    PREFIX_FILTER: プレフィックスフィルタ (optional)
    SUFFIX_FILTER: サフィックスフィルタ (optional)
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)


def paginate_manifest(objects: list[dict], max_per_chunk: int = 10000) -> list[dict]:
    """10,000+ オブジェクト対応の Manifest ページネーション

    オブジェクト数が max_per_chunk 以下の場合は単一チャンクを返す。
    超過する場合は ceil(N / max_per_chunk) チャンクに分割し、
    全チャンクの union が元のオブジェクトリストと完全一致することを保証する。

    Args:
        objects: S3 オブジェクトのリスト
        max_per_chunk: 1 チャンクあたりの最大オブジェクト数 (デフォルト: 10,000)

    Returns:
        list[dict]: チャンクのリスト。各チャンクは以下のキーを含む:
            - chunk_index (int): 0-based チャンクインデックス
            - total_chunks (int): 全チャンク数
            - objects (list[dict]): このチャンクに含まれるオブジェクト
            - total_objects_in_chunk (int): このチャンクのオブジェクト数
    """
    n = len(objects)
    if n <= max_per_chunk:
        return [
            {
                "chunk_index": 0,
                "total_chunks": 1,
                "objects": objects,
                "total_objects_in_chunk": n,
            }
        ]

    total_chunks = math.ceil(n / max_per_chunk)
    chunks = []
    for i in range(total_chunks):
        start = i * max_per_chunk
        end = min(start + max_per_chunk, n)
        chunk_objects = objects[start:end]
        chunks.append(
            {
                "chunk_index": i,
                "total_chunks": total_chunks,
                "objects": chunk_objects,
                "total_objects_in_chunk": len(chunk_objects),
            }
        )
    return chunks


def generate_manifest(objects: list[dict], execution_id: str) -> dict:
    """Manifest JSON を生成する

    Discovery Lambda のコアロジックを抽出したヘルパー関数。
    プロパティテストで直接テスト可能。

    Args:
        objects: S3ApHelper.list_objects() の戻り値と同形式のオブジェクトリスト。
                 各要素は {"Key": str, "Size": int, "LastModified": ..., "ETag": str}。
        execution_id: 実行 ID（Lambda の aws_request_id 等）

    Returns:
        dict: Manifest JSON。以下のキーを含む:
            - execution_id (str): 実行 ID
            - timestamp (str): ISO 8601 形式のタイムスタンプ
            - total_objects (int): objects 配列の長さ
            - objects (list[dict]): オブジェクト一覧
    """
    return {
        "execution_id": execution_id,
        "timestamp": datetime.utcnow().isoformat(),
        "total_objects": len(objects),
        "objects": objects,
    }


@lambda_error_handler
def handler(event, context):
    """Discovery Lambda: S3 AP からオブジェクト一覧取得 → Manifest 生成 → S3 AP 書き出し

    Environment Variables:
        S3_ACCESS_POINT: S3 AP Alias or ARN (入力読み取り用)
        S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用、省略時は S3_ACCESS_POINT を使用)
        PREFIX_FILTER: プレフィックスフィルタ (optional)
        SUFFIX_FILTER: サフィックスフィルタ (optional)
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(
        os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"])
    )
    prefix = os.environ.get("PREFIX_FILTER", "")
    suffix = os.environ.get("SUFFIX_FILTER", "")

    logger.info(
        "Discovery started: access_point=%s, prefix=%r, suffix=%r",
        os.environ["S3_ACCESS_POINT"],
        prefix,
        suffix,
    )

    objects = s3ap.list_objects(prefix=prefix, suffix=suffix)

    manifest = generate_manifest(objects, context.aws_request_id)

    manifest_key = (
        f"manifests/{datetime.utcnow().strftime('%Y/%m/%d')}"
        f"/{context.aws_request_id}.json"
    )

    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    logger.info(
        "Discovery completed: total_objects=%d, manifest=%s",
        len(objects),
        manifest_key,
    )

    return {
        "manifest_key": manifest_key,
        "total_objects": len(objects),
    }
