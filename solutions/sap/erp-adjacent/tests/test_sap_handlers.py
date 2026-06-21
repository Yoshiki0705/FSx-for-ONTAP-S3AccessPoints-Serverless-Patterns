"""SAP/ERP Adjacent — Lambda ハンドラーのユニットテスト"""

from __future__ import annotations

import importlib.util
import os
from unittest.mock import MagicMock, patch


def _load_handler(function_name: str):
    """指定した関数のハンドラーモジュールをロード"""
    handler_path = os.path.join(os.path.dirname(__file__), "..", "functions", function_name, "handler.py")
    spec = importlib.util.spec_from_file_location(f"sap_{function_name}_handler", handler_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, spec


class TestDiscovery:
    """SAP Discovery Lambda のテスト"""

    @patch.dict(
        os.environ,
        {
            "S3_ACCESS_POINT_ALIAS": "test-sap-s3ap",
            "FILE_PREFIX": "idoc-export/",
            "MAX_FILES": "100",
        },
    )
    def test_discovery_categorizes_idoc(self):
        """IDoc ファイルが正しくカテゴリ分類される"""
        module, _ = _load_handler("discovery")

        mock_response = {
            "Contents": [
                {
                    "Key": "idoc-export/ORDERS_20260520.idoc",
                    "Size": 4096,
                    "LastModified": MagicMock(isoformat=lambda: "2026-05-20T00:00:00"),
                },
                {
                    "Key": "idoc-export/INVOIC_20260520.txt",
                    "Size": 2048,
                    "LastModified": MagicMock(isoformat=lambda: "2026-05-20T00:00:00"),
                },
            ],
            "IsTruncated": False,
        }

        with patch.object(module.s3_client, "list_objects_v2", return_value=mock_response):
            result = module.handler({}, None)

        assert result["status"] == "completed"
        assert result["object_count"] == 2
        categories = [obj["category"] for obj in result["objects"]]
        assert "sap_idoc" in categories

    @patch.dict(
        os.environ,
        {
            "S3_ACCESS_POINT_ALIAS": "test-sap-s3ap",
            "FILE_PREFIX": "edi-inbound/",
            "MAX_FILES": "50",
        },
    )
    def test_discovery_categorizes_edi(self):
        """EDI ファイルが正しくカテゴリ分類される"""
        module, _ = _load_handler("discovery")

        mock_response = {
            "Contents": [
                {
                    "Key": "edi-inbound/PO_850.x12",
                    "Size": 1024,
                    "LastModified": MagicMock(isoformat=lambda: "2026-05-20T00:00:00"),
                },
            ],
            "IsTruncated": False,
        }

        with patch.object(module.s3_client, "list_objects_v2", return_value=mock_response):
            result = module.handler({}, None)

        assert result["status"] == "completed"
        assert result["objects"][0]["category"] == "edi_document"

    @patch.dict(
        os.environ,
        {
            "S3_ACCESS_POINT_ALIAS": "test-sap-s3ap",
            "FILE_PREFIX": "hulft-landing/",
            "MAX_FILES": "100",
        },
    )
    def test_discovery_categorizes_hulft(self):
        """HULFT ファイルが正しくカテゴリ分類される"""
        module, _ = _load_handler("discovery")

        mock_response = {
            "Contents": [
                {
                    "Key": "hulft-landing/hulft_transfer_001.csv",
                    "Size": 8192,
                    "LastModified": MagicMock(isoformat=lambda: "2026-05-20T00:00:00"),
                },
            ],
            "IsTruncated": False,
        }

        with patch.object(module.s3_client, "list_objects_v2", return_value=mock_response):
            result = module.handler({}, None)

        assert result["status"] == "completed"
        assert result["objects"][0]["category"] == "hulft_transfer"

    @patch.dict(
        os.environ,
        {
            "S3_ACCESS_POINT_ALIAS": "test-sap-s3ap",
            "FILE_PREFIX": "batch-output/",
            "MAX_FILES": "100",
        },
    )
    def test_discovery_categorizes_batch(self):
        """バッチ出力ファイルが正しくカテゴリ分類される"""
        module, _ = _load_handler("discovery")

        mock_response = {
            "Contents": [
                {
                    "Key": "batch-output/batch_job_20260520.csv",
                    "Size": 16384,
                    "LastModified": MagicMock(isoformat=lambda: "2026-05-20T00:00:00"),
                },
            ],
            "IsTruncated": False,
        }

        with patch.object(module.s3_client, "list_objects_v2", return_value=mock_response):
            result = module.handler({}, None)

        assert result["status"] == "completed"
        assert result["objects"][0]["category"] == "batch_output"

    @patch.dict(
        os.environ,
        {
            "S3_ACCESS_POINT_ALIAS": "test-sap-s3ap",
            "FILE_PREFIX": "data/",
            "MAX_FILES": "5",
        },
    )
    def test_discovery_respects_max_files(self):
        """MAX_FILES 制限が正しく適用される"""
        module, _ = _load_handler("discovery")

        mock_response = {
            "Contents": [
                {
                    "Key": f"data/file_{i:03d}.csv",
                    "Size": 1024,
                    "LastModified": MagicMock(isoformat=lambda: "2026-05-20T00:00:00"),
                }
                for i in range(10)
            ],
            "IsTruncated": False,
        }

        with patch.object(module.s3_client, "list_objects_v2", return_value=mock_response):
            result = module.handler({}, None)

        assert result["object_count"] <= 5


class TestReport:
    """SAP Report Lambda のテスト"""

    @patch.dict(os.environ, {"OUTPUT_BUCKET": "", "SNS_TOPIC_ARN": ""})
    def test_report_aggregates_results(self):
        """処理結果が正しく集約される"""
        module, _ = _load_handler("report")

        event = {
            "processed_results": [
                {"key": "file1.csv", "status": "completed", "category": "sap_idoc"},
                {"key": "file2.csv", "status": "completed", "category": "sap_idoc"},
                {"key": "file3.csv", "status": "error", "category": "edi_document", "error": "Read failed"},
            ]
        }

        result = module.handler(event, None)

        assert result["status"] == "completed"
        assert result["report"]["summary"]["total_files"] == 3
        assert result["report"]["summary"]["succeeded"] == 2
        assert result["report"]["summary"]["failed"] == 1
        assert result["report"]["summary"]["success_rate_pct"] == 66.7
        assert result["report"]["category_breakdown"]["sap_idoc"] == 2
        assert result["report"]["category_breakdown"]["edi_document"] == 1

    @patch.dict(os.environ, {"OUTPUT_BUCKET": "", "SNS_TOPIC_ARN": ""})
    def test_report_handles_empty_results(self):
        """空の結果リストを正しく処理する"""
        module, _ = _load_handler("report")

        result = module.handler({"processed_results": []}, None)

        assert result["status"] == "completed"
        assert result["report"]["summary"]["total_files"] == 0
        assert result["report"]["summary"]["success_rate_pct"] == 0
