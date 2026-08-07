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
import logging
import traceback

from shared.fsx_helper import FsxHelperError  # noqa: F401
from shared.ontap_client import OntapClientError  # noqa: F401

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


class TokenStorageError(Exception):
    """Task Token ストレージエラー

    DynamoDB への Task Token 保存・取得に失敗した場合に発生する。
    Correlation ID の衝突リトライ上限超過、DynamoDB サービスエラー等。

    Attributes:
        correlation_id: 関連する Correlation ID (存在する場合)
        retry_count: リトライ回数
    """

    def __init__(
        self,
        message: str,
        correlation_id: str | None = None,
        retry_count: int = 0,
    ):
        super().__init__(message)
        self.correlation_id = correlation_id
        self.retry_count = retry_count


def lambda_error_handler(func):
    """Lambda 関数の共通エラーハンドリングデコレータ

    未処理例外のスタックトレースを構造化ログに残し、そのうえで例外を再送出する。

    以前は例外を飲み込んで `{"statusCode": 500, ...}` を返していた。これは
    Lambda を正常終了させるため、呼び出し側から見ると**成功**になる。この
    リポジトリのハンドラは Step Functions のタスクと EventBridge のターゲット
    であり、いずれも戻り値の statusCode を見ない。結果として:

    - Step Functions は失敗したタスクを成功と判定し、次のステートへ進む。
      Map の `ItemsPath` が解決できずに `States.Runtime` で落ちるなど、実際の
      原因とは無関係なエラーが表面に出る。
    - 各ステートマシンが定義している `States.TaskFailed` の Retry / Catch は
      Lambda が失敗しないため一度も発火しない（死んだ設定になっていた）。
    - EventBridge のリトライと DLQ も同様に働かない。

    リポジトリ全体を調べたうえでの変更である: 戻り値の statusCode を参照している
    ステートマシンは存在せず、API Gateway イベントを持つ唯一のテンプレートは
    このデコレータを使っていない。つまり 500 辞書に依存している利用者はいない。

    HTTP レスポンス形状が必要な関数（API Gateway / AppSync の背後）では、この
    デコレータではなくハンドラ内で明示的に整形すること。

    Raises:
        Exception: ハンドラが投げた例外をそのまま再送出する
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
            raise

    return wrapper
