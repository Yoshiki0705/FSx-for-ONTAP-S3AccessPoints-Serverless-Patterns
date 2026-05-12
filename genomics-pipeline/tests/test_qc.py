"""UC7 ゲノミクス / バイオインフォマティクス QC Lambda ユニットテスト

ストリーミング QC、品質メトリクス計算、エラーハンドリングをテストする。
Lambda ハンドラーの入出力形式、S3ApHelper ストリーミングダウンロード、
正常系・異常系の品質チェックを検証する。

Requirements: 13.1, 13.2
"""

from __future__ import annotations

import os
import re
import sys
from unittest.mock import MagicMock, patch

import pytest

# shared モジュールと UC7 関数のパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from functions.qc.handler import (
    FastqParseError,
    _parse_fastq_records,
    _streaming_text_lines,
)


# =========================================================================
# _parse_fastq_records テスト
# =========================================================================


class TestParseFastqRecords:
    """FASTQ レコードパースのテスト"""

    def test_single_record(self):
        """単一レコードが正しくパースされること"""
        lines = [
            "@READ_000001",
            "ATGCATGCATGC",
            "+",
            "IIIIIIIIIIII",  # ASCII 73 - 33 = 40 (Phred score)
        ]
        result = _parse_fastq_records(iter(lines), max_records=100)

        assert result["total_reads"] == 1
        assert result["average_quality_score"] == 40.0
        # GC content: 6 G/C out of 12 = 50%
        assert result["gc_content_percentage"] == 50.0
        assert result["sequence_length_distribution"]["min"] == 12
        assert result["sequence_length_distribution"]["max"] == 12
        assert result["sequence_length_distribution"]["mean"] == 12.0

    def test_multiple_records(self):
        """複数レコードが正しくパースされること"""
        lines = [
            "@READ_001",
            "AAAA",
            "+",
            "IIII",  # quality 40
            "@READ_002",
            "GGGGGG",
            "+",
            "######",  # ASCII 35 - 33 = 2 (Phred score)
        ]
        result = _parse_fastq_records(iter(lines), max_records=100)

        assert result["total_reads"] == 2
        # GC: 0 from first (4 A's) + 6 from second (6 G's) = 6/10 = 60%
        assert result["gc_content_percentage"] == 60.0
        # Sequence lengths: 4 and 6
        assert result["sequence_length_distribution"]["min"] == 4
        assert result["sequence_length_distribution"]["max"] == 6
        assert result["sequence_length_distribution"]["mean"] == 5.0

    def test_max_records_limit(self):
        """max_records で読み取りレコード数が制限されること"""
        lines = []
        for i in range(10):
            lines.extend([
                f"@READ_{i:03d}",
                "ATGC",
                "+",
                "IIII",
            ])
        result = _parse_fastq_records(iter(lines), max_records=5)

        assert result["total_reads"] == 5

    def test_empty_input_raises_error(self):
        """空入力で FastqParseError が発生すること"""
        with pytest.raises(FastqParseError, match="No valid FASTQ records"):
            _parse_fastq_records(iter([]), max_records=100)

    def test_header_only_raises_error(self):
        """ヘッダーのみ（不完全レコード）で FastqParseError が発生すること"""
        lines = ["@READ_001", "ATGC"]  # 4行揃わない
        with pytest.raises(FastqParseError, match="No valid FASTQ records"):
            _parse_fastq_records(iter(lines), max_records=100)

    def test_invalid_header_skipped(self):
        """不正なヘッダー行のレコードがスキップされること"""
        lines = [
            "INVALID_HEADER",  # @ で始まらない
            "ATGC",
            "+",
            "IIII",
            "@VALID_READ",
            "GGCC",
            "+",
            "IIII",
        ]
        result = _parse_fastq_records(iter(lines), max_records=100)

        # 不正ヘッダーのレコードはスキップされ、有効なレコードのみカウント
        assert result["total_reads"] == 1

    def test_invalid_separator_skipped(self):
        """不正なセパレータ行のレコードがスキップされること"""
        lines = [
            "@READ_001",
            "ATGC",
            "INVALID",  # + で始まらない
            "IIII",
            "@READ_002",
            "GGCC",
            "+",
            "IIII",
        ]
        result = _parse_fastq_records(iter(lines), max_records=100)

        assert result["total_reads"] == 1

    def test_gc_content_all_gc(self):
        """全て GC の配列で gc_content_percentage が 100% になること"""
        lines = [
            "@READ_001",
            "GGGGCCCC",
            "+",
            "IIIIIIII",
        ]
        result = _parse_fastq_records(iter(lines), max_records=100)

        assert result["gc_content_percentage"] == 100.0

    def test_gc_content_no_gc(self):
        """GC を含まない配列で gc_content_percentage が 0% になること"""
        lines = [
            "@READ_001",
            "AAAATTTT",
            "+",
            "IIIIIIII",
        ]
        result = _parse_fastq_records(iter(lines), max_records=100)

        assert result["gc_content_percentage"] == 0.0

    def test_quality_score_calculation(self):
        """品質スコアが正しく計算されること (Phred+33)"""
        # ASCII '!' = 33, so Phred score = 0
        # ASCII 'I' = 73, so Phred score = 40
        lines = [
            "@READ_001",
            "ATGC",
            "+",
            "!!!!",  # All quality 0
        ]
        result = _parse_fastq_records(iter(lines), max_records=100)

        assert result["average_quality_score"] == 0.0

    def test_pass_filter_rate(self):
        """フィルタ通過率が正しく計算されること"""
        lines = [
            "@READ_001",
            "ATGC",
            "+",
            "IIII",  # quality 40 (above default threshold 20)
            "@READ_002",
            "ATGC",
            "+",
            "!!!!",  # quality 0 (below threshold)
        ]
        result = _parse_fastq_records(iter(lines), max_records=100)

        assert result["pass_filter_rate"] == 0.5

    def test_variable_length_sequences(self):
        """異なる長さの配列が正しく処理されること"""
        lines = [
            "@READ_001",
            "AT",
            "+",
            "II",
            "@READ_002",
            "ATGCATGC",
            "+",
            "IIIIIIII",
            "@READ_003",
            "ATGCATGCATGCATGC",
            "+",
            "IIIIIIIIIIIIIIII",
        ]
        result = _parse_fastq_records(iter(lines), max_records=100)

        assert result["total_reads"] == 3
        assert result["sequence_length_distribution"]["min"] == 2
        assert result["sequence_length_distribution"]["max"] == 16


