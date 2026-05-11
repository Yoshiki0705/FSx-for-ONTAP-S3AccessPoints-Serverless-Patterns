"""UC7 ゲノミクス / バイオインフォマティクス バリアント集計 ユニットテスト

VCF パース、バリアント統計集計、Cross-Region Comprehend Medical 呼び出しを
テストする。Lambda ハンドラーの入出力形式、エラーハンドリング、
ヘルパー関数のロジックを検証する。

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

from functions.variant_aggregation.handler import (
    VcfParseError,
    _is_snp,
    _is_transition,
    _parse_vcf_records,
    _streaming_text_lines,
)


# =========================================================================
# _is_snp テスト
# =========================================================================


class TestIsSnp:
    """SNP 判定のテスト"""

    def test_single_base_substitution_is_snp(self):
        """1 塩基置換が SNP と判定されること"""
        assert _is_snp("A", "G") is True
        assert _is_snp("C", "T") is True

    def test_insertion_is_not_snp(self):
        """挿入が SNP でないと判定されること"""
        assert _is_snp("A", "AT") is False

    def test_deletion_is_not_snp(self):
        """欠失が SNP でないと判定されること"""
        assert _is_snp("AT", "A") is False

    def test_multi_base_change_is_not_snp(self):
        """複数塩基変異が SNP でないと判定されること"""
        assert _is_snp("AT", "GC") is False


# =========================================================================
# _is_transition テスト
# =========================================================================


class TestIsTransition:
    """Transition 判定のテスト"""

    def test_a_to_g_is_transition(self):
        """A→G が Transition と判定されること"""
        assert _is_transition("A", "G") is True

    def test_g_to_a_is_transition(self):
        """G→A が Transition と判定されること"""
        assert _is_transition("G", "A") is True

    def test_c_to_t_is_transition(self):
        """C→T が Transition と判定されること"""
        assert _is_transition("C", "T") is True

    def test_t_to_c_is_transition(self):
        """T→C が Transition と判定されること"""
        assert _is_transition("T", "C") is True

    def test_a_to_c_is_transversion(self):
        """A→C が Transversion（非 Transition）と判定されること"""
        assert _is_transition("A", "C") is False

    def test_a_to_t_is_transversion(self):
        """A→T が Transversion と判定されること"""
        assert _is_transition("A", "T") is False

    def test_case_insensitive(self):
        """大文字小文字を区別しないこと"""
        assert _is_transition("a", "g") is True
        assert _is_transition("c", "t") is True


# =========================================================================
# _parse_vcf_records テスト
# =========================================================================


class TestParseVcfRecords:
    """VCF レコードパースのテスト"""

    def test_single_snp(self):
        """単一 SNP レコードが正しくパースされること"""
        lines = [
            "##fileformat=VCFv4.2",
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
            "chr1\t100\t.\tA\tG\t30\tPASS\t.",
        ]
        result = _parse_vcf_records(iter(lines))

        assert result["total_variants"] == 1
        assert result["snp_count"] == 1
        assert result["indel_count"] == 0

    def test_single_indel(self):
        """単一 Indel レコードが正しくパースされること"""
        lines = [
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
            "chr1\t100\t.\tA\tAT\t30\tPASS\t.",
        ]
        result = _parse_vcf_records(iter(lines))

        assert result["total_variants"] == 1
        assert result["snp_count"] == 0
        assert result["indel_count"] == 1

    def test_mixed_variants(self):
        """SNP と Indel の混合が正しく集計されること"""
        lines = [
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
            "chr1\t100\t.\tA\tG\t30\tPASS\t.",  # SNP (transition)
            "chr1\t200\t.\tC\tT\t30\tPASS\t.",  # SNP (transition)
            "chr1\t300\t.\tA\tC\t30\tPASS\t.",  # SNP (transversion)
            "chr1\t400\t.\tA\tAT\t30\tPASS\t.",  # Indel
            "chr1\t500\t.\tGCC\tG\t30\tPASS\t.",  # Indel
        ]
        result = _parse_vcf_records(iter(lines))

        assert result["total_variants"] == 5
        assert result["snp_count"] == 3
        assert result["indel_count"] == 2
        # Ti/Tv ratio: 2 transitions / 1 transversion = 2.0
        assert result["ti_tv_ratio"] == 2.0

    def test_multi_allelic_variants(self):
        """複数 ALT アレル（カンマ区切り）が正しく処理されること"""
        lines = [
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
            "chr1\t100\t.\tA\tG,C\t30\tPASS\t.",  # 2 SNPs
        ]
        result = _parse_vcf_records(iter(lines))

        assert result["total_variants"] == 2
        assert result["snp_count"] == 2

    def test_structural_variants_skipped(self):
        """構造変異（<DEL>, <INS> 等）がスキップされること"""
        lines = [
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
            "chr1\t100\t.\tA\t<DEL>\t30\tPASS\t.",
            "chr1\t200\t.\tA\t*\t30\tPASS\t.",
            "chr1\t300\t.\tA\tG\t30\tPASS\t.",  # Valid SNP
        ]
        result = _parse_vcf_records(iter(lines))

        assert result["total_variants"] == 1
        assert result["snp_count"] == 1

    def test_header_lines_skipped(self):
        """ヘッダー行（# で始まる行）がスキップされること"""
        lines = [
            "##fileformat=VCFv4.2",
            "##INFO=<ID=DP,Number=1,Type=Integer>",
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
            "chr1\t100\t.\tA\tG\t30\tPASS\t.",
        ]
        result = _parse_vcf_records(iter(lines))

        assert result["total_variants"] == 1

    def test_empty_lines_skipped(self):
        """空行がスキップされること"""
        lines = [
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
            "",
            "chr1\t100\t.\tA\tG\t30\tPASS\t.",
            "",
        ]
        result = _parse_vcf_records(iter(lines))

        assert result["total_variants"] == 1

    def test_malformed_lines_skipped(self):
        """不正な行（フィールド不足）がスキップされること"""
        lines = [
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
            "chr1\t100",  # フィールド不足
            "chr1\t200\t.\tA\tG\t30\tPASS\t.",  # 有効
        ]
        result = _parse_vcf_records(iter(lines))

        assert result["total_variants"] == 1

    def test_no_valid_records_raises_error(self):
        """有効なレコードがない場合に VcfParseError が発生すること"""
        lines = [
            "##fileformat=VCFv4.2",
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
        ]
        with pytest.raises(VcfParseError, match="No valid variant records"):
            _parse_vcf_records(iter(lines))

    def test_ti_tv_ratio_no_transversions(self):
        """Transversion がない場合に ti_tv_ratio が 0.0 になること"""
        lines = [
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
            "chr1\t100\t.\tA\tG\t30\tPASS\t.",  # Transition only
            "chr1\t200\t.\tC\tT\t30\tPASS\t.",  # Transition only
        ]
        result = _parse_vcf_records(iter(lines))

        # All transitions, no transversions → ti_tv_ratio = 0.0
        # (because transversion_count == 0, the code returns 0.0)
        assert result["ti_tv_ratio"] == 0.0

    def test_het_hom_detection(self):
        """ヘテロ/ホモ接合性が正しく検出されること"""
        lines = [
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE",
            "chr1\t100\t.\tA\tG\t30\tPASS\t.\tGT:DP\t0/1:30",  # Het
            "chr1\t200\t.\tC\tT\t30\tPASS\t.\tGT:DP\t1/1:25",  # Hom
            "chr1\t300\t.\tG\tA\t30\tPASS\t.\tGT:DP\t0/1:20",  # Het
        ]
        result = _parse_vcf_records(iter(lines))

        assert result["total_variants"] == 3
        # het_hom_ratio: 2 het / 1 hom = 2.0
        assert result["het_hom_ratio"] == 2.0


