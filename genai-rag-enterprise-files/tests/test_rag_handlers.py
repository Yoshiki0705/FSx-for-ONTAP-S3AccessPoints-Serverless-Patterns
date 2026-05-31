"""GenAI RAG Enterprise Files — Lambda ハンドラーのユニットテスト"""

from __future__ import annotations

import importlib.util
import os
from unittest.mock import MagicMock, patch


def _load_handler(function_name: str):
    """指定した関数のハンドラーモジュールをロード"""
    handler_path = os.path.join(os.path.dirname(__file__), "..", "functions", function_name, "handler.py")
    spec = importlib.util.spec_from_file_location(f"{function_name}_handler", handler_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, spec


class TestDiscovery:
    """Discovery Lambda のテスト"""

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-s3ap-alias"})
    def test_discovery_filters_supported_extensions(self):
        """サポートされる拡張子のみ返す"""
        module, spec = _load_handler("discovery")
        spec.loader.exec_module(module)

        mock_response = {
            "Contents": [
                {
                    "Key": "docs/report.pdf",
                    "Size": 1024,
                    "LastModified": MagicMock(isoformat=lambda: "2026-01-01T00:00:00"),
                },
                {
                    "Key": "docs/data.xlsx",
                    "Size": 2048,
                    "LastModified": MagicMock(isoformat=lambda: "2026-01-01T00:00:00"),
                },
                {
                    "Key": "images/photo.jpg",
                    "Size": 4096,
                    "LastModified": MagicMock(isoformat=lambda: "2026-01-01T00:00:00"),
                },
                {
                    "Key": "docs/notes.txt",
                    "Size": 512,
                    "LastModified": MagicMock(isoformat=lambda: "2026-01-01T00:00:00"),
                },
            ],
            "IsTruncated": False,
        }

        with patch.object(module.s3_client, "list_objects_v2", return_value=mock_response):
            result = module.handler({"prefix": "docs/"}, None)

        assert result["status"] == "completed"
        # .jpg は除外される
        assert result["object_count"] == 3
        extensions = [obj["extension"] for obj in result["objects"]]
        assert ".jpg" not in extensions
        assert ".pdf" in extensions
        assert ".xlsx" in extensions
        assert ".txt" in extensions

    @patch.dict(os.environ, {"S3_ACCESS_POINT_ALIAS": "test-s3ap-alias"})
    def test_discovery_handles_empty_bucket(self):
        """空のバケットの場合"""
        module, spec = _load_handler("discovery")
        spec.loader.exec_module(module)

        mock_response = {"Contents": [], "IsTruncated": False}

        with patch.object(module.s3_client, "list_objects_v2", return_value=mock_response):
            result = module.handler({}, None)

        assert result["status"] == "completed"
        assert result["object_count"] == 0


class TestChunking:
    """Chunking Lambda のテスト"""

    @patch.dict(
        os.environ,
        {
            "S3_ACCESS_POINT_ALIAS": "test-s3ap-alias",
            "CHUNK_SIZE": "100",
            "CHUNK_OVERLAP": "20",
        },
    )
    def test_chunking_splits_text(self):
        """テキストが正しくチャンク分割される"""
        module, spec = _load_handler("chunking")
        spec.loader.exec_module(module)

        test_text = "A" * 250  # 250文字のテキスト
        mock_body = MagicMock()
        mock_body.read.return_value = test_text.encode("utf-8")
        mock_response = {"Body": mock_body}

        with patch.object(module.s3_client, "get_object", return_value=mock_response):
            result = module.handler({"key": "test.txt", "extension": ".txt"}, None)

        assert result["status"] == "completed"
        assert result["chunk_count"] > 1
        assert result["total_chars"] == 250


class TestAclExtraction:
    """ACL Extraction Lambda のテスト"""

    @patch.dict(os.environ, {"SIMULATION_MODE": "true"})
    def test_simulation_confidential_file(self):
        """機密ファイルは限定アクセス"""
        module, spec = _load_handler("acl_extraction")
        spec.loader.exec_module(module)

        result = module.handler({"key": "confidential/report.pdf"}, None)

        assert result["status"] == "completed"
        assert result["simulation"] is True
        assert len(result["acl"]["allowed_sids"]) == 1  # 限定

    @patch.dict(os.environ, {"SIMULATION_MODE": "true"})
    def test_simulation_public_file(self):
        """公開ファイルは広いアクセス"""
        module, spec = _load_handler("acl_extraction")
        spec.loader.exec_module(module)

        result = module.handler({"key": "public/announcement.txt"}, None)

        assert result["status"] == "completed"
        assert "S-1-5-21-DOMAIN-513" in result["acl"]["allowed_sids"]  # Domain Users
