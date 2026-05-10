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
from typing import Any

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
            S3ApHelperError: FSxN S3AP への書き込み失敗時
            ClientError: 標準 S3 への書き込み失敗時
        """
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