# =========================================================================
# _streaming_text_lines テスト
# =========================================================================


class TestStreamingTextLines:
    """ストリーミングテキスト行変換のテスト"""

    def test_plain_text_streaming(self):
        """非圧縮テキストのストリーミングが正しく動作すること"""
        mock_s3ap = MagicMock()
        chunks = [
            b"#CHROM\tPOS\tID\tREF\tALT\n",
            b"chr1\t100\t.\tA\tG\n",
        ]
        mock_s3ap.streaming_download.return_value = iter(chunks)

        lines = list(_streaming_text_lines(mock_s3ap, "test.vcf"))

        assert "#CHROM\tPOS\tID\tREF\tALT" in lines
        assert "chr1\t100\t.\tA\tG" in lines

    def test_chunk_boundary_handling(self):
        """チャンク境界をまたぐ行が正しく処理されること"""
        mock_s3ap = MagicMock()
        chunks = [
            b"chr1\t100\t.\tA",
            b"\tG\t30\tPASS\t.\n",
        ]
        mock_s3ap.streaming_download.return_value = iter(chunks)

        lines = list(_streaming_text_lines(mock_s3ap, "test.vcf"))

        assert "chr1\t100\t.\tA\tG\t30\tPASS\t." in lines


# =========================================================================
# Lambda ハンドラーテスト (mock)
# =========================================================================


