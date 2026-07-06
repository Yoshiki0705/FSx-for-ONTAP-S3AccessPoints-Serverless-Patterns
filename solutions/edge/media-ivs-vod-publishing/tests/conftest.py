"""Pytest fixtures for media-ivs-vod-publishing tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# shared モジュール解決（リポジトリルートを sys.path に追加）
# tests → media-ivs-vod-publishing → edge → solutions → root (5 levels)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))


def _load_handler(function_name: str):
    module_name = f"media_ivs_vod_{function_name}_handler"
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
def moderation_handler():
    return _load_handler("moderation")


@pytest.fixture
def transcode_handler():
    return _load_handler("transcode")


@pytest.fixture
def lambda_context():
    ctx = MagicMock()
    ctx.aws_request_id = "test-request-id-media-ivs-vod"
    ctx.function_name = "test-function"
    return ctx


class FakeS3Ap:
    """S3ApHelper のテスト用フェイク。"""

    def __init__(self, objects=None, bodies=None):
        self._objects = objects or []
        self._bodies = bodies or {}
        self.put_calls = []

    def list_objects(self, prefix: str = "", suffix: str = "", max_keys: int = 1000):
        return [o for o in self._objects if o["Key"].startswith(prefix)]

    def get_object(self, key: str):
        body = MagicMock()
        body.read.return_value = self._bodies.get(key, b"data")
        return {"Body": body, "ContentType": "application/octet-stream"}

    def head_object(self, key: str):
        return {"ContentType": "application/octet-stream"}

    def streaming_download(self, key: str, chunk_size: int = 8 * 1024 * 1024):
        yield self._bodies.get(key, b"data")

    def put_object(self, key: str, body, content_type: str = "application/octet-stream"):
        self.put_calls.append({"key": key, "body": body, "content_type": content_type})
        return {"ETag": "fake-etag"}

    def multipart_upload(self, key, data_iterator, content_type="application/octet-stream", part_size=None):
        data = b"".join(data_iterator)
        self.put_calls.append({"key": key, "body": data, "content_type": content_type, "multipart": True})
        return {"ETag": "fake-etag-multipart"}


@pytest.fixture
def fake_s3ap_factory():
    def _factory(objects=None, bodies=None):
        return FakeS3Ap(objects=objects, bodies=bodies)

    return _factory
