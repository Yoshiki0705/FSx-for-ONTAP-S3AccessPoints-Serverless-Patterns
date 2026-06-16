"""Pytest fixtures for content-edge-delivery tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# shared モジュール解決（リポジトリルートを sys.path に追加）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def _load_handler(function_name: str):
    module_name = f"content_edge_delivery_{function_name}_handler"
    handler_path = Path(__file__).resolve().parent.parent / "functions" / function_name / "handler.py"
    spec = importlib.util.spec_from_file_location(module_name, handler_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def publish_handler():
    return _load_handler("publish")


@pytest.fixture
def delivery_log_sync_handler():
    return _load_handler("delivery_log_sync")


@pytest.fixture
def lambda_context():
    ctx = MagicMock()
    ctx.aws_request_id = "test-request-id-content-edge-delivery"
    ctx.function_name = "test-function"
    return ctx


class FakeS3Ap:
    """S3ApHelper のテスト用フェイク。"""

    def __init__(self, objects=None, bodies=None, metadata=None):
        self._objects = objects or []
        self._bodies = bodies or {}
        self._metadata = metadata or {}
        self.put_calls = []

    def list_objects(self, prefix: str = "", suffix: str = "", max_keys: int = 1000):
        return [o for o in self._objects if o["Key"].startswith(prefix)]

    def get_object(self, key: str):
        body = MagicMock()
        body.read.return_value = self._bodies.get(key, b"data")
        return {"Body": body, "ContentType": "application/octet-stream"}

    def head_object(self, key: str):
        return {"Metadata": self._metadata.get(key, {})}

    def put_object(self, key: str, body, content_type: str = "application/octet-stream"):
        self.put_calls.append({"key": key, "body": body, "content_type": content_type})
        return {"ETag": "fake-etag"}


@pytest.fixture
def fake_s3ap_factory():
    def _factory(objects=None, bodies=None, metadata=None):
        return FakeS3Ap(objects=objects, bodies=bodies, metadata=metadata)

    return _factory
