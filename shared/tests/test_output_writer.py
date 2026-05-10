"""OutputWriter ユニットテスト

環境変数による出力先切替（STANDARD_S3 / FSXN_S3AP）と、各書き込み API
（put_bytes / put_text / put_json）、FSxN S3AP 仕様への準拠を検証する。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from shared.exceptions import S3ApHelperError
from shared.output_writer import (
    DEFAULT_S3AP_PREFIX,
    FSXN_S3AP,
    STANDARD_S3,
    OutputWriter,
    OutputWriterError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    """boto3.Session のモック"""
    session = MagicMock()
    s3_client = MagicMock()
    s3_client.put_object.return_value = {"ETag": '"abc123"'}
    session.client.return_value = s3_client
    session._s3_client = s3_client
    return session


@pytest.fixture
def writer_standard(mock_session) -> OutputWriter:
    """STANDARD_S3 モードの Writer"""
    return OutputWriter(
        destination=STANDARD_S3,
        bucket="my-output-bucket",
        session=mock_session,
    )


@pytest.fixture
def writer_s3ap(mock_session) -> OutputWriter:
    """FSXN_S3AP モードの Writer"""
    return OutputWriter(
        destination=FSXN_S3AP,
        s3ap_alias="my-volume-ext-s3alias",
        s3ap_prefix="ai-outputs/",
        session=mock_session,
    )


# ---------------------------------------------------------------------------
# Construction / validation
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_standard_s3_requires_bucket(self):
        with pytest.raises(OutputWriterError, match="OUTPUT_BUCKET is required"):
            OutputWriter(destination=STANDARD_S3, bucket=None)

    def test_fsxn_s3ap_requires_alias(self):
        with pytest.raises(OutputWriterError, match="OUTPUT_S3AP_ALIAS is required"):
            OutputWriter(destination=FSXN_S3AP, s3ap_alias=None)

    def test_invalid_destination_rejected(self):
        with pytest.raises(OutputWriterError, match="Invalid OUTPUT_DESTINATION"):
            OutputWriter(destination="INVALID", bucket="foo")

    def test_standard_s3_constructed_ok(self, mock_session):
        w = OutputWriter(
            destination=STANDARD_S3, bucket="b", session=mock_session
        )
        assert w.destination == STANDARD_S3
        assert "Standard S3 bucket 'b'" in w.target_description

    def test_fsxn_s3ap_constructed_ok(self, mock_session):
        w = OutputWriter(
            destination=FSXN_S3AP,
            s3ap_alias="xxx-ext-s3alias",
            session=mock_session,
        )
        assert w.destination == FSXN_S3AP
        assert "FSxN S3 Access Point 'xxx-ext-s3alias'" in w.target_description

    def test_s3ap_prefix_normalized_to_trailing_slash(self, mock_session):
        w = OutputWriter(
            destination=FSXN_S3AP,
            s3ap_alias="x",
            s3ap_prefix="foo/bar",
            session=mock_session,
        )
        # 内部プレフィックスが "foo/bar/" に正規化される
        bucket, key = w._resolve_target("test.json")
        assert key == "foo/bar/test.json"

    def test_s3ap_empty_prefix_supported(self, mock_session):
        w = OutputWriter(
            destination=FSXN_S3AP,
            s3ap_alias="x",
            s3ap_prefix="",
            session=mock_session,
        )
        bucket, key = w._resolve_target("test.json")
        assert key == "test.json"


# ---------------------------------------------------------------------------
# from_env
# ---------------------------------------------------------------------------


class TestFromEnv:
    def test_default_destination_is_standard_s3(self, mock_session):
        with patch.dict(
            "os.environ",
            {"OUTPUT_BUCKET": "b1"},
            clear=True,
        ):
            w = OutputWriter.from_env(session=mock_session)
            assert w.destination == STANDARD_S3

    def test_standard_s3_from_env(self, mock_session):
        with patch.dict(
            "os.environ",
            {
                "OUTPUT_DESTINATION": "STANDARD_S3",
                "OUTPUT_BUCKET": "my-bucket",
            },
            clear=True,
        ):
            w = OutputWriter.from_env(session=mock_session)
            assert w.destination == STANDARD_S3
            bucket, key = w._resolve_target("k.json")
            assert bucket == "my-bucket"
            assert key == "k.json"

    def test_fsxn_s3ap_from_env(self, mock_session):
        with patch.dict(
            "os.environ",
            {
                "OUTPUT_DESTINATION": "FSXN_S3AP",
                "OUTPUT_S3AP_ALIAS": "xxx-ext-s3alias",
                "OUTPUT_S3AP_PREFIX": "outputs/",
            },
            clear=True,
        ):
            w = OutputWriter.from_env(session=mock_session)
            assert w.destination == FSXN_S3AP
            bucket, key = w._resolve_target("k.json")
            assert bucket == "xxx-ext-s3alias"
            assert key == "outputs/k.json"

    def test_destination_case_insensitive(self, mock_session):
        with patch.dict(
            "os.environ",
            {
                "OUTPUT_DESTINATION": "fsxn_s3ap",
                "OUTPUT_S3AP_ALIAS": "xxx",
            },
            clear=True,
        ):
            w = OutputWriter.from_env(session=mock_session)
            assert w.destination == FSXN_S3AP


# ---------------------------------------------------------------------------
# put_bytes / put_text / put_json
# ---------------------------------------------------------------------------


class TestPutOperations:
    def test_put_bytes_standard_s3(self, writer_standard, mock_session):
        result = writer_standard.put_bytes(
            key="foo/bar.bin",
            body=b"\x00\x01\x02",
            content_type="application/octet-stream",
        )
        mock_session._s3_client.put_object.assert_called_once_with(
            Bucket="my-output-bucket",
            Key="foo/bar.bin",
            Body=b"\x00\x01\x02",
            ContentType="application/octet-stream",
        )
        assert result == {
            "destination": STANDARD_S3,
            "bucket_or_ap": "my-output-bucket",
            "key": "foo/bar.bin",
            "etag": '"abc123"',
            "size": 3,
        }

    def test_put_bytes_fsxn_s3ap_applies_prefix(self, writer_s3ap, mock_session):
        result = writer_s3ap.put_bytes(
            key="foo/bar.json",
            body=b"{}",
            content_type="application/json",
        )
        mock_session._s3_client.put_object.assert_called_once_with(
            Bucket="my-volume-ext-s3alias",
            Key="ai-outputs/foo/bar.json",  # プレフィックス付与
            Body=b"{}",
            ContentType="application/json",
        )
        assert result["destination"] == FSXN_S3AP
        assert result["key"] == "ai-outputs/foo/bar.json"

    def test_put_text_encodes_utf8(self, writer_standard, mock_session):
        writer_standard.put_text(key="note.txt", text="日本語テキスト")
        call_kwargs = mock_session._s3_client.put_object.call_args.kwargs
        assert call_kwargs["Body"] == "日本語テキスト".encode("utf-8")
        assert call_kwargs["ContentType"] == "text/plain; charset=utf-8"

    def test_put_json_serializes_dict(self, writer_standard, mock_session):
        writer_standard.put_json(
            key="report.json",
            data={"status": "OK", "count": 5},
        )
        call_kwargs = mock_session._s3_client.put_object.call_args.kwargs
        assert json.loads(call_kwargs["Body"]) == {"status": "OK", "count": 5}
        assert call_kwargs["ContentType"] == "application/json; charset=utf-8"

    def test_put_json_default_ensure_ascii_false(self, writer_standard, mock_session):
        """日本語がエスケープされずに書き込まれる"""
        writer_standard.put_json(key="ja.json", data={"msg": "こんにちは"})
        call_kwargs = mock_session._s3_client.put_object.call_args.kwargs
        # ensure_ascii=False で日本語がそのまま保存される
        assert "こんにちは".encode("utf-8") in call_kwargs["Body"]


# ---------------------------------------------------------------------------
# SSE-FSX compliance: FSxN S3AP では ServerSideEncryption を渡さないこと
# ---------------------------------------------------------------------------


class TestSSEFSXCompliance:
    def test_no_server_side_encryption_param_for_fsxn(
        self, writer_s3ap, mock_session
    ):
        """FSxN S3AP は SSE-FSX が自動適用されるため、
        アプリからは ServerSideEncryption を指定してはならない。"""
        writer_s3ap.put_bytes(key="x.bin", body=b"abc")
        call_kwargs = mock_session._s3_client.put_object.call_args.kwargs
        assert "ServerSideEncryption" not in call_kwargs
        assert "SSEKMSKeyId" not in call_kwargs

    def test_no_server_side_encryption_param_for_standard_s3(
        self, writer_standard, mock_session
    ):
        """STANDARD_S3 モードでも本ヘルパーは SSE パラメータを渡さない。
        標準 S3 側の bucket 設定（SSE-KMS 等）に委ねる。"""
        writer_standard.put_bytes(key="x.bin", body=b"abc")
        call_kwargs = mock_session._s3_client.put_object.call_args.kwargs
        assert "ServerSideEncryption" not in call_kwargs


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def _client_error(self, code="AccessDenied", operation="PutObject"):
        return ClientError(
            {"Error": {"Code": code, "Message": f"{code} msg"}},
            operation,
        )

    def test_s3ap_put_failure_wrapped_as_s3ap_helper_error(
        self, writer_s3ap, mock_session
    ):
        mock_session._s3_client.put_object.side_effect = self._client_error()
        with pytest.raises(S3ApHelperError, match="FSxN S3 Access Point"):
            writer_s3ap.put_bytes(key="x.bin", body=b"abc")

    def test_standard_s3_put_failure_raises_client_error(
        self, writer_standard, mock_session
    ):
        """STANDARD_S3 モードの失敗は ClientError をそのまま伝播"""
        mock_session._s3_client.put_object.side_effect = self._client_error()
        with pytest.raises(ClientError):
            writer_standard.put_bytes(key="x.bin", body=b"abc")


# ---------------------------------------------------------------------------
# build_s3_uri
# ---------------------------------------------------------------------------


class TestBuildS3Uri:
    def test_standard_s3_uri(self, writer_standard):
        assert (
            writer_standard.build_s3_uri("report/out.json")
            == "s3://my-output-bucket/report/out.json"
        )

    def test_fsxn_s3ap_uri_with_prefix(self, writer_s3ap):
        assert (
            writer_s3ap.build_s3_uri("report/out.json")
            == "s3://my-volume-ext-s3alias/ai-outputs/report/out.json"
        )


# ---------------------------------------------------------------------------
# get_bytes / get_text / get_json — 書き込み先と対称な読み出し
# ---------------------------------------------------------------------------


class TestGetOperations:
    def _body(self, data: bytes):
        mock_body = MagicMock()
        mock_body.read.return_value = data
        return mock_body

    def test_get_bytes_standard_s3(self, writer_standard, mock_session):
        mock_session._s3_client.get_object.return_value = {
            "Body": self._body(b"\x00\x01")
        }
        data = writer_standard.get_bytes("foo/bar.bin")
        mock_session._s3_client.get_object.assert_called_once_with(
            Bucket="my-output-bucket", Key="foo/bar.bin"
        )
        assert data == b"\x00\x01"

    def test_get_bytes_fsxn_s3ap_applies_prefix(self, writer_s3ap, mock_session):
        mock_session._s3_client.get_object.return_value = {
            "Body": self._body(b"payload")
        }
        data = writer_s3ap.get_bytes("foo/bar.json")
        mock_session._s3_client.get_object.assert_called_once_with(
            Bucket="my-volume-ext-s3alias", Key="ai-outputs/foo/bar.json"
        )
        assert data == b"payload"

    def test_get_text_decodes_utf8(self, writer_standard, mock_session):
        mock_session._s3_client.get_object.return_value = {
            "Body": self._body("こんにちは".encode("utf-8"))
        }
        text = writer_standard.get_text("hello.txt")
        assert text == "こんにちは"

    def test_get_json_parses(self, writer_standard, mock_session):
        mock_session._s3_client.get_object.return_value = {
            "Body": self._body(b'{"foo": "bar", "count": 3}')
        }
        result = writer_standard.get_json("data.json")
        assert result == {"foo": "bar", "count": 3}

    def test_s3ap_get_failure_wrapped_as_s3ap_helper_error(
        self, writer_s3ap, mock_session
    ):
        mock_session._s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "missing"}},
            "GetObject",
        )
        with pytest.raises(S3ApHelperError, match="FSxN S3 Access Point"):
            writer_s3ap.get_bytes("missing.json")

    def test_standard_s3_get_failure_raises_client_error(
        self, writer_standard, mock_session
    ):
        mock_session._s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "missing"}},
            "GetObject",
        )
        with pytest.raises(ClientError):
            writer_standard.get_bytes("missing.json")