# =========================================================================
# _streaming_text_lines テスト
# =========================================================================


class TestStreamingTextLines:
    """ストリーミングテキスト行変換のテスト"""

    def test_plain_text_streaming(self):
        """非圧縮テキストのストリーミングが正しく動作すること"""
        mock_s3ap = MagicMock()
        chunks = [
            b"@READ_001\nATGC\n+\nIIII\n",
            b"@READ_002\nGGCC\n+\nIIII\n",
        ]
        mock_s3ap.streaming_download.return_value = iter(chunks)

        lines = list(_streaming_text_lines(mock_s3ap, "test.fastq"))

        assert "@READ_001" in lines
        assert "ATGC" in lines
        assert "@READ_002" in lines
        assert "GGCC" in lines

    def test_chunk_boundary_handling(self):
        """チャンク境界をまたぐ行が正しく処理されること"""
        mock_s3ap = MagicMock()
        # 行の途中でチャンクが分割される
        chunks = [
            b"@READ_001\nAT",
            b"GC\n+\nIIII\n",
        ]
        mock_s3ap.streaming_download.return_value = iter(chunks)

        lines = list(_streaming_text_lines(mock_s3ap, "test.fastq"))

        assert "@READ_001" in lines
        assert "ATGC" in lines
        assert "+" in lines
        assert "IIII" in lines


# =========================================================================
# Lambda ハンドラーテスト (mock)
# =========================================================================


