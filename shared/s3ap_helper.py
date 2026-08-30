"""S3 Access Point ヘルパー

FSx for NetApp ONTAP の S3 Access Points 経由のデータアクセスを抽象化する共通モジュール。
ListObjectsV2、GetObject、PutObject、ページネーション、サフィックスフィルタを提供する。

FSx for ONTAP S3 Access Points は S3 API のサブセットのみをサポートするため、
SUPPORTED_OPERATIONS で互換 API を明示する。

Key patterns:
- Alias (xxx-ext-s3alias) と ARN の両形式を bucket_param として受け付ける
- list_objects: ContinuationToken による自動ページネーション + クライアントサイドサフィックスフィルタ
- AccessDenied エラー時に S3ApHelperError で記述的なメッセージを返す
"""

from __future__ import annotations

import logging
from typing import Iterator

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from shared.exceptions import S3ApHelperError

logger = logging.getLogger(__name__)

# AccessDenied のとき、原因は 2 つの層のどちらかにある。
#
# これまでこのモジュールのメッセージは IAM と AP ポリシーだけを指していた。原因が
# もう一方の層にあるとき、その案内は真逆の方向へ人を送る。AD 参加 SVM（CIFS 有効）
# では、ONTAP が S3 AP のデータ操作ごとに unix→win の逆引き name-mapping を行い、
# これには AD DC への LDAP/Kerberos 接続が必要になる。DC に到達できないと
# ListObjectsV2 / GetObject / PutObject は AccessDenied になる。IAM も AP ポリシーも
# ネットワーク経路も正常なまま失敗するため、切り分けが難しい。
#
# 見分け方: HeadBucket は S3 メタデータ層だけを見るので、この状況でも成功する。
# HeadBucket が通ってデータ操作が AccessDenied なら、IAM ではなくファイルシステム層。
#
# ここで「AD の問題だ」と断定はしない。SVM 名を知らないので判定できない。両方の
# 可能性と、切り分ける手順を示すのが正しい。
#
# AWS 側の案内で ARN 形式に触れるのは、これが公式に記録された原因だから:
# https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/troubleshooting-access-points-for-fsxn.html
# （"Access Denied with default S3 access point permissions for automatically created
# service roles" — バケット ARN 形式が使われている場合は AP の ARN に直す）
#
# 「AP ポリシーが無いこと」は原因として挙げない。同一アカウントでは identity-based と
# AP ポリシーが結合して評価され、どちらかが許可すれば通るため、ポリシー未設定は
# 正常に動作する状態である（実測 2026-08-17/18, ap-northeast-1, ONTAP 9.18.1P3D1 —
# docs/s3ap-authorization-model.md）。原因になるのは AP ポリシー側の明示的な拒否で、
# その場合はエラー本文に with an explicit deny in a resource-based policy が入る。
_ACCESS_DENIED_LAYERS = (
    "AccessDenied has two possible layers here.\n"
    "  1. AWS side — the IAM identity policy, or an explicit Deny in the Access Point "
    "policy. Note that the Resource ARN must be the Access Point form "
    "(arn:aws:s3:<region>:<account>:accesspoint/<name>[/object/*]); a bucket-style "
    "ARN does not work. Having no Access Point policy at all is not a cause: within a "
    "single account the identity-based policy alone establishes the allow.\n"
    "  2. ONTAP file-system side — on an AD-joined SVM (CIFS enabled), every data "
    "operation needs the SVM to reach its AD domain controllers. When they are "
    "unreachable, this call fails while IAM, the AP policy and the network are all "
    "correct.\n"
    "To tell them apart, call HeadBucket on the same Access Point. HeadBucket only "
    "checks the S3 metadata layer, so it succeeds in case 2 — a HeadBucket that "
    "works alongside a failing data operation points at the file system, not IAM.\n"
    "For case 2, check DC reachability with shared.ad_health_check."
    "check_ad_dc_reachability(), or:\n"
    "  GET /api/protocols/cifs/domains?svm.name=<svm>&fields=discovered_servers\n"
    "and look for at least one entry with server_type=ms_dc and state=ok. A "
    "non-empty list is not sufficient: entries persist after the controllers stop "
    "answering."
)


