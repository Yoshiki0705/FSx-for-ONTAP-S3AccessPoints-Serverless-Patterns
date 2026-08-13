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
from shared.s3ap_helper import S3ApHelper, access_denied_message

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
        assert arn_helper.bucket_param == "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/my-ap"

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

    # --- get_object_bytes ---
    # Rekognition と Textract は FSx for ONTAP の S3 AP 上のオブジェクトを S3Object
    # 参照では読めない（InvalidS3ObjectException になり、AP ポリシーでサービス
    # プリンシパルを許可しても解消しない）。そのため bytes を取得して inline で渡す
    # 経路が必要で、その入口がこのメソッド。
    def test_get_object_bytes_returns_the_body(self, alias_helper: S3ApHelper):
        """本文を bytes で返すこと。"""
        body = MagicMock()
        body.read.return_value = b"payload"
        alias_helper._s3_client.head_object.return_value = {"ContentLength": 7}
        alias_helper._s3_client.get_object.return_value = {"Body": body}

        assert alias_helper.get_object_bytes("images/a.png") == b"payload"

    def test_get_object_bytes_refuses_an_object_over_the_inline_limit(self, alias_helper: S3ApHelper):
        """同期 AI API の inline 上限を超えるものは取得前に落とす。

        取得してから気づくと、無駄に転送した上でサービス側が曖昧なエラーを返す。
        """
        alias_helper._s3_client.head_object.return_value = {"ContentLength": S3ApHelper.MAX_INLINE_AI_BYTES + 1}

        with pytest.raises(S3ApHelperError) as excinfo:
            alias_helper.get_object_bytes("images/huge.tif")

        assert excinfo.value.error_code == "ObjectTooLargeForInlineAnalysis"
        # 上限超過なら本文は取得しない。
        alias_helper._s3_client.get_object.assert_not_called()

    def test_get_object_bytes_honours_an_explicit_limit(self, alias_helper: S3ApHelper):
        """max_bytes を渡したらそちらを使うこと。"""
        alias_helper._s3_client.head_object.return_value = {"ContentLength": 100}

        with pytest.raises(S3ApHelperError):
            alias_helper.get_object_bytes("images/a.png", max_bytes=10)

    # --- put_object ---

    def test_put_object_bytes(self, alias_helper: S3ApHelper):
        """put_object が bytes ボディで正しく動作することを検証する"""
        alias_helper._s3_client.put_object.return_value = {"ETag": '"xyz"'}

        result = alias_helper.put_object("output/result.bin", b"binary-data", content_type="application/octet-stream")

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


# ---------------------------------------------------------------------------
# TestAccessDeniedDiagnosis
# ---------------------------------------------------------------------------


