"""Output Writer — 標準 S3 バケットと FSxN S3 Access Points の両方に対応した出力ヘルパー

各 UC の Lambda ハンドラが生成した成果物（JSON/TEXT/バイナリ）を、
環境変数 `OUTPUT_DESTINATION` に応じて以下のいずれかに書き込む:

- `STANDARD_S3` (デフォルト): `OUTPUT_BUCKET` で指定された通常の S3 バケット
- `FSXN_S3AP`: `OUTPUT_S3AP_ALIAS` で指定された FSx for NetApp ONTAP S3 Access Point

### なぜこのヘルパーが必要か

プロジェクトの核となる価値提案は "enterprise file data on FSxN consumed by AI/ML/Analytics
services with no data movement" である。従来は Lambda ハンドラが直接
`boto3.client('s3').put_object(Bucket=OUTPUT_BUCKET, ...)` で標準 S3 に書き込んでいた。

しかし FSxN S3AP は PutObject を Supported としており
(docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)、
Bedrock/Rekognition/Textract の出力 JSON 等を FSxN S3AP に書き戻せば、SMB/NFS
ユーザーが既存のディレクトリ構造の中で AI 成果物を閲覧できる。

本ヘルパーは以下の責務を持つ:
1. 出力先の切替（STANDARD_S3 / FSXN_S3AP）
2. FSxN S3AP 仕様への準拠:
   - SSE-FSX が強制されるため `ServerSideEncryption` は渡さない
   - `GetObjectAcl` / `PutObjectAcl` は `bucket-owner-full-control` のみサポート
   - 5GB を超える場合はマルチパートアップロード（`shared.s3ap_helper` 側で対応）
3. FSxN S3AP モード時のプレフィックス付与（`OUTPUT_S3AP_PREFIX`）

### Environment Variables

| 変数 | 用途 | デフォルト |
|------|------|----------|
| `OUTPUT_DESTINATION` | `STANDARD_S3` or `FSXN_S3AP` | `STANDARD_S3` |
| `OUTPUT_BUCKET` | STANDARD_S3 モードの書き込み先バケット名 | (必須 for STANDARD_S3) |
| `OUTPUT_S3AP_ALIAS` | FSXN_S3AP モードの書き込み先 S3AP Alias or ARN | (必須 for FSXN_S3AP) |
| `OUTPUT_S3AP_PREFIX` | FSXN_S3AP モードで全出力キーに付与するプレフィックス | `ai-outputs/` |

### Usage

```python
from shared.output_writer import OutputWriter

writer = OutputWriter.from_env()
writer.put_json(
    key="assessments/2026/05/10/claim_001.json",
    data={"claim_id": "CLM-001", "status": "APPROVED"},
)
```
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Iterator

import boto3
from botocore.exceptions import ClientError

from shared.exceptions import S3ApHelperError

logger = logging.getLogger(__name__)


# 出力先の定数
STANDARD_S3 = "STANDARD_S3"
FSXN_S3AP = "FSXN_S3AP"
VALID_DESTINATIONS = {STANDARD_S3, FSXN_S3AP}

# デフォルト値
DEFAULT_S3AP_PREFIX = "ai-outputs/"


class OutputWriterError(Exception):
    """OutputWriter 設定エラー"""

    pass


# 5 GB limit for single PutObject
_MAX_PUT_OBJECT_SIZE = 5 * 1024 * 1024 * 1024


def _chunk_bytes(data: bytes, part_size: int):
    """Split bytes into chunks of part_size."""
    for i in range(0, len(data), part_size):
        yield data[i : i + part_size]


class OutputWriter:
    """出力先を環境変数で切替可能な S3 書き込みヘルパー

    OutputDestination が `STANDARD_S3` の場合は通常の S3 バケットに、
    `FSXN_S3AP` の場合は FSx for NetApp ONTAP の S3 Access Point に書き込む。
    """

    def __init__(
        self,
        destination: str,
        bucket: str | None = None,
        s3ap_alias: str | None = None,
        s3ap_prefix: str = DEFAULT_S3AP_PREFIX,
        session: boto3.Session | None = None,
    ):
        """OutputWriter を初期化

        Args:
            destination: `STANDARD_S3` または `FSXN_S3AP`
            bucket: STANDARD_S3 モード時の書き込み先バケット名
            s3ap_alias: FSXN_S3AP モード時の S3 Access Point Alias または ARN
            s3ap_prefix: FSXN_S3AP モード時に全出力キーに付与するプレフィックス
            session: boto3 セッション (オプション)

        Raises:
            OutputWriterError: 必須設定が欠落している場合
        """
        if destination not in VALID_DESTINATIONS:
            raise OutputWriterError(
                f"Invalid OUTPUT_DESTINATION '{destination}'. "
                f"Must be one of: {sorted(VALID_DESTINATIONS)}"
            )

        if destination == STANDARD_S3:
            if not bucket:
                raise OutputWriterError(
                    "OUTPUT_BUCKET is required when OUTPUT_DESTINATION=STANDARD_S3"
                )
        elif destination == FSXN_S3AP:
            if not s3ap_alias:
                raise OutputWriterError(
                    "OUTPUT_S3AP_ALIAS is required when OUTPUT_DESTINATION=FSXN_S3AP"
                )

        self._destination = destination
        self._bucket = bucket
        self._s3ap_alias = s3ap_alias
        self._s3ap_prefix = s3ap_prefix.rstrip("/") + "/" if s3ap_prefix else ""
        self._session = session or boto3.Session()
        self._s3_client = self._session.client("s3")

    @classmethod
    def from_env(cls, session: boto3.Session | None = None) -> OutputWriter:
        """環境変数から OutputWriter を構築

        環境変数の優先順位:
        - `OUTPUT_DESTINATION`: `STANDARD_S3` / `FSXN_S3AP` (デフォルト: `STANDARD_S3`)
        - `OUTPUT_BUCKET`: STANDARD_S3 モード時のバケット名
        - `OUTPUT_S3AP_ALIAS`: FSXN_S3AP モード時の S3AP Alias or ARN
        - `OUTPUT_S3AP_PREFIX`: FSXN_S3AP モード時のプレフィックス (デフォルト: `ai-outputs/`)

        Returns:
            OutputWriter: 環境変数から構築されたインスタンス

        Raises:
            OutputWriterError: 必須環境変数が欠落している場合
        """
        destination = os.environ.get("OUTPUT_DESTINATION", STANDARD_S3).upper()
        bucket = os.environ.get("OUTPUT_BUCKET")
        s3ap_alias = os.environ.get("OUTPUT_S3AP_ALIAS")
        s3ap_prefix = os.environ.get("OUTPUT_S3AP_PREFIX", DEFAULT_S3AP_PREFIX)

        return cls(
            destination=destination,
            bucket=bucket,
            s3ap_alias=s3ap_alias,
            s3ap_prefix=s3ap_prefix,
            session=session,
        )

    @property
    def destination(self) -> str:
        """書き込み先のタイプを返す (`STANDARD_S3` or `FSXN_S3AP`)"""
        return self._destination

    @property
    def target_description(self) -> str:
        """書き込み先の人間可読な説明を返す（ログ出力用）"""
        if self._destination == STANDARD_S3:
            return f"Standard S3 bucket '{self._bucket}'"
        return f"FSxN S3 Access Point '{self._s3ap_alias}' (prefix: {self._s3ap_prefix!r})"

    def _resolve_target(self, key: str) -> tuple[str, str]:
        """書き込み先の Bucket パラメータと実際のキーを返す

        Args:
            key: 論理的なオブジェクトキー

        Returns:
            tuple[str, str]: (bucket_param, resolved_key)
                bucket_param は put_object の Bucket パラメータにそのまま渡せる値
                resolved_key はプレフィックス付与後の実キー
        """
        if self._destination == STANDARD_S3:
            return self._bucket, key  # type: ignore[return-value]
        # FSXN_S3AP: alias or ARN をそのまま Bucket として使用
        resolved_key = f"{self._s3ap_prefix}{key.lstrip('/')}" if self._s3ap_prefix else key
        return self._s3ap_alias, resolved_key  # type: ignore[return-value]

    def put_bytes(
        self,
        key: str,
        body: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """バイナリデータを書き込む

        Args:
            key: オブジェクトキー
            body: バイナリデータ
            content_type: Content-Type (デフォルト: "application/octet-stream")

        Returns:
            dict: 以下のキーを含む:
                - destination (str): `STANDARD_S3` or `FSXN_S3AP`
                - bucket_or_ap (str): 書き込み先
                - key (str): 実際の書き込みキー（プレフィックス付与後）
                - etag (str): ETag
                - size (int): サイズ（バイト）

        Raises:
            OutputWriterError: body が 5 GB を超える場合
            S3ApHelperError: FSxN S3AP への書き込み失敗時
            ClientError: 標準 S3 への書き込み失敗時
        """
        if len(body) > _MAX_PUT_OBJECT_SIZE:
            raise OutputWriterError(
                f"Body size {len(body):,} bytes exceeds 5 GB limit for put_object. "
                f"Use put_stream() or put_file() for large objects."
            )

        bucket_param, resolved_key = self._resolve_target(key)

        # FSxN S3AP は SSE-FSX のみサポートなので ServerSideEncryption は渡さない
        put_kwargs = {
            "Bucket": bucket_param,
            "Key": resolved_key,
            "Body": body,
            "ContentType": content_type,
        }

        try:
            response = self._s3_client.put_object(**put_kwargs)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if self._destination == FSXN_S3AP:
                raise S3ApHelperError(
                    f"Failed to put object '{resolved_key}' to "
                    f"FSxN S3 Access Point '{self._s3ap_alias}': {e}. "
                    f"Note: FSxN S3AP requires SSE-FSX (auto) and has a 5GB object size limit.",
                    error_code=error_code,
                ) from e
            raise

        logger.info(
            "Output written: destination=%s, target=%s, key=%s, size=%d, etag=%s",
            self._destination,
            bucket_param,
            resolved_key,
            len(body),
            response.get("ETag", ""),
        )

        return {
            "destination": self._destination,
            "bucket_or_ap": bucket_param,
            "key": resolved_key,
            "etag": response.get("ETag", ""),
            "size": len(body),
        }

    def put_text(
        self,
        key: str,
        text: str,
        content_type: str = "text/plain; charset=utf-8",
    ) -> dict[str, Any]:
        """テキストデータを書き込む

        Args:
            key: オブジェクトキー
            text: テキストデータ (UTF-8 エンコードされる)
            content_type: Content-Type

        Returns:
            dict: put_bytes と同じ
        """
        return self.put_bytes(key, text.encode("utf-8"), content_type=content_type)

    def put_json(
        self,
        key: str,
        data: Any,
        ensure_ascii: bool = False,
        content_type: str = "application/json; charset=utf-8",
    ) -> dict[str, Any]:
        """JSON データを書き込む

        Args:
            key: オブジェクトキー
            data: JSON シリアライズ可能なオブジェクト
            ensure_ascii: json.dumps の ensure_ascii フラグ
            content_type: Content-Type

        Returns:
            dict: put_bytes と同じ
        """
        body = json.dumps(data, default=str, ensure_ascii=ensure_ascii).encode("utf-8")
        return self.put_bytes(key, body, content_type=content_type)

    def build_s3_uri(self, key: str) -> str:
        """書き込み済みオブジェクトを参照する S3 URI を構築する

        ログ出力や Step Functions 出力ペイロードの結果トレース用。

        Args:
            key: オブジェクトキー（`put_*` に渡したのと同じ論理キー）

        Returns:
            str: `s3://<bucket-or-alias>/<prefix><key>` 形式の URI
        """
        bucket_param, resolved_key = self._resolve_target(key)
        return f"s3://{bucket_param}/{resolved_key}"

    # -----------------------------------------------------------------
    # Multipart / Streaming API (Phase 8 Theme J)
    # -----------------------------------------------------------------

    def put_stream(
        self,
        key: str,
        data: "bytes | Iterator[bytes]",
        content_type: str = "application/octet-stream",
        part_size: int = 100 * 1024 * 1024,
        content_length_hint: int | None = None,
        progress_callback: "Any | None" = None,
    ) -> dict[str, Any]:
        """ストリーミングアップロード（任意サイズ対応）

        小さいデータは put_object、大きいデータは自動で multipart upload に
        プロモーションする。

        Args:
            key: オブジェクトキー
            data: バイト列または bytes の Iterator
            content_type: Content-Type
            part_size: multipart 時のパートサイズ（デフォルト 100 MB）
            content_length_hint: 総サイズが既知の場合のヒント
            progress_callback: 進捗コールバック fn(bytes_uploaded: int, total_hint: int | None)

        Returns:
            dict: put_bytes と同形式（destination, bucket_or_ap, key, etag, size）
        """

        # Normalize data to iterator
        if isinstance(data, bytes):
            if content_length_hint is None:
                content_length_hint = len(data)
            data_iterator: Iterator[bytes] = _chunk_bytes(data, part_size)
        else:
            data_iterator = data

        multipart_threshold = part_size * 2

        # Fast path: known-small data
        if content_length_hint is not None and content_length_hint < multipart_threshold:
            buffer = b"".join(data_iterator)
            result = self.put_bytes(key, buffer, content_type=content_type)
            if progress_callback:
                progress_callback(len(buffer), content_length_hint)
            return result

        # Probe-and-decide: buffer up to threshold
        buffered: list[bytes] = []
        accumulated = 0
        for chunk in data_iterator:
            buffered.append(chunk)
            accumulated += len(chunk)
            if accumulated >= multipart_threshold:
                break
        else:
            # Iterator exhausted below threshold: single PUT
            buffer = b"".join(buffered)
            result = self.put_bytes(key, buffer, content_type=content_type)
            if progress_callback:
                progress_callback(len(buffer), content_length_hint)
            return result

        # Large data — use multipart
        def merged_iterator() -> Iterator[bytes]:
            for chunk in buffered:
                yield chunk
            for chunk in data_iterator:
                yield chunk

        bucket_param, resolved_key = self._resolve_target(key)

        if self._destination == FSXN_S3AP:
            return self._put_multipart_fsxn_s3ap(
                resolved_key, merged_iterator(), content_type, part_size,
                progress_callback, content_length_hint,
            )
        return self._put_multipart_standard_s3(
            bucket_param, resolved_key, merged_iterator(), content_type, part_size,
            progress_callback, content_length_hint,
        )

    def put_file(
        self,
        key: str,
        path: "str | Any",
        content_type: str | None = None,
        part_size: int = 100 * 1024 * 1024,
        progress_callback: "Any | None" = None,
    ) -> dict[str, Any]:
        """ローカルファイルパスからアップロード

        ファイルサイズに基づいて自動で通常 / multipart を選択する。

        Args:
            key: オブジェクトキー
            path: ローカルファイルパス
            content_type: Content-Type（None の場合は拡張子から推定）
            part_size: multipart 時のパートサイズ
            progress_callback: 進捗コールバック

        Returns:
            dict: put_bytes と同形式
        """
        import mimetypes
        from pathlib import Path as PathLib

        file_path = PathLib(path) if not isinstance(path, PathLib) else path
        file_size = file_path.stat().st_size

        if content_type is None:
            guessed, _ = mimetypes.guess_type(str(file_path))
            content_type = guessed or "application/octet-stream"

        def file_iterator():
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(part_size)
                    if not chunk:
                        break
                    yield chunk

        return self.put_stream(
            key=key,
            data=file_iterator(),
            content_type=content_type,
            part_size=part_size,
            content_length_hint=file_size,
            progress_callback=progress_callback,
        )

    def get_stream(
        self,
        key: str,
        chunk_size: int = 8 * 1024 * 1024,
    ):
        """ストリーミングダウンロード（メモリ効率のために Iterator を返す）

        Args:
            key: オブジェクトキー
            chunk_size: 1 回の read サイズ（デフォルト 8 MB）

        Yields:
            bytes: チャンク
        """
        bucket_param, resolved_key = self._resolve_target(key)
        try:
            response = self._s3_client.get_object(
                Bucket=bucket_param, Key=resolved_key
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if self._destination == FSXN_S3AP:
                raise S3ApHelperError(
                    f"Failed to get object '{resolved_key}' from "
                    f"FSxN S3 Access Point '{self._s3ap_alias}': {e}.",
                    error_code=error_code,
                ) from e
            raise

        body = response["Body"]
        while True:
            chunk = body.read(chunk_size)
            if not chunk:
                break
            yield chunk

    def _put_multipart_standard_s3(
        self,
        bucket: str,
        key: str,
        data_iterator,
        content_type: str,
        part_size: int,
        progress_callback=None,
        content_length_hint: int | None = None,
    ) -> dict[str, Any]:
        """Standard S3 multipart upload implementation."""
        try:
            create_resp = self._s3_client.create_multipart_upload(
                Bucket=bucket, Key=key, ContentType=content_type
            )
        except ClientError:
            raise

        upload_id = create_resp["UploadId"]
        parts: list[dict] = []
        part_number = 1
        total_uploaded = 0
        buffer = b""

        try:
            for chunk in data_iterator:
                buffer += chunk
                while len(buffer) >= part_size:
                    part_data = buffer[:part_size]
                    buffer = buffer[part_size:]

                    upload_resp = self._s3_client.upload_part(
                        Bucket=bucket,
                        Key=key,
                        UploadId=upload_id,
                        PartNumber=part_number,
                        Body=part_data,
                    )
                    parts.append({
                        "PartNumber": part_number,
                        "ETag": upload_resp["ETag"],
                    })
                    total_uploaded += len(part_data)
                    part_number += 1

                    if progress_callback:
                        progress_callback(total_uploaded, content_length_hint)

            # Upload remaining buffer
            if buffer:
                upload_resp = self._s3_client.upload_part(
                    Bucket=bucket,
                    Key=key,
                    UploadId=upload_id,
                    PartNumber=part_number,
                    Body=buffer,
                )
                parts.append({
                    "PartNumber": part_number,
                    "ETag": upload_resp["ETag"],
                })
                total_uploaded += len(buffer)

                if progress_callback:
                    progress_callback(total_uploaded, content_length_hint)

            # Complete
            complete_resp = self._s3_client.complete_multipart_upload(
                Bucket=bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )

            logger.info(
                "Multipart upload complete: destination=%s, bucket=%s, key=%s, "
                "size=%d, parts=%d, etag=%s",
                self._destination, bucket, key, total_uploaded,
                len(parts), complete_resp.get("ETag", ""),
            )

            return {
                "destination": self._destination,
                "bucket_or_ap": bucket,
                "key": key,
                "etag": complete_resp.get("ETag", ""),
                "size": total_uploaded,
            }

        except Exception as e:
            logger.error(
                "Multipart upload failed for key '%s', aborting upload_id '%s': %s",
                key, upload_id, str(e),
            )
            try:
                self._s3_client.abort_multipart_upload(
                    Bucket=bucket, Key=key, UploadId=upload_id
                )
            except ClientError as abort_err:
                logger.warning(
                    "Failed to abort multipart upload '%s': %s", upload_id, str(abort_err)
                )
            raise

    def _put_multipart_fsxn_s3ap(
        self,
        resolved_key: str,
        data_iterator,
        content_type: str,
        part_size: int,
        progress_callback=None,
        content_length_hint: int | None = None,
    ) -> dict[str, Any]:
        """FSxN S3AP multipart upload — delegates to S3ApHelper."""
        from shared.s3ap_helper import S3ApHelper

        helper = S3ApHelper(self._s3ap_alias, session=self._session)

        # Wrap iterator with progress tracking if callback provided
        if progress_callback:
            original_iterator = data_iterator
            total_uploaded = 0

            def tracked_iterator():
                nonlocal total_uploaded
                for chunk in original_iterator:
                    total_uploaded += len(chunk)
                    progress_callback(total_uploaded, content_length_hint)
                    yield chunk

            data_iterator = tracked_iterator()

        complete_resp = helper.multipart_upload(
            key=resolved_key,
            data_iterator=data_iterator,
            content_type=content_type,
            part_size=part_size,
        )

        return {
            "destination": self._destination,
            "bucket_or_ap": self._s3ap_alias,
            "key": resolved_key,
            "etag": complete_resp.get("ETag", ""),
            "size": total_uploaded if progress_callback else 0,
        }

    # -----------------------------------------------------------------
    # Read helpers (symmetric to put_*): same destination as put_*
    #
    # UC16 のように Lambda が前段の成果物を読み戻すパイプラインでは、
    # 書き出し先と読み出し先が一致していないとチェーンが成立しない。
    # get_bytes/text/json は put_* と同じ destination / prefix 解決を行うため、
    # ハンドラは OutputWriter 1 つで全 I/O をまかなえる。
    # -----------------------------------------------------------------
    def get_bytes(self, key: str) -> bytes:
        """書き込み先と同じロケーションからバイナリを取得する。

        Args:
            key: put_bytes / put_json / put_text で書き込んだ論理キー

        Returns:
            bytes: オブジェクトの Body

        Raises:
            S3ApHelperError: FSxN S3AP からの読み取り失敗時
            ClientError: 標準 S3 からの読み取り失敗時
        """
        bucket_param, resolved_key = self._resolve_target(key)
        try:
            response = self._s3_client.get_object(
                Bucket=bucket_param, Key=resolved_key
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if self._destination == FSXN_S3AP:
                raise S3ApHelperError(
                    f"Failed to get object '{resolved_key}' from "
                    f"FSxN S3 Access Point '{self._s3ap_alias}': {e}.",
                    error_code=error_code,
                ) from e
            raise
        return response["Body"].read()

    def get_text(self, key: str, encoding: str = "utf-8") -> str:
        """書き込み先と同じロケーションからテキストを取得する。"""
        return self.get_bytes(key).decode(encoding)

    def get_json(self, key: str) -> Any:
        """書き込み先と同じロケーションから JSON をパースして取得する。"""
        return json.loads(self.get_bytes(key).decode("utf-8"))
