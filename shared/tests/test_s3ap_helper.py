"""S3ApHelper ユニットテスト

S3ApHelper の動作を検証するユニットテスト。
unittest.mock を使用して boto3 S3 クライアントをモックする。

Validates: Requirements 12.1
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

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
def alias_helper(mock_session) -> S3ApHelper:
    """Alias 形式の S3ApHelper インスタンスを返す"""
    return S3ApHelper("my-volume-ext-s3alias", session=mock_session)


@pytest.fixture
def arn_helper(mock_session) -> S3ApHelper:
    """ARN 形式の S3ApHelper インスタンスを返す"""
    return S3ApHelper(
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-ap",
        session=mock_session,
    )


def _make_client_error(
    code: str = "AccessDenied",
    message: str = "Access Denied",
    operation: str = "ListObjectsV2",
) -> ClientError:
    """テスト用 ClientError を生成する"""
    return ClientError(
        {"Error": {"Code": code, "Message": message}},
        operation,
    )


# ---------------------------------------------------------------------------
# TestS3ApHelper
# ---------------------------------------------------------------------------


class TestS3ApHelper:
    """S3ApHelper のテスト"""

    # --- bucket_param ---

    def test_alias_bucket_param(self, alias_helper: S3ApHelper):
        """Alias 形式が bucket_param としてそのまま使用されることを検証する"""
        assert alias_helper.bucket_param == "my-volume-ext-s3alias"

    def test_arn_bucket_param(self, arn_helper: S3ApHelper):
        """ARN 形式が bucket_param としてそのまま使用されることを検証する"""
        assert (
            arn_helper.bucket_param
            == "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-ap"
        )

    # --- list_objects ---

    def test_list_objects_basic(self, alias_helper: S3ApHelper):
        """list_objects が基本的なオブジェクトリストを返すことを検証する"""
        alias_helper._s3_client.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "data/file1.csv",
                    "Size": 1024,
                    "LastModified": datetime(2026, 1, 15),
                    "ETag": '"abc123"',
                },
                {
                    "Key": "data/file2.csv",
                    "Size": 2048,
                    "LastModified": datetime(2026, 1, 16),
                    "ETag": '"def456"',
                },
            ],
            "IsTruncated": False,
        }

        result = alias_helper.list_objects(prefix="data/")

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["Key"] == "data/file1.csv"
        assert result[1]["Key"] == "data/file2.csv"
        alias_helper._s3_client.list_objects_v2.assert_called_once()

    def test_list_objects_with_pagination(self, alias_helper: S3ApHelper):
        """2 ページのページネーションで全オブジェクトが返されることを検証する"""
        alias_helper._s3_client.list_objects_v2.side_effect = [
            {
                "Contents": [
                    {
                        "Key": "file1.csv",
                        "Size": 100,
                        "LastModified": datetime(2026, 1, 15),
                        "ETag": '"a"',
                    },
                ],
                "IsTruncated": True,
                "NextContinuationToken": "token-page2",
            },
            {
                "Contents": [
                    {
                        "Key": "file2.csv",
                        "Size": 200,
                        "LastModified": datetime(2026, 1, 16),
                        "ETag": '"b"',
                    },
                ],
                "IsTruncated": False,
            },
        ]

        result = alias_helper.list_objects()

        assert len(result) == 2
        assert result[0]["Key"] == "file1.csv"
        assert result[1]["Key"] == "file2.csv"
        assert alias_helper._s3_client.list_objects_v2.call_count == 2

    def test_list_objects_with_suffix_filter(self, alias_helper: S3ApHelper):
        """サフィックスフィルタが正しく動作することを検証する"""
        alias_helper._s3_client.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "data/file1.csv",
                    "Size": 100,
                    "LastModified": datetime(2026, 1, 15),
                    "ETag": '"a"',
                },
                {
                    "Key": "data/file2.json",
                    "Size": 200,
                    "LastModified": datetime(2026, 1, 16),
                    "ETag": '"b"',
                },
                {
                    "Key": "data/file3.csv",
                    "Size": 300,
                    "LastModified": datetime(2026, 1, 17),
                    "ETag": '"c"',
                },
            ],
            "IsTruncated": False,
        }

        result = alias_helper.list_objects(suffix=".csv")

        assert len(result) == 2
        assert all(obj["Key"].endswith(".csv") for obj in result)

    def test_list_objects_with_prefix_and_suffix(self, alias_helper: S3ApHelper):
        """プレフィックスとサフィックスの両方が正しく動作することを検証する"""
        alias_helper._s3_client.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "sensors/temp.csv",
                    "Size": 100,
                    "LastModified": datetime(2026, 1, 15),
                    "ETag": '"a"',
                },
                {
                    "Key": "sensors/image.png",
                    "Size": 200,
                    "LastModified": datetime(2026, 1, 16),
                    "ETag": '"b"',
                },
            ],
            "IsTruncated": False,
        }

        result = alias_helper.list_objects(prefix="sensors/", suffix=".csv")

        assert len(result) == 1
        assert result[0]["Key"] == "sensors/temp.csv"
        # Verify prefix was passed to the API call
        call_kwargs = alias_helper._s3_client.list_objects_v2.call_args[1]
        assert call_kwargs["Prefix"] == "sensors/"

    # --- get_object ---

    def test_get_object(self, alias_helper: S3ApHelper):
        """get_object がレスポンスを返すことを検証する"""
        mock_response = {
            "Body": MagicMock(),
            "ContentLength": 1024,
            "ContentType": "text/csv",
            "ETag": '"abc123"',
        }
        alias_helper._s3_client.get_object.return_value = mock_response

        result = alias_helper.get_object("data/file1.csv")

        assert result == mock_response
        alias_helper._s3_client.get_object.assert_called_once_with(
            Bucket="my-volume-ext-s3alias",
            Key="data/file1.csv",
        )

    # --- put_object ---

    def test_put_object_bytes(self, alias_helper: S3ApHelper):
        """put_object が bytes ボディで正しく動作することを検証する"""
        alias_helper._s3_client.put_object.return_value = {"ETag": '"xyz"'}

        result = alias_helper.put_object(
            "output/result.bin", b"binary-data", content_type="application/octet-stream"
        )

        assert result == {"ETag": '"xyz"'}
        alias_helper._s3_client.put_object.assert_called_once_with(
            Bucket="my-volume-ext-s3alias",
            Key="output/result.bin",
            Body=b"binary-data",
            ContentType="application/octet-stream",
        )

    def test_put_object_string(self, alias_helper: S3ApHelper):
        """put_object が string ボディを自動エンコードすることを検証する"""
        alias_helper._s3_client.put_object.return_value = {"ETag": '"xyz"'}

        result = alias_helper.put_object(
            "output/result.json",
            '{"key": "value"}',
            content_type="application/json",
        )

        assert result == {"ETag": '"xyz"'}
        # String should be auto-encoded to bytes
        alias_helper._s3_client.put_object.assert_called_once_with(
            Bucket="my-volume-ext-s3alias",
            Key="output/result.json",
            Body=b'{"key": "value"}',
            ContentType="application/json",
        )

    # --- head_object ---

    def test_head_object(self, alias_helper: S3ApHelper):
        """head_object がメタデータレスポンスを返すことを検証する"""
        mock_response = {
            "ContentLength": 1024,
            "ContentType": "text/csv",
            "ETag": '"abc123"',
            "LastModified": datetime(2026, 1, 15),
        }
        alias_helper._s3_client.head_object.return_value = mock_response

        result = alias_helper.head_object("data/file1.csv")

        assert result == mock_response
        alias_helper._s3_client.head_object.assert_called_once_with(
            Bucket="my-volume-ext-s3alias",
            Key="data/file1.csv",
        )

    # --- delete_object ---

    def test_delete_object(self, alias_helper: S3ApHelper):
        """delete_object がレスポンスを返すことを検証する"""
        mock_response = {"DeleteMarker": True}
        alias_helper._s3_client.delete_object.return_value = mock_response

        result = alias_helper.delete_object("data/old-file.csv")

        assert result == mock_response
        alias_helper._s3_client.delete_object.assert_called_once_with(
            Bucket="my-volume-ext-s3alias",
            Key="data/old-file.csv",
        )

    # --- AccessDenied error ---

    def test_access_denied_raises_descriptive_error(self, alias_helper: S3ApHelper):
        """AccessDenied ClientError が S3ApHelperError に変換され、error_code を持つことを検証する"""
        alias_helper._s3_client.list_objects_v2.side_effect = _make_client_error(
            code="AccessDenied",
            message="Access Denied",
            operation="ListObjectsV2",
        )

        with pytest.raises(S3ApHelperError) as exc_info:
            alias_helper.list_objects()

        assert exc_info.value.error_code == "AccessDenied"
        assert "Access denied" in str(exc_info.value)
        assert "my-volume-ext-s3alias" in str(exc_info.value)

    # --- SUPPORTED_OPERATIONS ---

    def test_supported_operations(self):
        """SUPPORTED_OPERATIONS が全サポート操作を含むことを検証する"""
        expected_ops = [
            "ListObjectsV2",
            "GetObject",
            "PutObject",
            "HeadObject",
            "DeleteObject",
            "DeleteObjects",
            "CopyObject",
            "GetObjectAttributes",
            "GetObjectTagging",
            "PutObjectTagging",
            "DeleteObjectTagging",
            "ListObjects",
            "HeadBucket",
            "GetBucketLocation",
            "ListParts",
            "CreateMultipartUpload",
            "UploadPart",
            "UploadPartCopy",
            "CompleteMultipartUpload",
            "AbortMultipartUpload",
            "ListMultipartUploads",
        ]
        assert len(S3ApHelper.SUPPORTED_OPERATIONS) == 21
        for op in expected_ops:
            assert op in S3ApHelper.SUPPORTED_OPERATIONS
