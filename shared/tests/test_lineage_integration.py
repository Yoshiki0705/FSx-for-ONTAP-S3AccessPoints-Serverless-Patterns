"""shared.integrations.lineage_integration ユニットテスト.

Data Lineage オプトイン統合ヘルパーの動作を検証する。
- LINEAGE_TABLE 未設定時はスキップ（オプトイン制御）
- LINEAGE_TABLE 設定時は LineageTracker.record() が呼ばれる
- 書き込み失敗時にメイン処理を中断しない
"""

import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.integrations.lineage_integration import (
    LineageContext,
    _is_lineage_enabled,
    _get_lineage_tracker,
    track_lineage,
)


class TestIsLineageEnabled:
    """_is_lineage_enabled() のテスト."""

    def test_not_enabled_when_env_not_set(self, monkeypatch):
        """LINEAGE_TABLE 未設定時は False を返す."""
        monkeypatch.delenv("LINEAGE_TABLE", raising=False)
        assert _is_lineage_enabled() is False

    def test_not_enabled_when_env_empty(self, monkeypatch):
        """LINEAGE_TABLE が空文字列の場合は False を返す."""
        monkeypatch.setenv("LINEAGE_TABLE", "")
        assert _is_lineage_enabled() is False

    def test_not_enabled_when_env_whitespace(self, monkeypatch):
        """LINEAGE_TABLE がスペースのみの場合は False を返す."""
        monkeypatch.setenv("LINEAGE_TABLE", "   ")
        assert _is_lineage_enabled() is False

    def test_enabled_when_env_set(self, monkeypatch):
        """LINEAGE_TABLE が設定されている場合は True を返す."""
        monkeypatch.setenv("LINEAGE_TABLE", "fsxn-s3ap-data-lineage")
        assert _is_lineage_enabled() is True


class TestGetLineageTracker:
    """_get_lineage_tracker() のテスト."""

    def test_returns_none_when_not_enabled(self, monkeypatch):
        """LINEAGE_TABLE 未設定時は None を返す."""
        monkeypatch.delenv("LINEAGE_TABLE", raising=False)
        assert _get_lineage_tracker() is None

    @patch("shared.integrations.lineage_integration._is_lineage_enabled", return_value=True)
    def test_returns_none_on_creation_error(self, mock_enabled, monkeypatch):
        """LineageTracker の生成に失敗した場合は None を返す."""
        monkeypatch.setenv("LINEAGE_TABLE", "test-table")

        with patch(
            "shared.lineage.LineageTracker",
            side_effect=Exception("connection error"),
        ):
            result = _get_lineage_tracker()
            assert result is None


