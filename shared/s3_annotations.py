"""S3 Annotations ヘルパー

Amazon S3 Annotations API を使い、処理結果オブジェクトにリッチメタデータを付与する。
データ分類、リネージ、Human Review 結果、AI 分析メタデータを
JSON annotation として標準 S3 バケット上の出力オブジェクトに保存する。

注意:
    FSx for ONTAP S3 Access Points は PutObjectAnnotation / GetObjectAnnotation を
    現時点でサポートしていない可能性がある（未検証）。
    このモジュールは OutputDestination=STANDARD_S3 の出力先に対して使用する。
    FSxN S3 AP 経由の annotation サポート状況は docs/s3ap-compatibility-notes.md を参照。

Usage:
    from shared.s3_annotations import AnnotationHelper, ProcessingAnnotation

    helper = AnnotationHelper(bucket="output-bucket")

    annotation = ProcessingAnnotation(
        uc_id="legal-compliance",
        source_path="/vol1/legal/contracts/deal-001.pdf",
        data_classification="INTERNAL",
        confidence_score=0.92,
        human_review_action="AUTO_APPROVE",
        model_id="amazon.nova-pro-v1:0",
        processing_timestamp="2026-06-18T10:30:00Z",
    )

    helper.put_annotation(
        key="legal/reports/deal-001-analysis.json",
        annotation_name="processing_metadata",
        annotation=annotation,
    )
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


# S3 Annotations API がサポートされていない場合のフォールバック動作
FALLBACK_MODE_SKIP = "skip"  # annotation 付与をスキップ（ログ出力のみ）
FALLBACK_MODE_TAG = "tag"  # Object Tagging にフォールバック（10タグ/256文字制限あり）
FALLBACK_MODE_ERROR = "error"  # 例外を raise


@dataclass
class ProcessingAnnotation:
    """処理メタデータ annotation のデータモデル。

    全 UC 共通で出力オブジェクトに付与する処理情報を構造化する。
    """

    # 必須フィールド
    uc_id: str
    source_path: str
    data_classification: str
    processing_timestamp: str

    # AI/ML 関連（オプション）
    confidence_score: float | None = None
    human_review_action: str | None = None  # AUTO_APPROVE | HUMAN_REVIEW | REJECT
    model_id: str | None = None
    embedding_model_id: str | None = None

    # リネージ（オプション）
    step_functions_execution_arn: str | None = None
    input_checksum: str | None = None
    output_checksum: str | None = None
    duration_ms: int | None = None

    # バージョニング（オプション）
    chunking_strategy_version: str | None = None
    uc_template_version: str | None = None
    annotation_schema_version: str = "1.0"

    # カスタムメタデータ
    custom: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """annotation を JSON 文字列に変換する。

        None 値のフィールドは出力から除外する。
        """
        data = {k: v for k, v in asdict(self).items() if v is not None}
        return json.dumps(data, ensure_ascii=False, default=str)

    def to_dict(self) -> dict[str, Any]:
        """annotation を辞書に変換する（None 除外）。"""
        return {k: v for k, v in asdict(self).items() if v is not None}


class AnnotationHelper:
    """S3 Annotations API ヘルパー。

    出力オブジェクトにリッチメタデータを annotation として付与する。
    API 未サポート環境ではフォールバック動作を選択可能。
    """

    def __init__(
        self,
        bucket: str,
        fallback_mode: str = FALLBACK_MODE_SKIP,
        session: boto3.Session | None = None,
    ):
        """AnnotationHelper を初期化する。

        Args:
            bucket: 出力先 S3 バケット名
            fallback_mode: API 未サポート時の動作
                - "skip": ログ出力してスキップ（デフォルト）
                - "tag": Object Tagging にフォールバック
                - "error": 例外を raise
            session: boto3 セッション（オプション）
        """
        self._bucket = bucket
        self._fallback_mode = fallback_mode
        self._session = session or boto3.Session()
        self._s3_client = self._session.client("s3")
        self._annotations_supported: bool | None = None

    @property
    def bucket(self) -> str:
        """出力先バケット名"""
        return self._bucket

    def put_annotation(
        self,
        key: str,
        annotation_name: str,
        annotation: ProcessingAnnotation | dict[str, Any] | str,
    ) -> dict[str, Any]:
        """オブジェクトに annotation を付与する。

        Args:
            key: S3 オブジェクトキー
            annotation_name: annotation 名（オブジェクトごとに一意）
            annotation: annotation データ（ProcessingAnnotation, dict, or JSON str）

        Returns:
            API レスポンス dict（成功時）、またはフォールバック結果

        Raises:
            S3AnnotationError: fallback_mode="error" で API 未サポート時
        """
        # annotation データを文字列に変換
        if isinstance(annotation, ProcessingAnnotation):
            payload = annotation.to_json()
        elif isinstance(annotation, dict):
            payload = json.dumps(annotation, ensure_ascii=False, default=str)
        else:
            payload = str(annotation)

        try:
            response = self._s3_client.put_object_annotation(
                Bucket=self._bucket,
                Key=key,
                AnnotationName=annotation_name,
                AnnotationPayload=payload.encode("utf-8"),
            )
            self._annotations_supported = True
            logger.info(
                "Annotation attached: bucket=%s key=%s name=%s",
                self._bucket,
                key,
                annotation_name,
            )
            return response

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("InvalidAction", "NotImplemented", "UnsupportedOperation"):
                self._annotations_supported = False
                return self._handle_fallback(key, annotation_name, payload, e)
            raise S3AnnotationError(
                f"Failed to put annotation: {error_code} — {e}"
            ) from e

        except AttributeError:
            # boto3 が put_object_annotation をまだ実装していない場合
            self._annotations_supported = False
            return self._handle_fallback(
                key,
                annotation_name,
                payload,
                RuntimeError("put_object_annotation not available in boto3"),
            )

    def get_annotation(
        self,
        key: str,
        annotation_name: str,
    ) -> dict[str, Any] | None:
        """オブジェクトから annotation を取得する。

        Args:
            key: S3 オブジェクトキー
            annotation_name: 取得する annotation 名

        Returns:
            annotation データ dict、または None（未サポート/未存在時）
        """
        try:
            response = self._s3_client.get_object_annotation(
                Bucket=self._bucket,
                Key=key,
                AnnotationName=annotation_name,
            )
            body = response["AnnotationPayload"].read().decode("utf-8")
            return json.loads(body)

        except (ClientError, AttributeError) as e:
            logger.warning(
                "Cannot get annotation: bucket=%s key=%s name=%s error=%s",
                self._bucket,
                key,
                annotation_name,
                str(e),
            )
            return None

    def list_annotations(self, key: str) -> list[str]:
        """オブジェクトに付与されている annotation 名の一覧を取得する。

        Args:
            key: S3 オブジェクトキー

        Returns:
            annotation 名のリスト
        """
        try:
            response = self._s3_client.list_object_annotations(
                Bucket=self._bucket,
                Key=key,
            )
            return [a["AnnotationName"] for a in response.get("Annotations", [])]

        except (ClientError, AttributeError) as e:
            logger.warning(
                "Cannot list annotations: bucket=%s key=%s error=%s",
                self._bucket,
                key,
                str(e),
            )
            return []

    def delete_annotation(self, key: str, annotation_name: str) -> bool:
        """オブジェクトから annotation を削除する。

        Args:
            key: S3 オブジェクトキー
            annotation_name: 削除する annotation 名

        Returns:
            削除成功なら True
        """
        try:
            self._s3_client.delete_object_annotation(
                Bucket=self._bucket,
                Key=key,
                AnnotationName=annotation_name,
            )
            logger.info(
                "Annotation deleted: bucket=%s key=%s name=%s",
                self._bucket,
                key,
                annotation_name,
            )
            return True

        except (ClientError, AttributeError) as e:
            logger.warning(
                "Cannot delete annotation: bucket=%s key=%s name=%s error=%s",
                self._bucket,
                key,
                annotation_name,
                str(e),
            )
            return False

    def _handle_fallback(
        self,
        key: str,
        annotation_name: str,
        payload: str,
        original_error: Exception,
    ) -> dict[str, Any]:
        """API 未サポート時のフォールバック処理。"""

        if self._fallback_mode == FALLBACK_MODE_ERROR:
            raise S3AnnotationError(
                f"S3 Annotations API not supported: {original_error}"
            ) from original_error

        if self._fallback_mode == FALLBACK_MODE_TAG:
            return self._fallback_to_tags(key, annotation_name, payload)

        # FALLBACK_MODE_SKIP（デフォルト）
        logger.warning(
            "S3 Annotations API not available, skipping: bucket=%s key=%s name=%s error=%s",
            self._bucket,
            key,
            annotation_name,
            str(original_error),
        )
        return {"fallback": "skipped", "annotation_name": annotation_name}

    def _fallback_to_tags(
        self,
        key: str,
        annotation_name: str,
        payload: str,
    ) -> dict[str, Any]:
        """Object Tagging にフォールバック（制限付き）。

        S3 Object Tags は 10 個まで、key 128文字 / value 256文字の制限あり。
        annotation の要約のみ保存する。
        """
        try:
            # JSON payload から主要フィールドを抽出してタグ化
            data = json.loads(payload)
            tags = []

            tag_mappings = {
                "uc_id": "uc-id",
                "data_classification": "classification",
                "human_review_action": "review-action",
                "confidence_score": "confidence",
            }

            for field_name, tag_key in tag_mappings.items():
                if field_name in data and data[field_name] is not None:
                    value = str(data[field_name])[:256]
                    tags.append({"Key": tag_key, "Value": value})

            if tags:
                self._s3_client.put_object_tagging(
                    Bucket=self._bucket,
                    Key=key,
                    Tagging={"TagSet": tags[:10]},
                )
                logger.info(
                    "Annotation fallback to tags: bucket=%s key=%s tags=%d",
                    self._bucket,
                    key,
                    len(tags),
                )

            return {"fallback": "tags", "tag_count": len(tags)}

        except (ClientError, json.JSONDecodeError) as e:
            logger.warning("Tag fallback failed: %s", str(e))
            return {"fallback": "failed", "error": str(e)}

    @property
    def is_supported(self) -> bool | None:
        """Annotations API がサポートされているかどうか。

        None: まだ試行していない
        True: サポートされている
        False: サポートされていない
        """
        return self._annotations_supported


class S3AnnotationError(Exception):
    """S3 Annotations 操作に失敗した場合の例外。"""

    pass