class TestAccessDeniedDiagnosis:
    """AccessDenied 診断メッセージのテスト

    AccessDenied の原因は AWS 側（IAM / AP ポリシー）と ONTAP ファイルシステム側
    （AD 参加 SVM で AD DC に到達できない）の 2 つの層に分かれる。以前のメッセージは
    前者だけを指していたため、後者が原因のときに真逆の方向へ人を送っていた。

    ここでは「両方の層に言及する」「切り分け方を示す」「AD だと断定しない」の 3 点を
    固定する。
    """

    def test_names_both_layers(self):
        """AWS 側と ONTAP ファイルシステム側の両方に言及することを検証する"""
        msg = access_denied_message("ListObjectsV2", "my-ap-ext-s3alias")

        # AWS 側
        assert "IAM" in msg
        assert "Access Point policy" in msg
        # ONTAP ファイルシステム側
        assert "file-system" in msg
        assert "AD-joined" in msg
        assert "domain controllers" in msg

    def test_names_headbucket_as_discriminator(self):
        """2 つの層を切り分ける手段として HeadBucket を示すことを検証する

        HeadBucket は S3 メタデータ層だけを見るため、ファイルシステム層が原因の
        ケースでも成功する。これが切り分けの決め手になる。
        """
        msg = access_denied_message("GetObject", "my-ap-ext-s3alias")

        assert "HeadBucket" in msg
        assert "metadata layer" in msg

    def test_gives_dc_reachability_check(self):
        """DC 到達性の判定条件を具体的に示すことを検証する

        「エントリが 1 件以上ある」では不十分で、server_type=ms_dc かつ state=ok の
        エントリが必要。DC が応答しなくなってもエントリ自体は残るため。
        """
        msg = access_denied_message("PutObject", "my-ap-ext-s3alias")

        assert "ms_dc" in msg
        assert "state=ok" in msg
        assert "discovered_servers" in msg
        assert "ad_health_check" in msg
        # 件数だけで判断させない注意書き
        assert "not sufficient" in msg

    def test_does_not_assert_ad_is_the_cause(self):
        """AD が原因だと断定しないことを検証する

        S3ApHelper は AP のエイリアス/ARN しか知らず SVM 名を持たないため、AD 参加
        SVM かどうかを判定できない。断定ではなく可能性として示す必要がある。
        """
        msg = access_denied_message("ListObjectsV2", "my-ap-ext-s3alias")

        lowered = msg.lower()
        assert "two possible layers" in lowered
        # 断定的な言い回しを禁止する
        for forbidden in (
            "this is an ad",
            "the cause is ad",
            "caused by ad",
            "must be ad",
        ):
            assert forbidden not in lowered

    def test_includes_access_point_arn_form_hint(self):
        """AP 形式の ARN が必要である点に触れることを検証する"""
        msg = access_denied_message("ListObjectsV2", "my-ap-ext-s3alias")

        assert "accesspoint/" in msg
        assert "bucket-style" in msg

    def test_includes_operation_and_access_point(self):
        """操作名と Access Point 名がメッセージに含まれることを検証する"""
        msg = access_denied_message("DeleteObject", "some-ap-ext-s3alias")

        assert "DeleteObject" in msg
        assert "some-ap-ext-s3alias" in msg

    def test_detail_is_optional(self):
        """detail を省略しても括弧が空で残らないことを検証する"""
        # 本文には check_ad_dc_reachability() など括弧を含む記述があるため、
        # 件名（1 行目）だけを見る
        without = access_denied_message("GetObject", "my-ap").splitlines()[0]
        assert "()" not in without
        assert "my-ap" in without

        with_detail = access_denied_message("GetObject", "my-ap", detail="key='a/b.csv'").splitlines()[0]
        assert "(key='a/b.csv')" in with_detail

    # --- 各操作の except 節が診断メッセージを使っていることを検証する ---

    @pytest.mark.parametrize(
        "invoke,client_method",
        [
            (lambda h: h.list_objects(prefix="data/"), "list_objects_v2"),
            (lambda h: h.get_object("a.csv"), "get_object"),
            (lambda h: h.put_object("a.csv", b"x"), "put_object"),
            (lambda h: h.head_object("a.csv"), "head_object"),
            (lambda h: h.delete_object("a.csv"), "delete_object"),
            (lambda h: list(h.streaming_download("a.csv")), "get_object"),
            (lambda h: h.streaming_download_range("a.csv", 0, 10), "get_object"),
            (
                lambda h: h.multipart_upload("a.csv", iter([b"x"])),
                "create_multipart_upload",
            ),
        ],
        ids=[
            "list_objects",
            "get_object",
            "put_object",
            "head_object",
            "delete_object",
            "streaming_download",
            "streaming_download_range",
            "multipart_upload",
        ],
    )
    def test_every_operation_emits_both_layers(self, alias_helper, mock_session, invoke, client_method):
        """全 8 操作の AccessDenied が両層に言及することを検証する

        1 箇所だけ IAM のみの旧文面が残る、という事故を防ぐ。
        """
        client = mock_session.client.return_value
        getattr(client, client_method).side_effect = _make_client_error(code="AccessDenied")

        with pytest.raises(S3ApHelperError) as exc_info:
            invoke(alias_helper)

        msg = str(exc_info.value)
        assert exc_info.value.error_code == "AccessDenied"
        assert "IAM" in msg
        assert "file-system" in msg
        assert "HeadBucket" in msg
        assert "ms_dc" in msg

    def test_non_access_denied_keeps_plain_message(self, alias_helper, mock_session):
        """AccessDenied 以外では診断メッセージを付けないことを検証する

        NoSuchKey 等に AD の話を出すとノイズになる。
        """
        client = mock_session.client.return_value
        client.get_object.side_effect = _make_client_error(code="NoSuchKey")

        with pytest.raises(S3ApHelperError) as exc_info:
            alias_helper.get_object("missing.csv")

        msg = str(exc_info.value)
        assert exc_info.value.error_code == "NoSuchKey"
        assert "HeadBucket" not in msg
        assert "ms_dc" not in msg
