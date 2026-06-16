"""Content Edge Delivery — Publish Lambda ハンドラ

FSx for ONTAP S3 Access Points 上の「配信承認済みレンディション」を、
CDN/エッジ配信ネットワークから配信可能にするための publish 処理。

本ハンドラは配信ベンダーに依存しない。統合メカニズム（docs/cdn-comparison.md 参照）を
DeliveryMode パラメータで切り替える:

- ORIGIN_PULL: オブジェクトをコピーせず、CDN が S3 AP を直接 SigV4 で取得する前提の
  配信マニフェスト（オリジン参照）を生成する。
- PUBLISH_PUSH: 承認済みレンディションを CDN 側 S3 互換オブジェクトストアへ複製する。
  オリジン認証問題を回避でき、CDN 非依存。DemoMode では外部 push をスキップして記録のみ行う。

重要（permission-aware）:
    公開 CDN 配信は NFS/SMB の ACL を経由しない。よって配信対象は
    APPROVED_PREFIX 配下の「公開可能と判定済み」のオブジェクトに限定する。
    ACL 制御下のマスターデータを配信レイヤへ直接流さないこと。

Environment Variables:
    S3_ACCESS_POINT: 入力（読み取り）用 S3 AP Alias or ARN
    S3_ACCESS_POINT_OUTPUT: 出力（マニフェスト書き込み）用 S3 AP Alias or ARN
    DELIVERY_MODE: "ORIGIN_PULL" | "PUBLISH_PUSH"（デフォルト: PUBLISH_PUSH）
    CDN_TARGET: "CLOUDFRONT" | "AKAMAI" | "FASTLY" | "CLOUDFLARE" | "OTHER"（記録用ラベル）
    APPROVED_PREFIX: 配信承認済みオブジェクトのプレフィックス（デフォルト: "delivery-approved/"）
    SUFFIX_FILTER: 配信対象拡張子のカンマ区切り（任意）
    DEMO_MODE: "true" の場合、外部ストアへの実 push をスキップ
    EXTERNAL_STORE_ENDPOINT: PUBLISH_PUSH 時の S3 互換エンドポイント URL（任意）
    EXTERNAL_STORE_BUCKET: PUBLISH_PUSH 時の配信先バケット名（任意）
    EXTERNAL_STORE_SECRET_NAME: 外部ストア認証情報の Secrets Manager 名（任意）
    DATA_CLASSIFICATION: 出力データ分類（デフォルト: PUBLIC）
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import boto3

from shared.data_classification import get_classification
from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.s3ap_helper import S3ApHelper
from shared.schemas.events import ApprovalProvenance, DeliveryPublishOutput

logger = logging.getLogger(__name__)

DEFAULT_APPROVED_PREFIX = "delivery-approved/"
DELIVERY_MODE_ORIGIN_PULL = "ORIGIN_PULL"
DELIVERY_MODE_PUBLISH_PUSH = "PUBLISH_PUSH"


def _is_demo_mode() -> bool:
    return os.environ.get("DEMO_MODE", "false").lower() == "true"


def _filter_targets(objects: list[dict], suffix: str) -> list[dict]:
    """配信対象オブジェクトをサフィックスでフィルタする。

    Args:
        objects: S3ApHelper.list_objects() の結果
        suffix: カンマ区切りの拡張子（空文字なら全件）

    Returns:
        list[dict]: 配信対象オブジェクト
    """
    if not suffix:
        return objects
    suffixes = tuple(s.strip().lower() for s in suffix.split(",") if s.strip())
    if not suffixes:
        return objects
    return [obj for obj in objects if obj["Key"].lower().endswith(suffixes)]


def _build_origin_reference(key: str, access_point: str, cdn_target: str) -> dict:
    """ORIGIN_PULL 用のオリジン参照エントリを生成する。

    実際のオブジェクトコピーは行わず、CDN がオリジンとして参照するための
    メタデータのみを返す。SigV4 オリジン署名の実機検証は別途必要（要検証）。
    """
    return {
        "key": key,
        "origin_access_point": access_point,
        "cdn_target": cdn_target,
        "delivery_mode": DELIVERY_MODE_ORIGIN_PULL,
        "note": "CDN pulls this object from the S3 AP origin via SigV4. Viewer token auth uses CDN-native mechanism (S3 presigned URL is unsupported).",
    }


def _external_store_session() -> boto3.Session | None:
    """外部 S3 互換ストア用の boto3 セッションを構築する（Security）。

    EXTERNAL_STORE_SECRET_NAME が設定されている場合、Secrets Manager から
    外部ストア（Akamai Object Storage / Cloudflare R2 / Fastly Object Storage 等）の
    認証情報を取得して専用セッションを返す。未設定の場合は None（既定セッション）を返す。

    Secret の想定形式（JSON）:
        {"access_key_id": "...", "secret_access_key": "...", "session_token": "(optional)"}

    Note:
        AWS の既定認証情報は外部ベンダーのストアには通用しないため、PUBLISH_PUSH で
        外部ストアへ複製する場合は本 Secret 経由の認証情報が必要。
    """
    secret_name = os.environ.get("EXTERNAL_STORE_SECRET_NAME", "")
    if not secret_name:
        return None
    sm = boto3.client("secretsmanager")
    resp = sm.get_secret_value(SecretId=secret_name)
    creds = json.loads(resp["SecretString"])
    return boto3.Session(
        aws_access_key_id=creds["access_key_id"],
        aws_secret_access_key=creds["secret_access_key"],
        aws_session_token=creds.get("session_token"),
    )


def _push_to_external_store(
    *,
    s3ap: S3ApHelper,
    key: str,
    bucket: str,
    endpoint_url: str,
    session: boto3.Session | None = None,
) -> dict:
    """PUBLISH_PUSH: 承認済みレンディションを S3 互換ストアへ複製する。

    Args:
        s3ap: 入力 S3 AP ヘルパー
        key: 複製対象オブジェクトキー
        bucket: 配信先 S3 互換バケット
        endpoint_url: S3 互換エンドポイント URL
        session: boto3 セッション（認証情報注入用、任意）

    Returns:
        dict: push 結果エントリ
    """
    obj = s3ap.get_object(key)
    body = obj["Body"].read()
    content_type = obj.get("ContentType", "application/octet-stream")

    sess = session or boto3.Session()
    client = sess.client("s3", endpoint_url=endpoint_url)
    client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)

    return {
        "key": key,
        "delivery_mode": DELIVERY_MODE_PUBLISH_PUSH,
        "target_bucket": bucket,
        "target_endpoint": endpoint_url,
        "bytes": len(body),
    }


def _approval_provenance(s3ap: S3ApHelper, key: str, execution_id: str) -> ApprovalProvenance:
    """配信承認の監査証跡を生成する（Governance）。

    承認情報はオブジェクトのユーザーメタデータ（x-amz-meta-approved-by /
    x-amz-meta-approval-id）から取得する。承認元が記録されていない場合は
    "unrecorded" とし、deny ではなく可視化する（運用で検知できるようにする）。
    """
    approver = "unrecorded"
    approval_id = ""
    try:
        head = s3ap.head_object(key)
        meta = head.get("Metadata", {}) or {}
        approver = meta.get("approved-by", approver)
        approval_id = meta.get("approval-id", "")
    except Exception:  # noqa: BLE001 — 証跡取得失敗で配信を止めない（警告のみ）
        logger.warning("Approval provenance lookup failed for key=%s; recording as unrecorded.", key)
    return {
        "source_key": key,
        "approver": approver,
        "approval_id": approval_id,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "execution_id": execution_id,
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context) -> DeliveryPublishOutput:
    """Content Edge Delivery Publish Lambda。

    承認済みレンディションを配信レイヤへ反映し、配信マニフェストを S3 AP に書き戻す。

    Returns:
        dict: manifest_key, delivery_mode, cdn_target, published, total_objects
    """
    s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
    s3ap_output = S3ApHelper(os.environ.get("S3_ACCESS_POINT_OUTPUT", os.environ["S3_ACCESS_POINT"]))

    delivery_mode = os.environ.get("DELIVERY_MODE", DELIVERY_MODE_PUBLISH_PUSH)
    cdn_target = os.environ.get("CDN_TARGET", "CLOUDFRONT")
    approved_prefix = os.environ.get("APPROVED_PREFIX", DEFAULT_APPROVED_PREFIX)
    suffix = os.environ.get("SUFFIX_FILTER", "")

    logger.info(
        "Publish started: mode=%s, cdn=%s, approved_prefix=%r, demo=%s",
        delivery_mode,
        cdn_target,
        approved_prefix,
        _is_demo_mode(),
    )

    # permission-aware: 承認済みプレフィックス配下のみを配信対象にする
    candidates = s3ap.list_objects(prefix=approved_prefix)
    targets = _filter_targets(candidates, suffix)

    published: list[dict] = []
    skipped: list[dict] = []
    provenance: list[ApprovalProvenance] = []

    # Security: 外部ストア認証セッションを一度だけ構築（PUBLISH_PUSH 実 push 時のみ使用）
    external_session: boto3.Session | None = None
    bucket = os.environ.get("EXTERNAL_STORE_BUCKET", "")
    endpoint = os.environ.get("EXTERNAL_STORE_ENDPOINT", "")
    will_push = delivery_mode == DELIVERY_MODE_PUBLISH_PUSH and not _is_demo_mode() and bool(bucket) and bool(endpoint)
    if will_push:
        external_session = _external_store_session()

    for obj in targets:
        key = obj["Key"]
        # Governance: 公開配信対象ごとに承認証跡を記録
        provenance.append(_approval_provenance(s3ap, key, context.aws_request_id))

        if delivery_mode == DELIVERY_MODE_ORIGIN_PULL:
            published.append(_build_origin_reference(key, os.environ["S3_ACCESS_POINT"], cdn_target))
            continue

        # PUBLISH_PUSH
        if not will_push:
            # DemoMode / 未設定時は実 push をスキップし、記録のみ
            skipped.append(
                {
                    "key": key,
                    "delivery_mode": DELIVERY_MODE_PUBLISH_PUSH,
                    "reason": "demo_mode_or_external_store_not_configured",
                }
            )
            continue
        published.append(
            _push_to_external_store(
                s3ap=s3ap,
                key=key,
                bucket=bucket,
                endpoint_url=endpoint,
                session=external_session,
            )
        )

    classification = get_classification()
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "delivery_mode": delivery_mode,
        "cdn_target": cdn_target,
        "total_candidates": len(candidates),
        "total_targets": len(targets),
        "published": published,
        "skipped": skipped,
        "provenance": provenance,
        "data_classification": classification.value,
        "data_classification_label": classification.label,
    }

    manifest_key = (
        f"delivery-manifests/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{context.aws_request_id}.json"
    )
    s3ap_output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="publish")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "content-edge-delivery"))
    metrics.put_metric("ObjectsPublished", float(len(published)), "Count")
    metrics.flush()

    logger.info(
        "Publish completed: published=%d, skipped=%d, manifest=%s",
        len(published),
        len(skipped),
        manifest_key,
    )

    return {
        "manifest_key": manifest_key,
        "delivery_mode": delivery_mode,
        "cdn_target": cdn_target,
        "published": published,
        "total_objects": len(published),
        "data_classification": classification.value,
    }
