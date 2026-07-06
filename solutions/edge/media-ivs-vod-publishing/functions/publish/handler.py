"""Media IVS VOD Publishing — Publish Lambda ハンドラ

Amazon IVS のライブ録画（HLS パッケージ）を、FSx for NetApp ONTAP の S3 Access Point へ
取り込み、master manifest を検証したうえで VOD publish マニフェストを書き戻す。

トリガー:
    - EVENT_DRIVEN（推奨）: EventBridge の "IVS Recording State Change"（Recording End）イベント。
      detail.recording_status / recording_s3_bucket_name / recording_s3_key_prefix を利用する。
    - POLLING: 明示的な recording_prefix / source_bucket、または env SOURCE_PREFIX_ROOT 配下を走査。

重要（permission-aware）:
    取り込みは指定された録画プレフィックス配下に限定する。公開配信は NFS/SMB の ACL を
    経由しないため、公開の可否は Human Review と運用（承認済みのみ公開）で担保する。

Human Review:
    publish-readiness の confidence（パッケージ完全性のヒューリスティック）を算出し、
    shared.human_review.evaluate_confidence で AUTO_APPROVE / HUMAN_REVIEW / REJECT を判定する。
    confidence は AI モデルスコアではない。最終的な公開可否は人間が決定する。

Environment Variables:
    S3_SOURCE: IVS 録画元の S3 バケット名 or S3 AP Alias（S3ApHelper は両形式を受け付ける）
    S3_ACCESS_POINT_OUTPUT: FSx for ONTAP 書き込み用 S3 AP Alias or ARN
    MASTER_MANIFEST_NAME: master manifest ファイル名（デフォルト "master.m3u8"）
    SOURCE_PREFIX_ROOT: POLLING 時の走査プレフィックス（デフォルト "ivs/v1/"）
    REQUIRE_RECORDING_END: "true" の場合、recording_status が "Recording End" 以外はスキップ
    DEMO_MODE: "true" の場合、実コピーをスキップし記録のみ（FSx 無しで検証）
    DATA_CLASSIFICATION: 出力データ分類（デフォルト PUBLIC）
    HUMAN_REVIEW_AUTO_APPROVE_THRESHOLD / HUMAN_REVIEW_REJECT_THRESHOLD: Human Review 閾値
    ENABLE_MODERATION: "true" で Amazon Rekognition による録画サムネイルのコンテンツモデレーションを実施
    MODERATION_MIN_CONFIDENCE: モデレーションラベル採用の最小 confidence（既定 80）
    MODERATION_MAX_IMAGES: モデレーション対象サムネイル数の上限（コスト制御、既定 5）
    MODERATION_THUMBNAIL_SUFFIX: サムネイル判定に使う拡張子（既定 ".jpg"）

Content moderation（Governance, opt-in）:
    ENABLE_MODERATION=true かつ非 DemoMode のとき、録画パッケージ内のサムネイル画像に対して
    Rekognition DetectModerationLabels を実行する。しきい値以上のモデレーションラベルが出た場合は
    publish をブロックし（blocked_by_moderation）、人手確認へ回す。既定は無効（オプトイン）で、
    推奨パス・DemoMode の動作は変わらない。完全性スコアとは独立した「公開可否」ゲートである。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import boto3

from shared.data_classification import get_classification
from shared.exceptions import lambda_error_handler
from shared.human_review import evaluate_confidence
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.s3ap_helper import S3ApHelper
from shared.schemas.events import MediaVodPublishOutput

logger = logging.getLogger(__name__)

DEFAULT_MASTER_MANIFEST = "master.m3u8"
DEFAULT_SOURCE_PREFIX_ROOT = "ivs/v1/"
RECORDING_END_STATUS = "Recording End"
PLAYLIST_SUFFIXES = (".m3u8",)
SEGMENT_SUFFIXES = (".ts", ".m4s", ".mp4")


def _multipart_threshold_bytes() -> int:
    """streaming multipart に切り替えるオブジェクトサイズしきい値（バイト）。

    既定 100 MB。これ以下は単純な PutObject、超過は低メモリの streaming multipart。
    """
    return int(float(os.environ.get("MULTIPART_THRESHOLD_MB", "100")) * 1024 * 1024)


def _max_lambda_ingest_bytes() -> int:
    """Lambda で取り込む最大オブジェクトサイズ（バイト）。0 で無制限。

    既定 20 GB。超過は Lambda の実行時間/エフェメラル制約に収まらない可能性が高いため
    skip し、DataSync / ECS・Batch（NFS/SMB マウント）を推奨する。
    """
    return int(float(os.environ.get("MAX_LAMBDA_INGEST_GB", "20")) * 1024 * 1024 * 1024)


def _moderation_enabled() -> bool:
    return os.environ.get("ENABLE_MODERATION", "false").lower() == "true"


def _moderate_thumbnails(source: S3ApHelper, keys: list[str]) -> dict:
    """録画サムネイルに対する Amazon Rekognition コンテンツモデレーション（opt-in / Governance）。

    サムネイル画像（既定 `.jpg`）を最大 `MODERATION_MAX_IMAGES` 件まで取得し、
    `DetectModerationLabels` を実行する。しきい値（`MODERATION_MIN_CONFIDENCE`）以上のラベルが
    1 つでも出れば flagged=True とする。画像バイトを直接渡すため、source が S3 バケット名でも
    S3 AP alias でも動作する（S3 AP は Rekognition の S3Object 直参照に非対応な場合があるため）。

    NOTE: これはサムネイルのサンプル検査であり、本文全編の網羅ではない。より厳密には
    Rekognition の非同期 `StartContentModeration`（動画）や音声/字幕の解析を別途組み込むこと。

    Args:
        source: 取り込み元 S3ApHelper
        keys: 録画パッケージ内オブジェクトキー一覧

    Returns:
        dict: {enabled, images_checked, flagged, labels, max_confidence, min_confidence}
    """
    thumb_suffix = os.environ.get("MODERATION_THUMBNAIL_SUFFIX", ".jpg").lower()
    max_images = int(os.environ.get("MODERATION_MAX_IMAGES", "5"))
    min_conf = float(os.environ.get("MODERATION_MIN_CONFIDENCE", "80"))

    thumbs = [k for k in keys if k.lower().endswith(thumb_suffix)][:max_images]
    if not thumbs:
        return {
            "enabled": True,
            "images_checked": 0,
            "flagged": False,
            "labels": [],
            "note": "no_thumbnails_found",
        }

    rekognition = boto3.client("rekognition")
    labels: list[dict] = []
    max_confidence = 0.0
    for key in thumbs:
        body = source.get_object(key)["Body"].read()
        resp = rekognition.detect_moderation_labels(Image={"Bytes": body}, MinConfidence=min_conf)
        for lbl in resp.get("ModerationLabels", []):
            conf = float(lbl.get("Confidence", 0.0))
            labels.append({"key": key, "name": lbl.get("Name"), "confidence": conf})
            max_confidence = max(max_confidence, conf)

    return {
        "enabled": True,
        "images_checked": len(thumbs),
        "flagged": bool(labels),
        "labels": labels,
        "max_confidence": max_confidence,
        "min_confidence": min_conf,
    }


def _is_demo_mode() -> bool:
    return os.environ.get("DEMO_MODE", "false").lower() == "true"


def _require_recording_end() -> bool:
    return os.environ.get("REQUIRE_RECORDING_END", "true").lower() == "true"


def _extract_recording_context(event: dict) -> dict:
    """イベントから録画コンテキスト（status / prefix / bucket / ids）を抽出する。

    EventBridge の IVS Recording State Change イベント（detail 配下）、明示的な
    top-level 指定、POLLING（プレフィックス走査）の 3 形態に対応する。

    Args:
        event: Lambda 入力イベント

    Returns:
        dict: recording_status, recording_prefix, source_bucket, recording_session_id,
              channel_name を含むコンテキスト
    """
    detail = event.get("detail") if isinstance(event, dict) else None
    if isinstance(detail, dict) and "recording_status" in detail:
        return {
            "recording_status": detail.get("recording_status", ""),
            "recording_prefix": detail.get("recording_s3_key_prefix", ""),
            "source_bucket": detail.get("recording_s3_bucket_name", ""),
            "recording_session_id": detail.get("recording_session_id", ""),
            "channel_name": detail.get("channel_name", ""),
        }
    # 明示指定（手動/Step Functions 経由）
    if isinstance(event, dict) and event.get("recording_prefix"):
        return {
            "recording_status": event.get("recording_status", RECORDING_END_STATUS),
            "recording_prefix": event.get("recording_prefix", ""),
            "source_bucket": event.get("source_bucket", ""),
            "recording_session_id": event.get("recording_session_id", ""),
            "channel_name": event.get("channel_name", ""),
        }
    # POLLING: プレフィックスルート配下を走査
    return {
        "recording_status": RECORDING_END_STATUS,
        "recording_prefix": os.environ.get("SOURCE_PREFIX_ROOT", DEFAULT_SOURCE_PREFIX_ROOT),
        "source_bucket": "",
        "recording_session_id": "",
        "channel_name": "",
    }


def _score_package(keys: list[str], master_manifest_name: str) -> tuple[float, bool, str]:
    """HLS パッケージの完全性から publish-readiness confidence を算出する。

    これは AI モデルスコアではなく、パッケージ完全性のヒューリスティックである。

    Args:
        keys: 取り込み対象オブジェクトキー一覧
        master_manifest_name: master manifest のファイル名

    Returns:
        tuple[float, bool, str]: (confidence, master_manifest_present, master_manifest_key)
    """
    master_keys = [k for k in keys if k.endswith(master_manifest_name)]
    has_master = bool(master_keys)
    has_playlist = any(k.endswith(PLAYLIST_SUFFIXES) for k in keys)
    has_segments = any(k.endswith(SEGMENT_SUFFIXES) for k in keys)

    if has_master and has_segments:
        confidence = 0.95
    elif has_playlist and has_segments:
        # プレイリストはあるが master manifest 名と一致しない
        confidence = 0.80
    elif has_playlist or has_segments:
        # 片方のみ → 不完全パッケージの可能性
        confidence = 0.55
    else:
        # manifest もセグメントも無い → 公開不可
        confidence = 0.15

    return confidence, has_master, (master_keys[0] if master_keys else "")


def _ingest_object(source: S3ApHelper, output: S3ApHelper, key: str, size: int) -> dict:
    """1 オブジェクトを FSx for ONTAP S3 AP へ取り込む。サイズで方式を自動選択する。

    - しきい値以下: `get_object` + `put_object`（小さい HLS セグメント/マニフェスト向け）。
    - しきい値超: `S3ApHelper.streaming_download` + `multipart_upload` による **streaming
      multipart**。本文を全量メモリに載せず part 単位でアップロードするため、単一 PutObject の
      5 GiB 上限を超える大容量も低メモリで書き込める。

    Args:
        source: 取り込み元 S3ApHelper
        output: FSx for ONTAP 出力 S3ApHelper
        key: オブジェクトキー
        size: オブジェクトサイズ（バイト）

    Returns:
        dict: 取り込み結果エントリ（method: "multipart" | "putobject"）
    """
    if size > _multipart_threshold_bytes():
        # 大容量: streaming + multipart（低メモリ）。ContentType は head_object から取得。
        content_type = source.head_object(key).get("ContentType", "application/octet-stream")
        output.multipart_upload(
            key=key,
            data_iterator=source.streaming_download(key),
            content_type=content_type,
        )
        return {"key": key, "bytes": size, "method": "multipart"}
    # 小容量: get_object + put_object
    src_obj = source.get_object(key)
    body = src_obj["Body"].read()
    content_type = src_obj.get("ContentType", "application/octet-stream")
    output.put_object(key=key, body=body, content_type=content_type)
    return {"key": key, "bytes": len(body), "method": "putobject"}


def _copy_package(source: S3ApHelper, output: S3ApHelper, objects: list[dict]) -> tuple[list[dict], list[dict]]:
    """取り込み: source から output（FSx for ONTAP S3 AP）へ HLS パッケージを複製する。

    Storage/Reliability lens: サイズで方式を自動選択する。しきい値
    （`MULTIPART_THRESHOLD_MB`、既定 100 MB）超は streaming multipart（低メモリ）で書き込み、
    単一 PutObject の 5 GiB 上限を超える大容量も扱える。ただし Lambda の実行時間/エフェメラル
    制約に配慮し、`MAX_LAMBDA_INGEST_GB`（既定 20 GB）超は skip して DataSync / ECS・Batch
    （NFS/SMB マウント）を推奨する（0 で無制限）。

    Args:
        source: 取り込み元 S3ApHelper
        output: FSx for ONTAP 出力 S3ApHelper
        objects: 複製対象オブジェクト（Key / Size を含む）

    Returns:
        tuple[list[dict], list[dict]]: (published, skipped)
    """
    published: list[dict] = []
    skipped: list[dict] = []
    max_ingest = _max_lambda_ingest_bytes()
    for obj in objects:
        key = obj["Key"]
        size = int(obj.get("Size", 0) or 0)
        if max_ingest and size > max_ingest:
            logger.warning(
                "Object %s (%d bytes) exceeds Lambda ingest ceiling; skipping (use DataSync/ECS).",
                key,
                size,
            )
            skipped.append({"key": key, "bytes": size, "reason": "exceeds_lambda_ingest_limit_use_datasync_or_ecs"})
            continue
        published.append(_ingest_object(source, output, key, size))
    return published, skipped


@trace_lambda_handler
@lambda_error_handler
def handler(event, context) -> MediaVodPublishOutput:
    """Media IVS VOD Publishing Publish Lambda。

    IVS の Recording End を起点に、HLS パッケージを FSx for ONTAP（S3 AP）へ取り込み、
    master manifest を検証し、Human Review 判定付きの VOD publish マニフェストを書き戻す。

    Returns:
        dict: manifest_key, status, master_manifest_present, human_review, total_objects,
              published, skipped, data_classification
    """
    ctx = _extract_recording_context(event)

    # Recording End 以外はスキップ（EVENT_DRIVEN の途中状態を無視）
    if _require_recording_end() and ctx["recording_status"] != RECORDING_END_STATUS:
        logger.info("Skipping non-Recording-End event: status=%r", ctx["recording_status"])
        return {
            "status": "skipped",
            "reason": f"recording_status is {ctx['recording_status']!r}, not {RECORDING_END_STATUS!r}",
            "recording_status": ctx["recording_status"],
        }

    source_alias = os.environ["S3_SOURCE"]
    output_alias = os.environ["S3_ACCESS_POINT_OUTPUT"]
    master_manifest_name = os.environ.get("MASTER_MANIFEST_NAME", DEFAULT_MASTER_MANIFEST)
    recording_prefix = (ctx["recording_prefix"] or "").rstrip("/")

    source = S3ApHelper(source_alias)
    output = S3ApHelper(output_alias)

    logger.info(
        "Publish started: source=%s, prefix=%r, demo=%s",
        source_alias,
        recording_prefix,
        _is_demo_mode(),
    )

    objects = source.list_objects(prefix=recording_prefix)
    keys = [o["Key"] for o in objects]

    confidence, master_present, master_key = _score_package(keys, master_manifest_name)
    decision = evaluate_confidence(confidence)

    # Governance (opt-in): サムネイルのコンテンツモデレーション。DemoMode では実行しない。
    moderation: dict = {"enabled": False}
    if _moderation_enabled():
        if _is_demo_mode():
            moderation = {"enabled": True, "skipped": "demo_mode"}
        else:
            moderation = _moderate_thumbnails(source, keys)
    blocked_by_moderation = bool(moderation.get("flagged"))

    published: list[dict] = []
    skipped: list[dict] = []

    if decision.action == "REJECT":
        # 完全性が閾値未満 → 公開しない（要エスカレーション）
        skipped = [{"key": k, "reason": "package_rejected_low_confidence"} for k in keys]
    elif blocked_by_moderation:
        # モデレーションでフラグ → 公開せず人手確認へ（完全性とは独立した公開可否ゲート）
        skipped = [{"key": k, "reason": "blocked_by_moderation"} for k in keys]
    elif _is_demo_mode():
        # DemoMode: 実コピーをスキップし記録のみ（検証は listing とマニフェスト検証で成立）
        skipped = [{"key": k, "reason": "demo_mode"} for k in keys]
    else:
        published, skipped = _copy_package(source, output, objects)

    classification = get_classification()
    now = datetime.now(timezone.utc)
    manifest = {
        "execution_id": context.aws_request_id,
        "timestamp": now.isoformat(),
        "recording_session_id": ctx["recording_session_id"],
        "channel_name": ctx["channel_name"],
        "source_bucket": ctx["source_bucket"] or source_alias,
        "recording_prefix": recording_prefix,
        "total_objects": len(keys),
        "master_manifest_present": master_present,
        "master_manifest_key": master_key,
        "published": published,
        "skipped": skipped,
        "human_review": decision.to_dict(),
        "moderation": moderation,
        "data_classification": classification.value,
        "data_classification_label": classification.label,
    }

    manifest_key = f"vod-publish-manifests/{now.strftime('%Y/%m/%d')}/{context.aws_request_id}.json"
    output.put_object(
        key=manifest_key,
        body=json.dumps(manifest, default=str),
        content_type="application/json",
    )

    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="publish")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "media-ivs-vod-publishing"))
    metrics.put_metric("ObjectsPublished", float(len(published)), "Count")
    metrics.put_metric("MasterManifestPresent", 1.0 if master_present else 0.0, "Count")
    metrics.put_metric("PublishReadinessConfidence", float(confidence), "None")
    metrics.flush()

    logger.info(
        "Publish completed: published=%d, skipped=%d, master_present=%s, action=%s, manifest=%s",
        len(published),
        len(skipped),
        master_present,
        decision.action,
        manifest_key,
    )

    return {
        "status": "completed",
        "manifest_key": manifest_key,
        "master_manifest_present": master_present,
        "master_manifest_key": master_key,
        "human_review": decision.to_dict(),
        "moderation": moderation,
        "blocked_by_moderation": blocked_by_moderation,
        "total_objects": len(published),
        "published": published,
        "skipped_count": len(skipped),
        "data_classification": classification.value,
    }
