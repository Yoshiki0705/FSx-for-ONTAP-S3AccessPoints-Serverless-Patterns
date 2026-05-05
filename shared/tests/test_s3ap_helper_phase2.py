"""S3ApHelper Phase 2 拡張ユニットテスト

S3ApHelper の Phase 2 追加メソッド（streaming_download, streaming_download_range,
multipart_upload）の動作を検証するユニットテスト。
unittest.mock を使用して boto3 S3 クライアントをモックする。

Validates: Requirements 13.7
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, call, patch

import pytest
from botocore.exceptions import ClientError

from shared.exceptions import S3ApHelperError
from shared.s3ap_helper import S3ApHelper


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    """モック boto3.Session を返す"""
    session = MagicMock()
    s3_client = MagicMock()
    session.client.return_value = s3_client
    session._s3_client = s3_client
    return session


@pytest.fixture
def helper(mock_session) -> S3ApHelper:
    """S3ApHelper インスタンスを返す"""
    return S3ApHelper("my-volume-ext-s3alias", session=mock_session)


def _make_client_error(
    code: str = "AccessDenied",
    message: str = "Access Denied",
    operation: str = "GetObject",
) -> ClientError:
    """テスト用 ClientError を生成する"""
    return ClientError(
        {"Error": {"Code": code, "Message": message}},
        operation,
    )


# ---------------------------------------------------------------------------
# streaming_download テスト
# ---------------------------------------------------------------------------


class TestStreamingDownload:
    """streaming_download メソッドのテスト"""

    def test_streaming_download_all_data(self, helper: S3ApHelper):
        """ストリーミングダウンロードで全データが取得されることを検証する"""
        data = b"Hello, World! This is test data for streaming download."
        mock_body = MagicMock()
        # read() が chunk_size ごとにデータを返し、最後に空バイトを返す
        mock_body.read.side_effect = [data[:20], data[20:], b""]

        helper._s3_client.get_object.return_value = {"Body": mock_body}

        chunks = list(helper.streaming_download("data/test.bin", chunk_size=20))

        assert b"".join(chunks) == data
        assert len(chunks) == 2
        helper._s3_client.get_object.assert_called_once_with(
            Bucket="my-volume-ext-s3alias",
            Key="data/test.bin",
        )
        mock_body.close.assert_called_once()

    def test_streaming_download_single_chunk(self, helper: S3ApHelper):
        """データが 1 チャンクに収まる場合のストリーミングダウンロードを検証する"""
        data = b"small data"
        mock_body = MagicMock()
        mock_body.read.side_effect = [data, b""]

        helper._s3_client.get_object.return_value = {"Body": mock_body}

        chunks = list(helper.streaming_download("data/small.bin", chunk_size=1024))

        assert b"".join(chunks) == data
        assert len(chunks) == 1
        mock_body.close.assert_called_once()

    def test_streaming_download_empty_object(self, helper: S3ApHelper):
        """空オブジェクトのストリーミングダウンロードを検証する"""
        mock_body = MagicMock()
        mock_body.read.return_value = b""

        helper._s3_client.get_object.return_value = {"Body": mock_body}

        chunks = list(helper.streaming_download("data/empty.bin"))

        assert chunks == []
        mock_body.close.assert_called_once()

    def test_streaming_download_body_close_on_exception(self, helper: S3ApHelper):
        """イテレーション中に例外が発生しても Body.close() が呼ばれることを検証する"""
        mock_body = MagicMock()
        mock_body.read.side_effect = [b"first chunk", IOError("read error")]

        helper._s3_client.get_object.return_value = {"Body": mock_body}

        gen = helper.streaming_download("data/error.bin", chunk_size=20)
        # 最初のチャンクは取得できる
        assert next(gen) == b"first chunk"
        # 2 番目の read で IOError が発生
        with pytest.raises(IOError, match="read error"):
            next(gen)
        # finally ブロックで close が呼ばれることを確認
        gen.close()
        mock_body.close.assert_called_once()

    def test_streaming_download_access_denied(self, helper: S3ApHelper):
        """AccessDenied エラーが S3ApHelperError に変換されることを検証する"""
        helper._s3_client.get_object.side_effect = _make_client_error(
            code="AccessDenied",
            message="Access Denied",
            operation="GetObject",
        )

        with pytest.raises(S3ApHelperError) as exc_info:
            list(helper.streaming_download("data/secret.bin"))

        assert exc_info.value.error_code == "AccessDenied"
        assert "Access denied" in str(exc_info.value)

    def test_streaming_download_other_error(self, helper: S3ApHelper):
        """AccessDenied 以外のエラーが S3ApHelperError に変換されることを検証する"""
        helper._s3_client.get_object.side_effect = _make_client_error(
            code="NoSuchKey",
            message="The specified key does not exist.",
            operation="GetObject",
        )

        with pytest.raises(S3ApHelperError) as exc_info:
            list(helper.streaming_download("data/missing.bin"))

        assert exc_info.value.error_code == "NoSuchKey"


# ---------------------------------------------------------------------------
# streaming_download_range テスト
# ---------------------------------------------------------------------------


class TestStreamingDownloadRange:
    """streaming_download_range メソッドのテスト"""

    def test_range_download_exact_bytes(self, helper: S3ApHelper):
        """Range ダウンロードで正確なバイト範囲が返されることを検証する"""
        expected_data = b"SEGY_HEADER_DATA_3600_BYTES"
        mock_body = MagicMock()
        mock_body.read.return_value = expected_data

        helper._s3_client.get_object.return_value = {"Body": mock_body}

        result = helper.streaming_download_range("surveys/test.segy", start=0, end=3599)

        assert result == expected_data
        helper._s3_client.get_object.assert_called_once_with(
            Bucket="my-volume-ext-s3alias",
            Key="surveys/test.segy",
            Range="bytes=0-3599",
        )

    def test_range_download_middle_range(self, helper: S3ApHelper):
        """ファイル中間部分の Range ダウンロードを検証する"""
        expected_data = b"middle_section"
        mock_body = MagicMock()
        mock_body.read.return_value = expected_data

        helper._s3_client.get_object.return_value = {"Body": mock_body}

        result = helper.streaming_download_range("data/large.bin", start=1000, end=1999)

        assert result == expected_data
        helper._s3_client.get_object.assert_called_once_with(
            Bucket="my-volume-ext-s3alias",
            Key="data/large.bin",
            Range="bytes=1000-1999",
        )

    def test_range_download_access_denied(self, helper: S3ApHelper):
        """Range ダウンロードの AccessDenied エラーを検証する"""
        helper._s3_client.get_object.side_effect = _make_client_error(
            code="AccessDenied",
            message="Access Denied",
            operation="GetObject",
        )

        with pytest.raises(S3ApHelperError) as exc_info:
            helper.streaming_download_range("data/secret.bin", start=0, end=100)

        assert exc_info.value.error_code == "AccessDenied"
        assert "Access denied" in str(exc_info.value)

    def test_range_download_other_error(self, helper: S3ApHelper):
        """Range ダウンロードの一般エラーを検証する"""
        helper._s3_client.get_object.side_effect = _make_client_error(
            code="NoSuchKey",
            message="The specified key does not exist.",
            operation="GetObject",
        )

        with pytest.raises(S3ApHelperError) as exc_info:
            helper.streaming_download_range("data/missing.bin", start=0, end=100)

        assert exc_info.value.error_code == "NoSuchKey"


# ---------------------------------------------------------------------------
# multipart_upload テスト
# ---------------------------------------------------------------------------


class TestMultipartUpload:
    """multipart_upload メソッドのテスト"""

    def test_multipart_upload_success(self, helper: S3ApHelper):
        """マルチパートアップロードの正常系を検証する"""
        helper._s3_client.create_multipart_upload.return_value = {
            "UploadId": "test-upload-id-123",
        }
        helper._s3_client.upload_part.return_value = {"ETag": '"etag-1"'}
        helper._s3_client.complete_multipart_upload.return_value = {
            "Location": "https://s3.amazonaws.com/my-volume-ext-s3alias/output/result.bin",
            "ETag": '"final-etag"',
        }

        # 小さいパートサイズでテスト
        data_chunks = [b"chunk1", b"chunk2", b"chunk3"]
        result = helper.multipart_upload(
            "output/result.bin",
            iter(data_chunks),
            content_type="application/octet-stream",
            part_size=10,  # 10 バイト
        )

        assert result["ETag"] == '"final-etag"'
        helper._s3_client.create_multipart_upload.assert_called_once_with(
            Bucket="my-volume-ext-s3alias",
            Key="output/result.bin",
            ContentType="application/octet-stream",
        )
        helper._s3_client.complete_multipart_upload.assert_called_once()

    def test_multipart_upload_multiple_parts(self, helper: S3ApHelper):
        """複数パートに分割されるマルチパートアップロードを検証する"""
        helper._s3_client.create_multipart_upload.return_value = {
            "UploadId": "upload-multi",
        }
        # 各 upload_part 呼び出しに異なる ETag を返す
        helper._s3_client.upload_part.side_effect = [
            {"ETag": '"etag-1"'},
            {"ETag": '"etag-2"'},
            {"ETag": '"etag-3"'},
        ]
        helper._s3_client.complete_multipart_upload.return_value = {
            "ETag": '"final"',
        }

        # part_size=5 で 15 バイトのデータ → 3 パート
        data_chunks = [b"AAAAA", b"BBBBB", b"CCCCC"]
        result = helper.multipart_upload(
            "output/multi.bin",
            iter(data_chunks),
            part_size=5,
        )

        assert helper._s3_client.upload_part.call_count == 3
        # CompleteMultipartUpload の Parts を検証
        complete_call = helper._s3_client.complete_multipart_upload.call_args
        parts = complete_call[1]["MultipartUpload"]["Parts"]
        assert len(parts) == 3
        assert parts[0] == {"PartNumber": 1, "ETag": '"etag-1"'}
        assert parts[1] == {"PartNumber": 2, "ETag": '"etag-2"'}
        assert parts[2] == {"PartNumber": 3, "ETag": '"etag-3"'}

    def test_multipart_upload_with_remainder(self, helper: S3ApHelper):
        """パートサイズで割り切れないデータの残りバッファがアップロードされることを検証する"""
        helper._s3_client.create_multipart_upload.return_value = {
            "UploadId": "upload-remainder",
        }
        helper._s3_client.upload_part.side_effect = [
            {"ETag": '"etag-1"'},
            {"ETag": '"etag-2"'},
        ]
        helper._s3_client.complete_multipart_upload.return_value = {
            "ETag": '"final"',
        }

        # part_size=10 で 15 バイト → 1 フルパート + 1 残りパート
        data_chunks = [b"A" * 10, b"B" * 5]
        result = helper.multipart_upload(
            "output/remainder.bin",
            iter(data_chunks),
            part_size=10,
        )

        assert helper._s3_client.upload_part.call_count == 2
        # 最初のパートは 10 バイト
        first_call = helper._s3_client.upload_part.call_args_list[0]
        assert len(first_call[1]["Body"]) == 10
        # 2 番目のパートは 5 バイト（残り）
        second_call = helper._s3_client.upload_part.call_args_list[1]
        assert len(second_call[1]["Body"]) == 5

    def test_multipart_upload_failure_aborts(self, helper: S3ApHelper):
        """upload_part 失敗時に abort_multipart_upload が呼ばれることを検証する"""
        helper._s3_client.create_multipart_upload.return_value = {
            "UploadId": "upload-fail",
        }
        helper._s3_client.upload_part.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "Internal error"}},
            "UploadPart",
        )

        with pytest.raises(S3ApHelperError) as exc_info:
            helper.multipart_upload(
                "output/fail.bin",
                iter([b"data"]),
                part_size=2,
            )

        assert exc_info.value.error_code == "MultipartUploadFailed"
        helper._s3_client.abort_multipart_upload.assert_called_once_with(
            Bucket="my-volume-ext-s3alias",
            Key="output/fail.bin",
            UploadId="upload-fail",
        )

    def test_multipart_upload_abort_failure_logged(self, helper: S3ApHelper):
        """abort_multipart_upload 自体が失敗してもメインエラーが raise されることを検証する"""
        helper._s3_client.create_multipart_upload.return_value = {
            "UploadId": "upload-abort-fail",
        }
        helper._s3_client.upload_part.side_effect = RuntimeError("upload broke")
        helper._s3_client.abort_multipart_upload.side_effect = _make_client_error(
            code="InternalError",
            message="Abort failed",
            operation="AbortMultipartUpload",
        )

        with pytest.raises(S3ApHelperError) as exc_info:
            helper.multipart_upload(
                "output/abort-fail.bin",
                iter([b"data"]),
                part_size=2,
            )

        assert exc_info.value.error_code == "MultipartUploadFailed"
        # abort が試行されたことを確認
        helper._s3_client.abort_multipart_upload.assert_called_once()

    def test_multipart_upload_create_failure(self, helper: S3ApHelper):
        """create_multipart_upload 失敗時に S3ApHelperError が raise されることを検証する"""
        helper._s3_client.create_multipart_upload.side_effect = _make_client_error(
            code="AccessDenied",
            message="Access Denied",
            operation="CreateMultipartUpload",
        )

        with pytest.raises(S3ApHelperError) as exc_info:
            helper.multipart_upload(
                "output/no-access.bin",
                iter([b"data"]),
            )

        assert exc_info.value.error_code == "AccessDenied"