def access_denied_message(operation: str, access_point: str, detail: str = "") -> str:
    """AccessDenied 用のメッセージを組み立てる。

    7 箇所の except 節が同じ本文を使うため、1 箇所にまとめている。片方の層の案内
    だけが残る事故を防ぐのが狙い。

    Args:
        operation: 失敗した S3 操作（例: "ListObjectsV2"）
        access_point: 対象の S3 AP Alias または ARN
        detail: 対象キーなどの追加情報（任意）
    """
    subject = f"{operation} on S3 Access Point '{access_point}'"
    if detail:
        subject = f"{subject} ({detail})"
    return f"Access denied: {subject}.\n{_ACCESS_DENIED_LAYERS}"


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
                    access_denied_message(
                        "ListObjectsV2",
                        self._access_point,
                        detail=f"prefix='{prefix}'",
                    )
                    + f"\nOriginal error: {e}",
                    error_code=error_code,
                ) from e
            raise S3ApHelperError(
                f"Failed to list objects from S3 Access Point '{self._access_point}' (prefix='{prefix}'): {e}",
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
                    access_denied_message(
                        "GetObject",
                        self._access_point,
                        detail=f"key='{key}'",
                    )
                    + f"\nOriginal error: {e}",
                    error_code=error_code,
                ) from e
            raise S3ApHelperError(
                f"Failed to get object '{key}' from S3 Access Point '{self._access_point}': {e}",
                error_code=error_code,
            ) from e

    # Rekognition の DetectLabels / DetectText と Textract の同期 API に bytes を
    # 直接渡せる上限。S3 参照（S3Object）は FSx for ONTAP の S3 AP では使えないため、
    # これらのサービスへ渡すデータはいったん取得して inline で渡す必要がある。
    MAX_INLINE_AI_BYTES = 5 * 1024 * 1024

    def get_object_bytes(self, key: str, max_bytes: int | None = None) -> bytes:
        """オブジェクトを bytes として取得する。

        Rekognition / Textract に画像や文書を渡すための入口。**これらのサービスは
        FSx for ONTAP の S3 Access Point 上のオブジェクトを `S3Object` 参照では
        読めない**（`InvalidS3ObjectException: Unable to get object metadata from S3`
        になる。AP ポリシーにサービスプリンシパルを許可しても解消しない）。
        そのため、AP から bytes を取得して `Image={"Bytes": ...}` /
        `Document={"Bytes": ...}` の形で渡す。

        Args:
            key: オブジェクトキー
            max_bytes: 上限バイト数。既定は同期 AI API の inline 上限
                (:attr:`MAX_INLINE_AI_BYTES`)。上限を超える場合は取得せずに失敗させる。

        Returns:
            bytes: オブジェクトの内容

        Raises:
            S3ApHelperError: 取得に失敗した場合、または上限を超えた場合
        """
        limit = self.MAX_INLINE_AI_BYTES if max_bytes is None else max_bytes

        # 先に大きさを確認する。上限超過を取得後に気づくと、無駄に転送した上で
        # サービス側が曖昧なエラーを返すことになる。
        head = self.head_object(key)
        size = head.get("ContentLength", 0)
        if size > limit:
            raise S3ApHelperError(
                f"Object '{key}' is {size} bytes, over the {limit} byte inline limit for "
                "synchronous Rekognition/Textract calls. Use an asynchronous API with a "
                "real S3 bucket, or downsample before analysis.",
                error_code="ObjectTooLargeForInlineAnalysis",
            )

        return self.get_object(key)["Body"].read()

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
            FSx for ONTAP S3 Access Points の PutObject は最大 5 GB まで。
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
                    access_denied_message(
                        "PutObject",
                        self._access_point,
                        detail=f"key='{key}'",
                    )
                    + f"\nOriginal error: {e}",
                    error_code=error_code,
                ) from e
            raise S3ApHelperError(
                f"Failed to put object '{key}' to S3 Access Point '{self._access_point}': {e}",
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
                    access_denied_message(
                        "HeadObject",
                        self._access_point,
                        detail=f"key='{key}'",
                    )
                    + f"\nOriginal error: {e}",
                    error_code=error_code,
                ) from e
            raise S3ApHelperError(
                f"Failed to head object '{key}' from S3 Access Point '{self._access_point}': {e}",
                error_code=error_code,
            ) from e

    def generate_presigned_get_url(self, key: str, expires_in: int = 300) -> str:
        """GetObject の presigned URL を生成する

        **この URL は Access Point に固定された ONTAP identity として実行される。**
        受け取った側は AWS の資格情報を持たないが、Layer 2 の権限はこの identity に
        対して評価される。実測（2026-08-26 / ONTAP 9.18.1P3D1）では、UNIX root を
        固定した AP で署名した URL が mode 0700・他 uid 所有のディレクトリの中身を
        返し、読み取り専用 identity の AP で署名した同じキーは 403 だった。
        **どの AP で署名するかが認可の実体なので、呼び出し側は AP を利用者の
        グループから決めること。**

        `self._s3_client` を使わず専用のクライアントを作る。presigned URL は
        リージョンのエンドポイントと SigV4 を明示した構成で生成する必要があり、
        既定のクライアントはその構成を持たない。共有すると、既定クライアントの
        構成変更が署名の成否に波及する。

        Args:
            key: オブジェクトキー
            expires_in: 有効期限（秒）

        Returns:
            str: presigned URL

        Raises:
            S3ApHelperError: URL 生成に失敗した場合
        """
        try:
            region = self._session.region_name or "ap-northeast-1"
            signer = self._session.client(
                "s3",
                region_name=region,
                endpoint_url=f"https://s3.{region}.amazonaws.com",
                config=BotoConfig(signature_version="s3v4"),
            )
            return signer.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_param, "Key": key},
                ExpiresIn=expires_in,
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            raise S3ApHelperError(
                f"Failed to presign GetObject for '{key}' on S3 Access Point '{self._access_point}': {e}",
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
                    access_denied_message(
                        "DeleteObject",
                        self._access_point,
                        detail=f"key='{key}'",
                    )
                    + f"\nOriginal error: {e}",
                    error_code=error_code,
                ) from e
            raise S3ApHelperError(
                f"Failed to delete object '{key}' from S3 Access Point '{self._access_point}': {e}",
                error_code=error_code,
            ) from e

    # ------------------------------------------------------------------ #
    # Phase 2: ストリーミングダウンロード / マルチパートアップロード
    # ------------------------------------------------------------------ #

    def streaming_download(
        self,
        key: str,
        chunk_size: int = 8 * 1024 * 1024,
    ) -> Iterator[bytes]:
        """ストリーミングダウンロード（大規模ファイル対応）

        メモリに全体をロードせず、チャンク単位で yield する。
        TB/PB クラスのファイルでも Lambda メモリ制限内で処理可能。

        Args:
            key: オブジェクトキー
            chunk_size: チャンクサイズ（デフォルト: 8 MB）

        Yields:
            bytes: ファイルデータのチャンク

        Raises:
            S3ApHelperError: S3 API 呼び出しに失敗した場合
        """
        try:
            response = self._s3_client.get_object(
                Bucket=self.bucket_param,
                Key=key,
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "AccessDenied":
                raise S3ApHelperError(
                    access_denied_message(
                        "GetObject",
                        self._access_point,
                        detail=f"streaming key='{key}'",
                    )
                    + f"\nOriginal error: {e}",
                    error_code=error_code,
                ) from e
            raise S3ApHelperError(
                f"Failed to stream object '{key}' from S3 Access Point '{self._access_point}': {e}",
                error_code=error_code,
            ) from e

        body = response["Body"]
        try:
            while True:
                chunk = body.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            body.close()

    def streaming_download_range(
        self,
        key: str,
        start: int,
        end: int,
    ) -> bytes:
        """Range リクエストによる部分ダウンロード

        SEG-Y ヘッダー（先頭 3600 バイト）等、ファイルの一部のみ取得する場合に使用。

        Args:
            key: オブジェクトキー
            start: 開始バイト位置
            end: 終了バイト位置

        Returns:
            bytes: 指定範囲のデータ

        Raises:
            S3ApHelperError: S3 API 呼び出しに失敗した場合
        """
        try:
            response = self._s3_client.get_object(
                Bucket=self.bucket_param,
                Key=key,
                Range=f"bytes={start}-{end}",
            )
            return response["Body"].read()
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "AccessDenied":
                raise S3ApHelperError(
                    access_denied_message(
                        "GetObject",
                        self._access_point,
                        detail=f"range bytes={start}-{end} key='{key}'",
                    )
                    + f"\nOriginal error: {e}",
                    error_code=error_code,
                ) from e
            raise S3ApHelperError(
                f"Failed to download range of object '{key}' from S3 Access Point '{self._access_point}': {e}",
                error_code=error_code,
            ) from e

    def multipart_upload(
        self,
        key: str,
        data_iterator: Iterator[bytes],
        content_type: str = "application/octet-stream",
        part_size: int = 100 * 1024 * 1024,
    ) -> dict:
        """マルチパートアップロード（100 MB 超ファイル対応）

        CreateMultipartUpload, UploadPart, CompleteMultipartUpload を使用する。
        失敗時は AbortMultipartUpload で確実にクリーンアップする。

        Args:
            key: 出力先オブジェクトキー
            data_iterator: データチャンクの Iterator
            content_type: Content-Type (デフォルト: "application/octet-stream")
            part_size: パートサイズ（デフォルト: 100 MB）

        Returns:
            dict: CompleteMultipartUpload レスポンス

        Raises:
            S3ApHelperError: マルチパートアップロードに失敗した場合
        """
        try:
            create_resp = self._s3_client.create_multipart_upload(
                Bucket=self.bucket_param,
                Key=key,
                ContentType=content_type,
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "AccessDenied":
                raise S3ApHelperError(
                    access_denied_message(
                        "CreateMultipartUpload",
                        self._access_point,
                        detail=f"key='{key}'",
                    )
                    + f"\nOriginal error: {e}",
                    error_code=error_code,
                ) from e
            raise S3ApHelperError(
                f"Failed to create multipart upload for key '{key}' on S3 Access Point '{self._access_point}': {e}",
                error_code=error_code,
            ) from e

        upload_id = create_resp["UploadId"]
        parts: list[dict] = []
        part_number = 1
        buffer = b""

        try:
            for chunk in data_iterator:
                buffer += chunk
                while len(buffer) >= part_size:
                    part_data = buffer[:part_size]
                    buffer = buffer[part_size:]

                    upload_resp = self._s3_client.upload_part(
                        Bucket=self.bucket_param,
                        Key=key,
                        UploadId=upload_id,
                        PartNumber=part_number,
                        Body=part_data,
                    )
                    parts.append(
                        {
                            "PartNumber": part_number,
                            "ETag": upload_resp["ETag"],
                        }
                    )
                    part_number += 1

            # 残りのバッファをアップロード
            if buffer:
                upload_resp = self._s3_client.upload_part(
                    Bucket=self.bucket_param,
                    Key=key,
                    UploadId=upload_id,
                    PartNumber=part_number,
                    Body=buffer,
                )
                parts.append(
                    {
                        "PartNumber": part_number,
                        "ETag": upload_resp["ETag"],
                    }
                )

            # CompleteMultipartUpload
            return self._s3_client.complete_multipart_upload(
                Bucket=self.bucket_param,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )

        except Exception as e:
            # 失敗時は AbortMultipartUpload で確実にクリーンアップ
            logger.error(
                "Multipart upload failed for key '%s', aborting upload_id '%s': %s",
                key,
                upload_id,
                str(e),
            )
            try:
                self._s3_client.abort_multipart_upload(
                    Bucket=self.bucket_param,
                    Key=key,
                    UploadId=upload_id,
                )
            except ClientError as abort_err:
                logger.warning(
                    "Failed to abort multipart upload '%s' for key '%s': %s",
                    upload_id,
                    key,
                    str(abort_err),
                )
            raise S3ApHelperError(
                f"Multipart upload failed for key '{key}': {e}",
                error_code="MultipartUploadFailed",
            ) from e
