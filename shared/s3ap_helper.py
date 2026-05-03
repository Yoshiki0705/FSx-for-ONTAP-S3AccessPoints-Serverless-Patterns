"""S3 Access Point ヘルパー

FSx for NetApp ONTAP の S3 Access Points 経由のデータアクセスを抽象化する共通モジュール。
ListObjectsV2、GetObject、PutObject、ページネーション、サフィックスフィルタを提供する。

FSx ONTAP S3 Access Points は S3 API のサブセットのみをサポートするため、
SUPPORTED_OPERATIONS で互換 API を明示する。

Key patterns:
- Alias (xxx-ext-s3alias) と ARN の両形式を bucket_param として受け付ける
- list_objects: ContinuationToken による自動ページネーション + クライアントサイドサフィックスフィルタ
- AccessDenied エラー時に S3ApHelperError で記述的なメッセージを返す
"""

from __future__ import annotations

import logging

import boto3
from botocore.exceptions import ClientError

from shared.exceptions import S3ApHelperError

logger = logging.getLogger(__name__)


class S3ApHelper:
    """S3 Access Point ヘルパー

    FSx for NetApp ONTAP の S3 Access Points 経由でオブジェクトの
    一覧取得、読み書き、メタデータ取得、削除を行う。

    Usage:
        helper = S3ApHelper("vol-name-xxxxx-ext-s3alias")
        objects = helper.list_objects(prefix="data/", suffix=".csv")
        response = helper.get_object("data/sensor-001.csv")
    """

    SUPPORTED_OPERATIONS = [
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

    def __init__(
        self,
        access_point: str,
        session: boto3.Session | None = None,
    ):
        """S3ApHelper を初期化

        Args:
            access_point: S3 AP Alias (例: vol-name-xxxxx-ext-s3alias)
                          または ARN (例: arn:aws:s3:ap-northeast-1:123456789012:accesspoint/name)
            session: boto3 セッション (オプション)。
                     クロスアカウント/クロスリージョンアクセス時に指定する。
        """
        self._access_point = access_point
        self._session = session or boto3.Session()
        self._s3_client = self._session.client("s3")

    @property
    def bucket_param(self) -> str:
        """S3 API の Bucket パラメータとして使用する値を返す

        Alias 形式と ARN 形式の両方をそのまま Bucket パラメータとして使用する。
        S3 API は Access Point Alias および ARN を Bucket パラメータとして受け付ける。

        Returns:
            str: S3 API の Bucket パラメータ値
        """
        return self._access_point

    def list_objects(
        self,
        prefix: str = "",
        suffix: str = "",
        max_keys: int = 1000,
    ) -> list[dict]:
        """オブジェクト一覧取得（自動ページネーション + サフィックスフィルタ）

        ContinuationToken を使用して全ページを自動的に取得する。
        S3 API はプレフィックスフィルタのみサポートするため、
        サフィックスフィルタはクライアントサイドで適用する。

        Args:
            prefix: プレフィックスフィルタ (例: "data/sensors/")
            suffix: サフィックスフィルタ (例: ".json", ".csv", ".dcm")
            max_keys: 1回の API コールあたりの最大キー数 (デフォルト: 1000)

        Returns:
            list[dict]: オブジェクト情報のリスト。各要素は以下のキーを含む:
                - Key (str): オブジェクトキー
                - Size (int): オブジェクトサイズ（バイト）
                - LastModified (datetime): 最終更新日時
                - ETag (str): エンティティタグ

        Raises:
            S3ApHelperError: S3 API 呼び出しに失敗した場合
        """
        all_objects: list[dict] = []
        continuation_token: str | None = None

        try:
            while True:
                kwargs: dict = {
                    "Bucket": self.bucket_param,
                    "MaxKeys": max_keys,
                }
                if prefix:
                    kwargs["Prefix"] = prefix
                if continuation_token:
                    kwargs["ContinuationToken"] = continuation_token

                response = self._s3_client.list_objects_v2(**kwargs)

                contents = response.get("Contents", [])
                for obj in contents:
                    item = {
                        "Key": obj["Key"],
                        "Size": obj["Size"],
                        "LastModified": obj["LastModified"].isoformat()
                        if hasattr(obj["LastModified"], "isoformat")
                        else str(obj["LastModified"]),
                        "ETag": obj.get("ETag", ""),
                    }
                    # サフィックスフィルタをクライアントサイドで適用
                    if suffix and not item["Key"].endswith(suffix):
                        continue
                    all_objects.append(item)

                # ページネーション: 次のページがあれば続行
                if response.get("IsTruncated"):
                    continuation_token = response.get("NextContinuationToken")
                    if not continuation_token:
                        break
                else:
                    break

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "AccessDenied":
                raise S3ApHelperError(
                    f"Access denied to S3 Access Point '{self._access_point}'. "
                    f"Verify that the IAM role has s3:ListBucket permission "
                    f"on the Access Point and that the Access Point policy "
                    f"allows the operation. Original error: {e}",
                    error_code=error_code,
                ) from e
            raise S3ApHelperError(
                f"Failed to list objects from S3 Access Point "
                f"'{self._access_point}' (prefix='{prefix}'): {e}",
                error_code=error_code,
            ) from e

        return all_objects

    def get_object(self, key: str) -> dict:
        """オブジェクト取得

        Args:
            key: オブジェクトキー

        Returns:
            dict: S3 GetObject レスポンス。以下のキーを含む:
                - Body (StreamingBody): オブジェクトデータ
                - ContentLength (int): コンテンツ長
                - ContentType (str): コンテンツタイプ
                - ETag (str): エンティティタグ

        Raises:
            S3ApHelperError: S3 API 呼び出しに失敗した場合
        """
        try:
            return self._s3_client.get_object(
                Bucket=self.bucket_param,
                Key=key,
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "AccessDenied":
                raise S3ApHelperError(
                    f"Access denied when getting object '{key}' from "
                    f"S3 Access Point '{self._access_point}'. "
                    f"Verify that the IAM role has s3:GetObject permission "
                    f"on the Access Point. Original error: {e}",
                    error_code=error_code,
                ) from e
            raise S3ApHelperError(
                f"Failed to get object '{key}' from S3 Access Point "
                f"'{self._access_point}': {e}",
                error_code=error_code,
            ) from e

    def put_object(
        self,
        key: str,
        body: bytes | str,
        content_type: str = "application/octet-stream",
    ) -> dict:
        """オブジェクト書き込み

        Args:
            key: オブジェクトキー
            body: 書き込むデータ (bytes または str)
            content_type: コンテンツタイプ (デフォルト: "application/octet-stream")

        Returns:
            dict: S3 PutObject レスポンス

        Raises:
            S3ApHelperError: S3 API 呼び出しに失敗した場合

        Note:
            FSx ONTAP S3 Access Points の PutObject は最大 5 GB まで。
            5 GB を超えるファイルはマルチパートアップロードを使用すること。
            暗号化は FSx が SSE-FSX で透過的に処理するため、
            ServerSideEncryption パラメータは指定不要。
        """
        if isinstance(body, str):
            body = body.encode("utf-8")

        try:
            return self._s3_client.put_object(
                Bucket=self.bucket_param,
                Key=key,
                Body=body,
                ContentType=content_type,
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "AccessDenied":
                raise S3ApHelperError(
                    f"Access denied when putting object '{key}' to "
                    f"S3 Access Point '{self._access_point}'. "
                    f"Verify that the IAM role has s3:PutObject permission "
                    f"on the Access Point. Original error: {e}",
                    error_code=error_code,
                ) from e
            raise S3ApHelperError(
                f"Failed to put object '{key}' to S3 Access Point "
                f"'{self._access_point}': {e}",
                error_code=error_code,
            ) from e

    def head_object(self, key: str) -> dict:
        """オブジェクトメタデータ取得

        Args:
            key: オブジェクトキー

        Returns:
            dict: S3 HeadObject レスポンス。以下のキーを含む:
                - ContentLength (int): コンテンツ長
                - ContentType (str): コンテンツタイプ
                - ETag (str): エンティティタグ
                - LastModified (datetime): 最終更新日時

        Raises:
            S3ApHelperError: S3 API 呼び出しに失敗した場合
        """
        try:
            return self._s3_client.head_object(
                Bucket=self.bucket_param,
                Key=key,
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "AccessDenied":
                raise S3ApHelperError(
                    f"Access denied when heading object '{key}' from "
                    f"S3 Access Point '{self._access_point}'. "
                    f"Verify that the IAM role has s3:GetObject permission "
                    f"on the Access Point. Original error: {e}",
                    error_code=error_code,
                ) from e
            raise S3ApHelperError(
                f"Failed to head object '{key}' from S3 Access Point "
                f"'{self._access_point}': {e}",
                error_code=error_code,
            ) from e

    def delete_object(self, key: str) -> dict:
        """オブジェクト削除

        Args:
            key: オブジェクトキー

        Returns:
            dict: S3 DeleteObject レスポンス

        Raises:
            S3ApHelperError: S3 API 呼び出しに失敗した場合
        """
        try:
            return self._s3_client.delete_object(
                Bucket=self.bucket_param,
                Key=key,
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "AccessDenied":
                raise S3ApHelperError(
                    f"Access denied when deleting object '{key}' from "
                    f"S3 Access Point '{self._access_point}'. "
                    f"Verify that the IAM role has s3:DeleteObject permission "
                    f"on the Access Point. Original error: {e}",
                    error_code=error_code,
                ) from e
            raise S3ApHelperError(
                f"Failed to delete object '{key}' from S3 Access Point "
                f"'{self._access_point}': {e}",
                error_code=error_code,
            ) from e
