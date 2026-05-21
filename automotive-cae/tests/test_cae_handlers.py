"""Automotive CAE — Lambda ハンドラーのユニットテスト"""

from __future__ import annotations

import importlib.util
import os
from unittest.mock import MagicMock, patch



def _load_handler(function_name: str):
    """指定した関数のハンドラーモジュールをロード"""
    handler_path = os.path.join(
        os.path.dirname(__file__), "..", "functions", function_name, "handler.py"
    )
    spec = importlib.util.spec_from_file_location(f"cae_{function_name}_handler", handler_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, spec


class TestDiscovery:
    """CAE Discovery Lambda のテスト"""

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-cae-s3ap"})
    def test_discovery_filters_cae_extensions(self):
        """CAE 関連拡張子のみ返す"""
        module, spec = _load_handler("discovery")
        spec.loader.exec_module(module)

        mock_response = {
            "Contents": [
                {"Key": "sim/crash.d3plot", "Size": 1048576, "LastModified": MagicMock(isoformat=lambda: "2026-01-01T00:00:00")},
                {"Key": "sim/mesh.bdf", "Size": 524288, "LastModified": MagicMock(isoformat=lambda: "2026-01-01T00:00:00")},
                {"Key": "sim/results.csv", "Size": 4096, "LastModified": MagicMock(isoformat=lambda: "2026-01-01T00:00:00")},
                {"Key": "sim/readme.md", "Size": 1024, "LastModified": MagicMock(isoformat=lambda: "2026-01-01T00:00:00")},
            ],
            "IsTruncated": False,
        }

        with patch.object(module.s3_client, "list_objects_v2", return_value=mock_response):
            result = module.handler({"prefix": "sim/"}, None)

        assert result["status"] == "completed"
        assert result["object_count"] == 3  # .md は除外
        categories = [obj["category"] for obj in result["objects"]]
        assert "solver_output" in categories
        assert "mesh" in categories
        assert "telemetry" in categories

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-cae-s3ap"})
    def test_discovery_categorizes_correctly(self):
        """ファイルカテゴリが正しく判定される"""
        module, spec = _load_handler("discovery")
        spec.loader.exec_module(module)

        mock_response = {
            "Contents": [
                {"Key": "output.d3plot", "Size": 100, "LastModified": MagicMock(isoformat=lambda: "2026-01-01T00:00:00")},
                {"Key": "input.k", "Size": 100, "LastModified": MagicMock(isoformat=lambda: "2026-01-01T00:00:00")},
                {"Key": "log.csv", "Size": 100, "LastModified": MagicMock(isoformat=lambda: "2026-01-01T00:00:00")},
            ],
            "IsTruncated": False,
        }

        with patch.object(module.s3_client, "list_objects_v2", return_value=mock_response):
            result = module.handler({"prefix": ""}, None)

        obj_map = {obj["key"]: obj["category"] for obj in result["objects"]}
        assert obj_map["output.d3plot"] == "solver_output"
        assert obj_map["input.k"] == "mesh"
        assert obj_map["log.csv"] == "telemetry"


class TestSolverOutputParser:
    """Solver Output Parser Lambda のテスト"""

    @patch.dict(os.environ, {
        "S3_ACCESS_POINT_ALIAS": "test-cae-s3ap",
        "OUTPUT_BUCKET": "test-output-bucket",
    })
    def test_parser_extracts_metadata(self):
        """メタデータが正しく抽出される"""
        module, spec = _load_handler("solver_output_parser")
        spec.loader.exec_module(module)

        mock_body = MagicMock()
        mock_body.read.return_value = b"LS-DYNA binary header data" * 100
        mock_response = {"Body": mock_body}

        with patch.object(module.s3_client, "get_object", return_value=mock_response):
            with patch.object(module.s3_client, "put_object"):
                result = module.handler({
                    "key": "sim/crash.d3plot",
                    "extension": ".d3plot",
                    "category": "solver_output",
                    "size": 1048576,
                }, None)

        assert result["status"] == "completed"
        assert result["metadata"]["solver_type"] == "LS-DYNA"
        assert result["metadata"]["category"] == "solver_output"


class TestQualityCheck:
    """Quality Check Lambda のテスト"""

    @patch.dict(os.environ, {"BEDROCK_MODEL_ID": "amazon.nova-pro-v1:0"})
    def test_quality_pass_for_valid_file(self):
        """正常ファイルは PASS"""
        module, spec = _load_handler("quality_check")
        spec.loader.exec_module(module)

        event = {
            "key": "sim/crash.d3plot",
            "parsed": {
                "metadata": {
                    "file_size": 1048576,
                    "category": "solver_output",
                    "solver_type": "LS-DYNA",
                }
            }
        }

        # Bedrock をモック
        with patch.object(module.bedrock_client, "invoke_model") as mock_bedrock:
            mock_body = MagicMock()
            mock_body.read.return_value = b'{"output":{"message":{"content":[{"text":"Analysis looks good."}]}}}'
            mock_bedrock.return_value = {"body": mock_body}

            result = module.handler(event, None)

        assert result["status"] == "completed"
        assert result["quality_score"] == "PASS"
        assert len(result["issues"]) == 0

    @patch.dict(os.environ, {"BEDROCK_MODEL_ID": "amazon.nova-pro-v1:0"})
    def test_quality_fail_for_empty_file(self):
        """空ファイルは FAIL"""
        module, spec = _load_handler("quality_check")
        spec.loader.exec_module(module)

        event = {
            "key": "sim/empty.d3plot",
            "parsed": {
                "metadata": {
                    "file_size": 0,
                    "category": "solver_output",
                    "solver_type": "unknown",
                }
            }
        }

        result = module.handler(event, None)

        assert result["quality_score"] == "FAIL"
        assert len(result["issues"]) >= 2  # empty + unknown solver
