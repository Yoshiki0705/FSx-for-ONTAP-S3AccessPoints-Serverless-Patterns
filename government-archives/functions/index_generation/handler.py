"""UC16 Government Archives Index Generation Lambda

OpenSearch に墨消し済みテキスト + メタデータをインデックスする。
OpenSearchMode により Serverless / Managed / None に対応。

Environment Variables:
    OUTPUT_BUCKET: 出力先 S3 バケット
    OPENSEARCH_MODE: "serverless" | "managed" | "none"
    OPENSEARCH_ENDPOINT: OpenSearch Collection/Domain エンドポイント
    OPENSEARCH_INDEX_NAME: インデックス名 (default: "government-archives")
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)


def _build_index_document(
    document_key: str,
    clearance_level: str,
    redacted_text: str,
    pii_count: int,
    language: str,
) -> dict[str, Any]:
    """OpenSearch インデックス用ドキュメントを構築する。"""
    return {
        "document_key": document_key,
        "clearance_level": clearance_level,
        "content": redacted_text,
        "pii_count": pii_count,
        "language": language,
        "content_length": len(redacted_text),
    }


def _index_to_opensearch(
    endpoint: str, index_name: str, doc_id: str, document: dict[str, Any]
) -> bool:
    """OpenSearch に index API でドキュメントを保存する。

    opensearch-py ライブラリが利用可能な場合に使用（Lambda Layer で提供）。
    利用不可の場合は Skip して True を返す。
    """
    try:
        from opensearchpy import OpenSearch, RequestsHttpConnection
        from requests_aws4auth import AWS4Auth

        credentials = boto3.Session().get_credentials()
        region = os.environ.get("AWS_REGION", "ap-northeast-1")
        awsauth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            region,
            "aoss",  # Serverless
            session_token=credentials.token,
        )

        client = OpenSearch(
            hosts=[{"host": endpoint, "port": 443}],
            http_auth=awsauth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            timeout=30,
        )

        response = client.index(
            index=index_name,
            id=doc_id,
            body=document,
        )
        logger.info("Indexed to OpenSearch: %s", response)
        return True
    except ImportError:
        logger.warning("opensearch-py not available, skipping indexing")
        return False
    except Exception as e:
        logger.error("OpenSearch indexing failed: %s", e)
        return False


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """UC16 Index Generation Lambda ハンドラ。

    Input:
        {
            "document_key": "...",
            "redacted_text_key": "...",
            "clearance_level": "...",
            "pii_count": int,
            "language": "en"
        }

    Output:
        {"document_key": str, "indexed": bool, "index_name": str}
    """
    output_bucket = os.environ["OUTPUT_BUCKET"]
    opensearch_mode = os.environ.get("OPENSEARCH_MODE", "none")
    opensearch_endpoint = os.environ.get("OPENSEARCH_ENDPOINT", "")
    index_name = os.environ.get("OPENSEARCH_INDEX_NAME", "government-archives")

    document_key = event.get("document_key", "")
    redacted_text_key = event.get("redacted_text_key", "")

    # none モードの場合はスキップ
    if opensearch_mode == "none" or not opensearch_endpoint:
        logger.info(
            "UC16 IndexGeneration skipped: mode=%s, endpoint=%s",
            opensearch_mode,
            bool(opensearch_endpoint),
        )
        return {
            "document_key": document_key,
            "indexed": False,
            "reason": "OpenSearch disabled",
            "index_name": index_name,
        }

    # 墨消し済みテキストを取得
    s3_client = boto3.client("s3")
    try:
        response = s3_client.get_object(Bucket=output_bucket, Key=redacted_text_key)
        redacted_text = response["Body"].read().decode("utf-8")
    except Exception as e:
        logger.error("Failed to read redacted text: %s", e)
        redacted_text = ""

    # インデックスドキュメント構築
    doc = _build_index_document(
        document_key=document_key,
        clearance_level=event.get("clearance_level", "public"),
        redacted_text=redacted_text,
        pii_count=event.get("pii_count", 0),
        language=event.get("language", "en"),
    )

    # OpenSearch インデックス
    doc_id = document_key.replace("/", "_")
    indexed = _index_to_opensearch(opensearch_endpoint, index_name, doc_id, doc)

    logger.info(
        "UC16 IndexGeneration: document=%s, indexed=%s, mode=%s",
        document_key,
        indexed,
        opensearch_mode,
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="index_generation")
    metrics.set_dimension("UseCase", "government-archives")
    metrics.set_dimension("OpenSearchMode", opensearch_mode)
    metrics.put_metric("DocumentsIndexed", 1.0 if indexed else 0.0, "Count")
    metrics.flush()

    return {
        "document_key": document_key,
        "indexed": indexed,
        "index_name": index_name,
        "opensearch_mode": opensearch_mode,
    }