class TestQcHandler:
    """QC Lambda ハンドラーのテスト"""

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
        "QC_SAMPLE_SIZE": "100",
    })
    @patch("functions.qc.handler.OutputWriter")
    @patch("functions.qc.handler.S3ApHelper")
    def test_handler_success(self, mock_s3ap_cls, mock_output_writer_class):
        """正常系: FASTQ ファイルの QC が成功すること"""
        from functions.qc.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap

        # ストリーミングダウンロードのモック
        fastq_data = b"@READ_001\nATGCATGC\n+\nIIIIIIII\n@READ_002\nGGCCAAGG\n+\nIIIIIIII\n"
        mock_s3ap.streaming_download.return_value = iter([fastq_data])

        mock_writer = MagicMock()
        mock_output_writer_class.from_env.return_value = mock_writer

        event = {"Key": "samples/sample_001.fastq", "Size": 5000}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "SUCCESS"
        assert result["file_key"] == "samples/sample_001.fastq"
        assert "quality_metrics" in result
        assert result["quality_metrics"]["total_reads"] == 2
        assert "output_key" in result
        assert result["output_key"].endswith(".json")

        # OutputWriter に書き込まれたことを確認
        mock_writer.put_json.assert_called_once()

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.qc.handler.OutputWriter")
    @patch("functions.qc.handler.S3ApHelper")
    def test_handler_empty_file_error(self, mock_s3ap_cls, mock_output_writer_class):
        """異常系: 空ファイルで ERROR ステータスが返ること"""
        from functions.qc.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap
        mock_s3ap.streaming_download.return_value = iter([b""])

        event = {"Key": "samples/empty.fastq", "Size": 0}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "ERROR"
        assert result["file_key"] == "samples/empty.fastq"
        assert "error" in result
        assert result["error_type"] == "FastqParseError"

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.qc.handler.OutputWriter")
    @patch("functions.qc.handler.S3ApHelper")
    def test_handler_s3_download_error(self, mock_s3ap_cls, mock_output_writer_class):
        """異常系: S3 ダウンロードエラーで ERROR ステータスが返ること"""
        from functions.qc.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap
        mock_s3ap.streaming_download.side_effect = Exception("Connection timeout")

        event = {"Key": "samples/sample.fastq", "Size": 100}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "ERROR"
        assert result["file_key"] == "samples/sample.fastq"
        assert "Connection timeout" in result["error"]

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.qc.handler.OutputWriter")
    @patch("functions.qc.handler.S3ApHelper")
    def test_handler_output_key_has_date_partition(self, mock_s3ap_cls, mock_output_writer_class):
        """出力キーに日付パーティションが含まれること"""
        from functions.qc.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap

        fastq_data = b"@READ_001\nATGC\n+\nIIII\n"
        mock_s3ap.streaming_download.return_value = iter([fastq_data])

        mock_writer = MagicMock()
        mock_output_writer_class.from_env.return_value = mock_writer

        event = {"Key": "samples/sample_001.fastq", "Size": 100}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "SUCCESS"
        # 日付パーティション YYYY/MM/DD を確認
        assert re.search(r"\d{4}/\d{2}/\d{2}", result["output_key"])
        assert result["output_key"].startswith("qc/")

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.qc.handler.OutputWriter")
    @patch("functions.qc.handler.S3ApHelper")
    def test_handler_gz_file_stem(self, mock_s3ap_cls, mock_output_writer_class):
        """.fastq.gz ファイルのステムが正しく処理されること"""
        import gzip

        from functions.qc.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap

        # gzip 圧縮された FASTQ データを生成
        fastq_text = b"@READ_001\nATGC\n+\nIIII\n"
        fastq_gz_data = gzip.compress(fastq_text)
        mock_s3ap.streaming_download.return_value = iter([fastq_gz_data])

        mock_writer = MagicMock()
        mock_output_writer_class.from_env.return_value = mock_writer

        event = {"Key": "samples/sample_001.fastq.gz", "Size": 100}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "SUCCESS"
        # .fastq.gz の場合、stem は sample_001 になる
        assert "sample_001_qc.json" in result["output_key"]