class TestTrackLineageDecorator:
    """track_lineage() デコレータのテスト."""

    def test_skips_when_lineage_not_enabled(self, monkeypatch):
        """LINEAGE_TABLE 未設定時はデコレートされた関数の動作に影響しない."""
        monkeypatch.delenv("LINEAGE_TABLE", raising=False)

        @track_lineage(uc_id="test-uc")
        def my_handler(event, context):
            return {
                "source_file_key": "/vol1/test.pdf",
                "output_keys": ["s3://bucket/out.json"],
                "status": "success",
            }

        result = my_handler({}, None)
        assert result["status"] == "success"
        assert result["source_file_key"] == "/vol1/test.pdf"

    def test_records_lineage_when_enabled(self, monkeypatch):
        """LINEAGE_TABLE 設定時に LineageTracker.record() が呼ばれる."""
        monkeypatch.setenv("LINEAGE_TABLE", "test-lineage-table")

        mock_tracker = MagicMock()
        mock_tracker.record.return_value = "test-lineage-id"

        with patch(
            "shared.integrations.lineage_integration._get_lineage_tracker",
            return_value=mock_tracker,
        ):

            @track_lineage(uc_id="legal-compliance")
            def my_handler(event, context):
                return {
                    "source_file_key": "/vol1/legal/contract.pdf",
                    "execution_arn": "arn:aws:states:us-east-1:123:execution:test",
                    "output_keys": ["s3://bucket/output.json"],
                    "status": "success",
                }

            result = my_handler({}, None)

        assert result["status"] == "success"
        mock_tracker.record.assert_called_once()
        call_args = mock_tracker.record.call_args[0][0]
        assert call_args.source_file_key == "/vol1/legal/contract.pdf"
        assert call_args.uc_id == "legal-compliance"
        assert call_args.status == "success"
        assert call_args.output_keys == ["s3://bucket/output.json"]
        assert call_args.duration_ms >= 0

    def test_does_not_interrupt_on_write_failure(self, monkeypatch):
        """Lineage 書き込み失敗時にメイン処理の戻り値が正常に返る."""
        monkeypatch.setenv("LINEAGE_TABLE", "test-lineage-table")

        mock_tracker = MagicMock()
        mock_tracker.record.side_effect = Exception("DynamoDB write failed")

        with patch(
            "shared.integrations.lineage_integration._get_lineage_tracker",
            return_value=mock_tracker,
        ):

            @track_lineage(uc_id="test-uc")
            def my_handler(event, context):
                return {
                    "source_file_key": "/vol1/test.pdf",
                    "output_keys": ["s3://bucket/out.json"],
                    "status": "success",
                }

            # Should NOT raise even though record() fails
            result = my_handler({}, None)

        assert result["status"] == "success"
        assert result["source_file_key"] == "/vol1/test.pdf"

    def test_records_failed_status_on_exception(self, monkeypatch):
        """デコレートされた関数が例外を raise した場合、status="failed" で記録する."""
        monkeypatch.setenv("LINEAGE_TABLE", "test-lineage-table")

        mock_tracker = MagicMock()
        mock_tracker.record.return_value = "test-lineage-id"

        with patch(
            "shared.integrations.lineage_integration._get_lineage_tracker",
            return_value=mock_tracker,
        ):

            @track_lineage(uc_id="test-uc")
            def my_handler(event, context):
                raise RuntimeError("Processing failed")

            # Pass event with source_file_key so decorator can extract it from args
            event = {
                "source_file_key": "/vol1/test.pdf",
                "execution_arn": "arn:test",
                "output_keys": [],
            }
            with pytest.raises(RuntimeError, match="Processing failed"):
                my_handler(event, None)

        mock_tracker.record.assert_called_once()
        call_args = mock_tracker.record.call_args[0][0]
        assert call_args.status == "failed"
        assert call_args.source_file_key == "/vol1/test.pdf"

    def test_skips_when_result_not_dict(self, monkeypatch):
        """戻り値が dict でない場合は Lineage 記録をスキップする."""
        monkeypatch.setenv("LINEAGE_TABLE", "test-lineage-table")

        mock_tracker = MagicMock()

        with patch(
            "shared.integrations.lineage_integration._get_lineage_tracker",
            return_value=mock_tracker,
        ):

            @track_lineage(uc_id="test-uc")
            def my_handler(event, context):
                return "not a dict"

            result = my_handler({}, None)

        assert result == "not a dict"
        mock_tracker.record.assert_not_called()

    def test_skips_when_no_source_key(self, monkeypatch):
        """戻り値に source_file_key がない場合は Lineage 記録をスキップする."""
        monkeypatch.setenv("LINEAGE_TABLE", "test-lineage-table")

        mock_tracker = MagicMock()

        with patch(
            "shared.integrations.lineage_integration._get_lineage_tracker",
            return_value=mock_tracker,
        ):

            @track_lineage(uc_id="test-uc")
            def my_handler(event, context):
                return {"output_keys": [], "status": "success"}

            result = my_handler({}, None)

        assert result["status"] == "success"
        mock_tracker.record.assert_not_called()