class TestVariantAggregationHandler:
    """バリアント集計 Lambda ハンドラーのテスト"""

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.variant_aggregation.handler.boto3")
    @patch("functions.variant_aggregation.handler.S3ApHelper")
    def test_handler_success(self, mock_s3ap_cls, mock_boto3):
        """正常系: VCF ファイルのバリアント集計が成功すること"""
        from functions.variant_aggregation.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap

        vcf_data = (
            b"##fileformat=VCFv4.2\n"
            b"#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
            b"chr1\t100\t.\tA\tG\t30\tPASS\t.\n"
            b"chr1\t200\t.\tA\tAT\t30\tPASS\t.\n"
        )
        mock_s3ap.streaming_download.return_value = iter([vcf_data])

        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        event = {"Key": "variants/sample_001.vcf", "Size": 1000}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "SUCCESS"
        assert result["file_key"] == "variants/sample_001.vcf"
        assert "variant_statistics" in result
        assert result["variant_statistics"]["total_variants"] == 2
        assert result["variant_statistics"]["snp_count"] == 1
        assert result["variant_statistics"]["indel_count"] == 1
        assert "output_key" in result

        mock_s3_client.put_object.assert_called_once()

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.variant_aggregation.handler.boto3")
    @patch("functions.variant_aggregation.handler.S3ApHelper")
    def test_handler_empty_vcf_error(self, mock_s3ap_cls, mock_boto3):
        """異常系: 有効なレコードがない VCF で ERROR ステータスが返ること"""
        from functions.variant_aggregation.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap

        vcf_data = b"##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        mock_s3ap.streaming_download.return_value = iter([vcf_data])

        event = {"Key": "variants/empty.vcf", "Size": 100}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "ERROR"
        assert result["file_key"] == "variants/empty.vcf"
        assert result["error_type"] == "VcfParseError"

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.variant_aggregation.handler.boto3")
    @patch("functions.variant_aggregation.handler.S3ApHelper")
    def test_handler_s3_error(self, mock_s3ap_cls, mock_boto3):
        """異常系: S3 ダウンロードエラーで ERROR ステータスが返ること"""
        from functions.variant_aggregation.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap
        mock_s3ap.streaming_download.side_effect = Exception("Network error")

        event = {"Key": "variants/sample.vcf", "Size": 100}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "ERROR"
        assert result["file_key"] == "variants/sample.vcf"
        assert "Network error" in result["error"]

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.variant_aggregation.handler.boto3")
    @patch("functions.variant_aggregation.handler.S3ApHelper")
    def test_handler_output_key_date_partition(self, mock_s3ap_cls, mock_boto3):
        """出力キーに日付パーティションが含まれること"""
        from functions.variant_aggregation.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap

        vcf_data = (
            b"#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
            b"chr1\t100\t.\tA\tG\t30\tPASS\t.\n"
        )
        mock_s3ap.streaming_download.return_value = iter([vcf_data])

        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        event = {"Key": "variants/sample_001.vcf", "Size": 100}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "SUCCESS"
        assert re.search(r"\d{4}/\d{2}/\d{2}", result["output_key"])
        assert result["output_key"].startswith("variants/")

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT": "test-ap-ext-s3alias",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    @patch("functions.variant_aggregation.handler.boto3")
    @patch("functions.variant_aggregation.handler.S3ApHelper")
    def test_handler_vcf_gz_file_stem(self, mock_s3ap_cls, mock_boto3):
        """.vcf.gz ファイルのステムが正しく処理されること"""
        import gzip

        from functions.variant_aggregation.handler import handler

        mock_s3ap = MagicMock()
        mock_s3ap_cls.return_value = mock_s3ap

        vcf_text = (
            b"#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
            b"chr1\t100\t.\tA\tG\t30\tPASS\t.\n"
        )
        vcf_gz_data = gzip.compress(vcf_text)
        mock_s3ap.streaming_download.return_value = iter([vcf_gz_data])

        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        event = {"Key": "variants/sample_001.vcf.gz", "Size": 100}
        context = MagicMock()

        result = handler(event, context)

        assert result["status"] == "SUCCESS"
        # .vcf.gz の場合、stem は sample_001 になる
        assert "sample_001_stats.json" in result["output_key"]


