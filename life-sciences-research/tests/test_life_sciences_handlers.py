"""Life Sciences Research — Lambda ハンドラーのユニットテスト"""

from __future__ import annotations

import importlib.util
import os
from unittest.mock import MagicMock, patch


def _load_handler(function_name: str):
    """指定した関数のハンドラーモジュールをロード"""
    handler_path = os.path.join(
        os.path.dirname(__file__), "..", "functions", function_name, "handler.py"
    )
    spec = importlib.util.spec_from_file_location(
        f"lifesci_{function_name}_handler", handler_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, spec


class TestClassification:
    """Classification Lambda のテスト"""

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-lifesci-s3ap"})
    def test_classify_microscopy_confocal(self):
        """共焦点顕微鏡画像が正しく分類される"""
        module, _ = _load_handler("classification")

        result = module.handler(
            {"key": "images/confocal/sample-001.nd2", "category": "microscopy_image"},
            None,
        )

        assert result["status"] == "completed"
        assert result["classification"]["classification"] == "confocal_microscopy"
        assert result["classification"]["confidence"] > 0.0

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-lifesci-s3ap"})
    def test_classify_microscopy_fluorescence(self):
        """蛍光顕微鏡画像が正しく分類される"""
        module, _ = _load_handler("classification")

        result = module.handler(
            {"key": "images/fluorescence_exp1.tiff", "category": "microscopy_image"},
            None,
        )

        assert result["status"] == "completed"
        assert result["classification"]["classification"] == "fluorescence_microscopy"

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-lifesci-s3ap"})
    def test_classify_microscopy_electron(self):
        """電子顕微鏡画像が正しく分類される"""
        module, _ = _load_handler("classification")

        result = module.handler(
            {"key": "images/sem_sample_001.tiff", "category": "microscopy_image"},
            None,
        )

        assert result["status"] == "completed"
        assert result["classification"]["classification"] == "electron_microscopy"

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-lifesci-s3ap"})
    def test_classify_sequence_fastq(self):
        """FASTQ ファイルが raw_sequencing に分類される"""
        module, _ = _load_handler("classification")

        result = module.handler(
            {"key": "sequences/sample_R1.fastq", "category": "sequence_data"},
            None,
        )

        assert result["status"] == "completed"
        assert result["classification"]["classification"] == "raw_sequencing"
        assert result["classification"]["confidence"] == 0.95

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-lifesci-s3ap"})
    def test_classify_sequence_vcf(self):
        """VCF ファイルが variant_calls に分類される"""
        module, _ = _load_handler("classification")

        result = module.handler(
            {"key": "variants/patient_001.vcf", "category": "sequence_data"},
            None,
        )

        assert result["status"] == "completed"
        assert result["classification"]["classification"] == "variant_calls"

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-lifesci-s3ap"})
    def test_classify_sequence_bam(self):
        """BAM ファイルが aligned_reads に分類される"""
        module, _ = _load_handler("classification")

        result = module.handler(
            {"key": "alignments/sample.bam", "category": "sequence_data"},
            None,
        )

        assert result["status"] == "completed"
        assert result["classification"]["classification"] == "aligned_reads"

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-lifesci-s3ap"})
    def test_classify_document_protocol(self):
        """プロトコル文書が正しく分類される"""
        module, _ = _load_handler("classification")

        result = module.handler(
            {"key": "docs/protocol_western_blot.pdf", "category": "document"},
            None,
        )

        assert result["status"] == "completed"
        assert result["classification"]["classification"] == "experimental_protocol"

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-lifesci-s3ap"})
    def test_classify_document_paper(self):
        """論文が正しく分類される"""
        module, _ = _load_handler("classification")

        result = module.handler(
            {"key": "papers/manuscript_draft_v3.pdf", "category": "document"},
            None,
        )

        assert result["status"] == "completed"
        assert result["classification"]["classification"] == "research_paper"

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-lifesci-s3ap"})
    def test_classify_experiment_timeseries(self):
        """時系列実験データが正しく分類される"""
        module, _ = _load_handler("classification")

        result = module.handler(
            {"key": "experiments/kinetics_assay_001.csv", "category": "experiment_data"},
            None,
        )

        assert result["status"] == "completed"
        assert result["classification"]["classification"] == "time_series"

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-lifesci-s3ap"})
    def test_classify_unknown_category(self):
        """未知カテゴリは unclassified を返す"""
        module, _ = _load_handler("classification")

        result = module.handler(
            {"key": "misc/random_file.xyz", "category": "unknown"},
            None,
        )

        assert result["status"] == "completed"
        assert result["classification"]["classification"] == "unclassified"
        assert result["classification"]["confidence"] == 0.0