class TestLineageContext:
    """LineageContext コンテキストマネージャーのテスト."""

    def test_skips_when_lineage_not_enabled(self, monkeypatch):
        """LINEAGE_TABLE 未設定時は記録をスキップする."""
        monkeypatch.delenv("LINEAGE_TABLE", raising=False)

        with LineageContext(
            uc_id="test-uc",
            source_file_key="/vol1/test.pdf",
            execution_arn="arn:test",
        ) as lctx:
            lctx.output_keys = ["s3://bucket/out.json"]
            lctx.status = "success"

        # lineage_id は None（記録されていない）
        assert lctx.lineage_id is None

    def test_records_lineage_when_enabled(self, monkeypatch):
        """LINEAGE_TABLE 設定時に Lineage が記録される."""
        monkeypatch.setenv("LINEAGE_TABLE", "test-lineage-table")

        mock_tracker = MagicMock()
        mock_tracker.record.return_value = "/vol1/test.pdf#2026-01-01T00:00:00.000Z"

        with patch(
            "shared.integrations.lineage_integration._get_lineage_tracker",
            return_value=mock_tracker,
        ):
            with LineageContext(
                uc_id="legal-compliance",
                source_file_key="/vol1/test.pdf",
                execution_arn="arn:aws:states:us-east-1:123:execution:test",
            ) as lctx:
                lctx.output_keys = ["s3://bucket/output.json"]
                lctx.status = "success"

        mock_tracker.record.assert_called_once()
        call_args = mock_tracker.record.call_args[0][0]
        assert call_args.source_file_key == "/vol1/test.pdf"
        assert call_args.uc_id == "legal-compliance"
        assert call_args.status == "success"
        assert call_args.output_keys == ["s3://bucket/output.json"]

    def test_does_not_interrupt_on_write_failure(self, monkeypatch):
        """Lineage 書き込み失敗時にコンテキスト内の処理は正常に完了する."""
        monkeypatch.setenv("LINEAGE_TABLE", "test-lineage-table")

        mock_tracker = MagicMock()
        mock_tracker.record.side_effect = Exception("DynamoDB write failed")

        with patch(
            "shared.integrations.lineage_integration._get_lineage_tracker",
            return_value=mock_tracker,
        ):
            result = None
            with LineageContext(
                uc_id="test-uc",
                source_file_key="/vol1/test.pdf",
            ) as lctx:
                lctx.status = "success"
                result = "processing completed"

        # メイン処理の結果は正常
        assert result == "processing completed"

    def test_sets_failed_status_on_exception(self, monkeypatch):
        """コンテキスト内で例外が発生した場合、status="failed" で記録する."""
        monkeypatch.setenv("LINEAGE_TABLE", "test-lineage-table")

        mock_tracker = MagicMock()
        mock_tracker.record.return_value = "test-id"

        with patch(
            "shared.integrations.lineage_integration._get_lineage_tracker",
            return_value=mock_tracker,
        ):
            with pytest.raises(RuntimeError, match="Processing error"):
                with LineageContext(
                    uc_id="test-uc",
                    source_file_key="/vol1/test.pdf",
                ) as lctx:
                    lctx.status = "success"
                    raise RuntimeError("Processing error")

        mock_tracker.record.assert_called_once()
        call_args = mock_tracker.record.call_args[0][0]
        assert call_args.status == "failed"

    def test_measures_duration(self, monkeypatch):
        """処理時間が正しく計測される."""
        monkeypatch.setenv("LINEAGE_TABLE", "test-lineage-table")

        mock_tracker = MagicMock()
        mock_tracker.record.return_value = "test-id"

        with patch(
            "shared.integrations.lineage_integration._get_lineage_tracker",
            return_value=mock_tracker,
        ):
            import time

            with LineageContext(
                uc_id="test-uc",
                source_file_key="/vol1/test.pdf",
            ) as lctx:
                time.sleep(0.01)  # 10ms
                lctx.status = "success"

        call_args = mock_tracker.record.call_args[0][0]
        # duration_ms should be at least 10ms
        assert call_args.duration_ms >= 10

    def test_write_failure_logs_warning(self, monkeypatch, caplog):
        """書き込み失敗時に警告ログが出力される."""
        monkeypatch.setenv("LINEAGE_TABLE", "test-lineage-table")

        mock_tracker = MagicMock()
        mock_tracker.record.side_effect = Exception("DynamoDB timeout")

        with patch(
            "shared.integrations.lineage_integration._get_lineage_tracker",
            return_value=mock_tracker,
        ):
            with caplog.at_level(logging.WARNING):
                with LineageContext(
                    uc_id="test-uc",
                    source_file_key="/vol1/test.pdf",
                ) as lctx:
                    lctx.status = "success"

        assert "Failed to record lineage" in caplog.text
        assert "DynamoDB timeout" in caplog.text
