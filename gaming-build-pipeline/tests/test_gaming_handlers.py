"""Gaming Build Pipeline — Lambda ハンドラーのユニットテスト"""

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
        f"gaming_{function_name}_handler", handler_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, spec


class TestQualityCheck:
    """Quality Check Lambda のテスト"""

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-gaming-s3ap"})
    def test_texture_pass_normal_size(self):
        """正常サイズのテクスチャは PASS"""
        module, _ = _load_handler("quality_check")

        result = module.handler(
            {"key": "textures/T_Hero_Diffuse.dds", "category": "texture", "size": 4194304},
            None,
        )

        assert result["status"] == "completed"
        assert result["quality_score"] == "PASS"
        assert len(result["issues"]) == 0

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-gaming-s3ap"})
    def test_texture_fail_empty_file(self):
        """空ファイルは issues を含む"""
        module, _ = _load_handler("quality_check")

        result = module.handler(
            {"key": "textures/empty.dds", "category": "texture", "size": 0},
            None,
        )

        assert result["quality_score"] != "PASS"
        assert any("empty" in issue.lower() or "0 bytes" in issue for issue in result["issues"])

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-gaming-s3ap"})
    def test_texture_warning_oversized(self):
        """100MB 超のテクスチャは WARNING/FAIL"""
        module, _ = _load_handler("quality_check")

        result = module.handler(
            {"key": "textures/T_Landscape_4K.dds", "category": "texture", "size": 150 * 1024 * 1024},
            None,
        )

        assert result["quality_score"] in ("WARNING", "FAIL")
        assert any("100MB" in issue or "limit" in issue for issue in result["issues"])

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-gaming-s3ap"})
    def test_texture_warning_spaces_in_name(self):
        """ファイル名にスペースがある場合は WARNING"""
        module, _ = _load_handler("quality_check")

        result = module.handler(
            {"key": "textures/Hero Diffuse Map.dds", "category": "texture", "size": 4194304},
            None,
        )

        assert any("spaces" in issue.lower() for issue in result["issues"])

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-gaming-s3ap"})
    def test_texture_suspiciously_small(self):
        """100 バイト未満のテクスチャは suspicious"""
        module, _ = _load_handler("quality_check")

        result = module.handler(
            {"key": "textures/tiny.dds", "category": "texture", "size": 50},
            None,
        )

        assert any("small" in issue.lower() or "suspicious" in issue.lower() for issue in result["issues"])

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-gaming-s3ap"})
    def test_shader_valid(self):
        """有効なシェーダーファイルは PASS"""
        module, _ = _load_handler("quality_check")

        mock_body = MagicMock()
        mock_body.read.return_value = b"#pragma once\n#include \"common.hlsl\"\nvoid main() {}"
        mock_body.close = MagicMock()
        mock_response = {"Body": mock_body}

        with patch.object(module.s3_client, "get_object", return_value=mock_response):
            result = module.handler(
                {"key": "shaders/PBR_Standard.hlsl", "category": "shader", "size": 2048},
                None,
            )

        assert result["quality_score"] == "PASS"
        assert len(result["issues"]) == 0

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-gaming-s3ap"})
    def test_shader_with_todo(self):
        """TODO を含むシェーダーは WARNING"""
        module, _ = _load_handler("quality_check")

        mock_body = MagicMock()
        mock_body.read.return_value = b"#pragma once\nvoid main() { // TODO: fix this }"
        mock_body.close = MagicMock()
        mock_response = {"Body": mock_body}

        with patch.object(module.s3_client, "get_object", return_value=mock_response):
            result = module.handler(
                {"key": "shaders/WIP_Effect.hlsl", "category": "shader", "size": 1024},
                None,
            )

        assert any("TODO" in issue for issue in result["issues"])

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-gaming-s3ap"})
    def test_build_artifact_pass(self):
        """正常なビルド成果物は PASS"""
        module, _ = _load_handler("quality_check")

        result = module.handler(
            {"key": "builds/game-client-win64.exe", "category": "build_artifact", "size": 52428800},
            None,
        )

        assert result["status"] == "completed"
        assert result["quality_score"] == "PASS"

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-gaming-s3ap"})
    def test_build_artifact_too_small(self):
        """1KB 未満のビルド成果物は suspicious"""
        module, _ = _load_handler("quality_check")

        result = module.handler(
            {"key": "builds/game-client.exe", "category": "build_artifact", "size": 512},
            None,
        )

        assert any("small" in issue.lower() for issue in result["issues"])

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-gaming-s3ap"})
    def test_result_contains_metadata(self):
        """結果に必要なメタデータが含まれる"""
        module, _ = _load_handler("quality_check")

        result = module.handler(
            {"key": "textures/T_Normal.dds", "category": "texture", "size": 2097152},
            None,
        )

        assert "key" in result
        assert "status" in result
        assert "category" in result
        assert "quality_score" in result
        assert "issues" in result
        assert "file_size_mb" in result
        assert "timestamp" in result
        assert result["file_size_mb"] == 2.0
