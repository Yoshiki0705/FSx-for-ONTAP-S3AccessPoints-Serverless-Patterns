"""Unit tests for the ENABLE_S3AP_APP_SIGNAL opt-in gate.

emit_s3ap_app_signal がデフォルト OFF であり、明示的な opt-in のときだけ
EMF レコードとメトリクスを出すことを検証する。実 AWS 呼び出しなし、
ネットワークなし、決定的。
"""

from __future__ import annotations

import json
from unittest.mock import patch

from shared.s3ap_app_signal import emit_s3ap_app_signal


class TestAppSignalGate:
    """ENABLE_S3AP_APP_SIGNAL による emit の有効/無効を検証する。"""

    def test_unset_emits_nothing(self, monkeypatch):
        """変数未設定のとき、何も出力せず空 dict を返す。"""
        monkeypatch.delenv("ENABLE_S3AP_APP_SIGNAL", raising=False)

        with patch("builtins.print") as mock_print:
            result = emit_s3ap_app_signal(object_key="data/object.txt", operation="GET")

        assert result == {}
        mock_print.assert_not_called()

    def test_false_emits_nothing(self, monkeypatch):
        """変数が "false" のとき、未設定と同じく何も出力しない。"""
        monkeypatch.setenv("ENABLE_S3AP_APP_SIGNAL", "false")

        with patch("builtins.print") as mock_print:
            result = emit_s3ap_app_signal(object_key="data/object.txt", operation="GET")

        assert result == {}
        mock_print.assert_not_called()

    def test_true_emits_signal_and_emf_record(self, monkeypatch):
        """変数が "true" のとき、従来どおり join key を返し EMF レコードを出力する。"""
        monkeypatch.setenv("ENABLE_S3AP_APP_SIGNAL", "true")

        with patch("builtins.print") as mock_print:
            result = emit_s3ap_app_signal(object_key="data/object.txt", operation="GET")

        # The signal dict carries the join key, unchanged from the pre-gate behaviour.
        assert result["s3ap_join_key"] == "GET|data/object.txt"
        assert result["s3ap_object_key"] == "data/object.txt"
        assert result["s3ap_operation"] == "GET"

        # Exactly one EMF record was printed; it is valid JSON in the
        # FSxONTAPAppSignals namespace and carries the S3apOperations metric.
        mock_print.assert_called_once()
        record = json.loads(mock_print.call_args[0][0])
        assert record["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "FSxONTAPAppSignals"
        assert record["S3apOperations"] == 1
        assert record["s3ap_join_key"] == "GET|data/object.txt"
