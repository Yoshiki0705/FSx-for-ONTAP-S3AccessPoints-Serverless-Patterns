"""金融・保険 OCR Lambda ハンドラ

Map ステートからドキュメント情報を受け取り、S3 AP 経由でドキュメントを取得し、
Amazon Textract で OCR を実行する。

ページ数に基づき同期 API (AnalyzeDocument) と非同期 API
(StartDocumentAnalysis) を自動選択する。

Environment Variables:
    S3_ACCESS_POINT: S3 AP Alias or ARN
"""

from __future__ import annotations

import json
import logging
import os
import time

import boto3

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)


def select_textract_api(page_count: int, threshold: int = 1) -> str:
    """Textract API の同期/非同期を選択する

    ページ数が閾値以下の場合は同期 API (AnalyzeDocument) を使用し、
    閾値を超える場合は非同期 API (StartDocumentAnalysis) を使用する。

    Args:
        page_count: ドキュメントのページ数
        threshold: 同期 API を使用する最大ページ数 (デフォルト: 1)

    Returns:
        str: "sync" (AnalyzeDocument) または "async" (StartDocumentAnalysis)
    """
    if page_count <= threshold:
        return "sync"
    return "async"


def _extract_text_sync(textract_client, document_bytes: bytes) -> str:
    """同期 Textract API (AnalyzeDocument) でテキスト抽出

    Args:
        textract_client: boto3 Textract クライアント
        document_bytes: ドキュメントのバイトデータ

    Returns:
        str: 抽出されたテキスト
    """
    response = textract_client.analyze_document(
        Document={"Bytes": document_bytes},
        FeatureTypes=["TABLES", "FORMS"],
    )

    lines = []
    for block in response.get("Blocks", []):
        if block["BlockType"] == "LINE":
            lines.append(block.get("Text", ""))

    return "\n".join(lines)


def _extract_text_async(
    textract_client, s3_bucket: str, s3_key: str
) -> str:
    """非同期 Textract API (StartDocumentAnalysis) でテキスト抽出

    Args:
        textract_client: boto3 Textract クライアント
        s3_bucket: ドキュメントが格納されている S3 バケット
        s3_key: ドキュメントの S3 キー

    Returns:
        str: 抽出されたテキスト
    """
    response = textract_client.start_document_analysis(
        DocumentLocation={
            "S3Object": {
                "Bucket": s3_bucket,
                "Name": s3_key,
            }
        },
        FeatureTypes=["TABLES", "FORMS"],
    )

    job_id = response["JobId"]
    logger.info("Textract async job started: job_id=%s", job_id)

    # ジョブ完了を待機
    while True:
        result = textract_client.get_document_analysis(JobId=job_id)
        status = result["JobStatus"]

        if status == "SUCCEEDED":
            break
        elif status == "FAILED":
            raise RuntimeError(
                f"Textract job {job_id} failed: "
                f"{result.get('StatusMessage', 'Unknown error')}"
            )

        time.sleep(5)

    # 全ページのテキストを収集
    lines = []
    for block in result.get("Blocks", []):
        if block["BlockType"] == "LINE":
            lines.append(block.get("Text", ""))

    # ページネーション対応
    next_token = result.get("NextToken")
    while next_token:
        result = textract_client.get_document_analysis(
            JobId=job_id, NextToken=next_token
        )
        for block in result.get("Blocks", []):
            if block["BlockType"] == "LINE":
                lines.append(block.get("Text", ""))
        next_token = result.get("NextToken")

    return "\n".join(lines)


@lambda_error_handler
def handler(event, context):
    """OCR Lambda: ドキュメント取得 → Textract OCR 実行

    Map ステートから以下の形式でドキュメント情報を受け取る:
        {"Key": str, "Size": int, "page_count": int (optional)}

    Returns:
        dict: document_key, extracted_text, page_count, api_mode
    """
    document_key = event["Key"]
    document_size = event.get("Size", 0)

    # ページ数の決定: イベントから取得、なければファイルサイズから推定
    # PDF の平均ページサイズ ~100KB をヒューリスティックとして使用
    page_count = event.get("page_count")
    if page_count is None:
        page_count = max(1, document_size // 100_000)

    api_mode = select_textract_api(
        page_count,
        threshold=int(os.environ.get("TEXTRACT_PAGE_THRESHOLD", "1")),
    )

    logger.info(
        "OCR processing: key=%s, size=%d, page_count=%d, api_mode=%s",
        document_key,
        document_size,
        page_count,
        api_mode,
    )

    # Textract クライアント（ap-northeast-1 非対応のため TEXTRACT_REGION で指定）
    # 参考: https://docs.aws.amazon.com/general/latest/gr/textract.html
    textract_region = os.environ.get("TEXTRACT_REGION", "us-east-1")
    textract_client = boto3.client("textract", region_name=textract_region)

    try:
        if api_mode == "sync":
            # 同期 API: ドキュメントバイトを直接渡す
            s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
            response = s3ap.get_object(document_key)
            document_bytes = response["Body"].read()

            extracted_text = _extract_text_sync(textract_client, document_bytes)
        else:
            # 非同期 API: S3 ロケーションを渡す
            # 非同期 API は S3 バケット/キーを直接参照する
            s3_bucket = os.environ["S3_ACCESS_POINT"]
            extracted_text = _extract_text_async(
                textract_client, s3_bucket, document_key
            )

    except Exception as e:
        logger.error(
            "Textract error for document %s: %s", document_key, str(e)
        )
        # エラー時はログ出力して空テキストで続行（ワークフロー全体を停止しない）
        return {
            "document_key": document_key,
            "extracted_text": "",
            "page_count": page_count,
            "api_mode": api_mode,
            "error": str(e),
        }

    return {
        "document_key": document_key,
        "extracted_text": extracted_text,
        "page_count": page_count,
        "api_mode": api_mode,
    }