# =========================================================================
# Cross-Region Comprehend Medical テスト
# =========================================================================


class TestCrossRegionComprehendMedical:
    """Cross-Region Comprehend Medical 呼び出しのテスト"""

    @patch.dict(os.environ, {
        "OUTPUT_BUCKET": "test-output-bucket",
        "SNS_TOPIC_ARN": "arn:aws:sns:ap-northeast-1:123456789012:test-topic",
        "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0",
        "CROSS_REGION": "us-east-1",
    })
    @patch("functions.summary.handler.boto3")
    @patch("functions.summary.handler.CrossRegionClient")
    def test_comprehend_medical_cross_region_call(
        self, mock_cr_client_cls, mock_boto3
    ):
        """Cross-Region Comprehend Medical が正しく呼び出されること"""
        from functions.summary.handler import _extract_biomedical_entities

        # CrossRegionClient のモック
        mock_cr_client = MagicMock()
        mock_cr_client.detect_entities_v2.return_value = {
            "Entities": [
                {
                    "Category": "MEDICAL_CONDITION",
                    "Type": "DX_NAME",
                    "Text": "breast cancer",
                    "Score": 0.95,
                },
                {
                    "Category": "TEST_TREATMENT_PROCEDURE",
                    "Type": "TEST_NAME",
                    "Text": "BRCA1",
                    "Score": 0.88,
                },
                {
                    "Category": "MEDICATION",
                    "Type": "GENERIC_NAME",
                    "Text": "tamoxifen",
                    "Score": 0.92,
                },
            ]
        }

        result = _extract_biomedical_entities(
            mock_cr_client, "BRCA1 gene mutation associated with breast cancer"
        )

        assert "breast cancer" in result["diseases"]
        assert "BRCA1" in result["genes"]
        assert "tamoxifen" in result["medications"]
        mock_cr_client.detect_entities_v2.assert_called_once()

    def test_comprehend_medical_low_confidence_filtered(self):
        """信頼度 0.7 未満のエンティティがフィルタされること"""
        from functions.summary.handler import _extract_biomedical_entities

        mock_cr_client = MagicMock()
        mock_cr_client.detect_entities_v2.return_value = {
            "Entities": [
                {
                    "Category": "MEDICAL_CONDITION",
                    "Type": "DX_NAME",
                    "Text": "high_confidence_disease",
                    "Score": 0.9,
                },
                {
                    "Category": "MEDICAL_CONDITION",
                    "Type": "DX_NAME",
                    "Text": "low_confidence_disease",
                    "Score": 0.5,  # Below 0.7 threshold
                },
            ]
        }

        result = _extract_biomedical_entities(mock_cr_client, "test text")

        assert "high_confidence_disease" in result["diseases"]
        assert "low_confidence_disease" not in result["diseases"]

    def test_comprehend_medical_error_handled_gracefully(self):
        """Comprehend Medical エラーがグレースフルに処理されること"""
        from functions.summary.handler import _extract_biomedical_entities

        mock_cr_client = MagicMock()
        mock_cr_client.detect_entities_v2.side_effect = Exception(
            "Service unavailable"
        )

        # エラーが発生してもワークフローは停止しない
        result = _extract_biomedical_entities(mock_cr_client, "test text")

        assert result["genes"] == []
        assert result["diseases"] == []
        assert result["medications"] == []

    def test_comprehend_medical_text_truncation(self):
        """20,000 文字を超えるテキストが切り詰められること"""
        from functions.summary.handler import _extract_biomedical_entities

        mock_cr_client = MagicMock()
        mock_cr_client.detect_entities_v2.return_value = {"Entities": []}

        long_text = "A" * 25000
        _extract_biomedical_entities(mock_cr_client, long_text)

        # 呼び出し時のテキストが 20,000 文字に切り詰められていることを確認
        call_args = mock_cr_client.detect_entities_v2.call_args[0][0]
        assert len(call_args) == 20000
