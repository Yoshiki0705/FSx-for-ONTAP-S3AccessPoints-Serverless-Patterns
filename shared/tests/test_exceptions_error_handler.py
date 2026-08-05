"""lambda_error_handler の契約テスト

このデコレータは以前、未処理例外を飲み込んで `{"statusCode": 500, ...}` を返して
いた。Lambda は正常終了するため、呼び出し側からは**成功**に見える。

このリポジトリのハンドラはすべて Step Functions のタスクか EventBridge の
ターゲットで、戻り値の statusCode を読む利用者は存在しない（リポジトリ全体を
確認済み: statusCode を参照するステートマシンは無く、API Gateway イベントを持つ
唯一のテンプレートはこのデコレータを使っていない）。その結果:

- Step Functions は失敗したタスクを成功と判定し次へ進む
- 各ステートマシンの States.TaskFailed の Retry / Catch が一度も発火しない
- EventBridge のリトライと DLQ も働かない

現在の契約は「診断ログを残してから再送出する」。ここではその両方を固定する。
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from shared.exceptions import lambda_error_handler


def _context():
    ctx = MagicMock()
    ctx.aws_request_id = "req-abc"
    return ctx


class TestLambdaErrorHandlerLogging:
    """ログ出力の検証（caplog を使うため property テストとは分離）"""

    def test_logs_stack_trace_before_reraising(self, caplog):
        """再送出する前にスタックトレースを ERROR で記録することを検証する

        再送出だけしてログを消すと、Step Functions のエラーには型と文字列しか
        乗らず、どこで落ちたか分からなくなる。
        """

        @lambda_error_handler
        def failing_handler(event, context):
            raise RuntimeError("boom")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(RuntimeError, match="boom"):
                failing_handler({}, _context())

        assert caplog.text, "the failure was not logged at all"
        assert "failing_handler" in caplog.text, "the handler name is missing from the log"
        assert "Traceback" in caplog.text, "the stack trace is missing from the log"
        assert "boom" in caplog.text

    def test_does_not_swallow_into_a_status_code(self):
        """500 辞書を返さないことを検証する

        これが復活すると Lambda が正常終了し、Step Functions は失敗を成功と
        判定して次のステートへ進む。
        """

        @lambda_error_handler
        def failing_handler(event, context):
            raise ValueError("nope")

        with pytest.raises(ValueError):
            result = failing_handler({}, _context())
            # ここに到達した場合、戻り値の形を報告して落とす
            pytest.fail(f"exception was swallowed, returned: {result!r}")

    def test_preserves_the_original_exception_type(self):
        """例外型を包み直さないことを検証する

        ステートマシンの Catch は ErrorEquals で型名を見る。ここで包み直すと
        パターン側の Catch が一致しなくなる。
        """

        class PatternSpecificError(RuntimeError):
            pass

        @lambda_error_handler
        def failing_handler(event, context):
            raise PatternSpecificError("specific")

        with pytest.raises(PatternSpecificError):
            failing_handler({}, _context())

    def test_successful_return_is_untouched(self):
        """正常時は戻り値をそのまま通すことを検証する"""

        @lambda_error_handler
        def ok_handler(event, context):
            return {"total_objects": 3, "objects": []}

        assert ok_handler({}, _context()) == {"total_objects": 3, "objects": []}

    def test_preserves_function_metadata(self):
        """functools.wraps によりハンドラ名が保たれることを検証する

        ログの %s に出る名前と、Lambda の Handler 設定解決の両方に関わる。
        """

        @lambda_error_handler
        def named_handler(event, context):
            return None

        assert named_handler.__name__ == "named_handler"
