"""共通例外クラスとエラーハンドリングデコレータ

全ユースケースで使用する共通例外クラスと Lambda 関数用の
エラーハンドリングデコレータを定義する。

例外クラス:
- OntapClientError: ONTAP REST API エラー (shared.ontap_client から再エクスポート)
- FsxHelperError: FSx API エラー (shared.fsx_helper から再エクスポート)
- S3ApHelperError: S3 Access Point エラー
- CrossRegionClientError: クロスリージョン API エラー

デコレータ:
- lambda_error_handler: Lambda 関数の未処理例外をキャッチし、構造化レスポンスを返す
"""

from __future__ import annotations

import functools
import json
import logging
import traceback

from shared.ontap_client import OntapClientError  # noqa: F401
from shared.fsx_helper import FsxHelperError  # noqa: F401

logger = logging.getLogger(__name__)


class S3ApHelperError(Exception):
    """S3 Access Point エラー

    Attributes:
        error_code: S3 エラーコード (例: "AccessDenied", "NoSuchKey")
    """

    def __init__(self, message: str, error_code: str | None = None):
        super().__init__(message)
        self.error_code = error_code


class CrossRegionClientError(Exception):
    """クロスリージョン API エラー

    Attributes:
        target_region: ターゲットリージョン (例: "us-east-1")
        service_name: AWS サービス名 (例: "textract", "comprehendmedical")
        original_error: 元の例外オブジェクト
    """

    def __init__(
        self,
        message: str,
        target_region: str | None = None,
        service_name: str | None = None,
        original_error: Exception | None = None,
    ):
        super().__init__(message)
        self.target_region = target_region
        self.service_name = service_name
        self.original_error = original_error


class StreamingError(Exception):
    """Kinesis ストリーミングエラー

    Attributes:
        failed_records: 失敗したレコードのリスト
        error_codes: Kinesis エラーコードのリスト
    """

    def __init__(
        self,
        message: str,
        failed_records: list | None = None,
        error_codes: list | None = None,
    ):
        super().__init__(message)
        self.failed_records = failed_records or []
        self.error_codes = error_codes or []


def lambda_error_handler(func):
    """Lambda 関数の共通エラーハンドリングデコレータ

    未処理例外をキャッチし、スタックトレースをログ出力した上で
    構造化されたエラーレスポンスを返す。

    Returns:
        dict: {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "error_type": type(e).__name__,
                "request_id": context.aws_request_id,
            })
        }
    """

    @functools.wraps(func)
    def wrapper(event, context):
        try:
            return func(event, context)
        except Exception as e:
            logger.error(
                "Unhandled exception in %s: %s\n%s",
                func.__name__,
                str(e),
                traceback.format_exc(),
            )
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "request_id": context.aws_request_id,
                }),
            }

    return wrapper
