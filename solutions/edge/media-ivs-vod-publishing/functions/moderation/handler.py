"""Media IVS VOD Publishing — Strict Moderation Lambda（opt-in, async）

サムネイルの同期検査（publish handler の `_moderate_thumbnails`）より厳密な、
動画・音声・字幕のモデレーションを行う **2 フェーズ（start / collect）** の非同期ワークフロー。
Step Functions（start → Wait → collect ループ → gate）から呼び出すことを想定する。

- 動画: Amazon Rekognition `StartContentModeration` / `GetContentModeration`（非同期）。
  入力は S3 上の単一動画ファイル（例: MediaConvert で HLS から生成した MP4）。HLS の
  セグメント群は直接対象にできないため、`video_key` は MP4 等を指すこと（MediaConvert 依存）。
- 音声: Amazon Transcribe `StartTranscriptionJob` → 完了後に文字起こしを取得し、
  Amazon Comprehend `DetectToxicContent` で有害表現を判定する。
- 字幕: 録画パッケージ内の字幕ファイル（既定 `.vtt` / `.srt`）を読み、Comprehend
  `DetectToxicContent` で同期判定する（start フェーズで実行）。

いずれかがしきい値以上でフラグされたら decision=BLOCK とし、publish をブロックして人手確認へ回す。
これは opt-in の追加コンポーネントであり、既定の推奨パス・DemoMode の動作には影響しない。

Environment Variables:
    S3_SOURCE: 動画/字幕が存在する標準 S3 バケット名（Rekognition/Transcribe 用）
    MODERATION_MIN_CONFIDENCE: Rekognition 動画ラベルの最小 confidence（既定 80）
    MODERATION_TOXICITY_THRESHOLD: Comprehend toxicity のしきい値（0-1、既定 0.5）
    MODERATION_LANGUAGE_CODE: Comprehend/Transcribe 言語（既定 "en"）
    CAPTION_SUFFIXES: 字幕拡張子のカンマ区切り（既定 ".vtt,.srt"）
    MODERATION_MAX_CAPTION_FILES: 字幕ファイル処理上限（既定 3）
    MODERATION_MAX_SEGMENTS: Comprehend TextSegments 上限（既定 10）
    TRANSCRIBE_OUTPUT_BUCKET: Transcribe 出力バケット（未設定なら S3_SOURCE）
    TRANSCRIBE_OUTPUT_PREFIX: Transcribe 出力プレフィックス（既定 "moderation/transcripts/"）
"""

from __future__ import annotations

import json
import logging
import os

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import trace_lambda_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

TOXIC_LABEL_NAMES = (
    "GRAPHIC",
    "HARASSMENT_OR_ABUSE",
    "HATE_SPEECH",
    "INSULT",
    "PROFANITY",
    "SEXUAL",
    "VIOLENCE_OR_THREAT",
)


def _min_confidence() -> float:
    return float(os.environ.get("MODERATION_MIN_CONFIDENCE", "80"))


def _toxicity_threshold() -> float:
    return float(os.environ.get("MODERATION_TOXICITY_THRESHOLD", "0.5"))


def _language_code() -> str:
    return os.environ.get("MODERATION_LANGUAGE_CODE", "en")


def _caption_suffixes() -> tuple[str, ...]:
    raw = os.environ.get("CAPTION_SUFFIXES", ".vtt,.srt")
    return tuple(s.strip().lower() for s in raw.split(",") if s.strip())


# ---------------------------------------------------------------------------
# Caption / text helpers
# ---------------------------------------------------------------------------


def _extract_caption_text(raw: str) -> str:
    """WebVTT / SRT からタイムコード・インデックス・ヘッダを除いた本文を抽出する。"""
    lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.upper().startswith("WEBVTT"):
            continue
        if "-->" in stripped:  # timestamp cue
            continue
        if stripped.isdigit():  # SRT sequence index
            continue
        lines.append(stripped)
    return " ".join(lines)


def _chunk_text(text: str, max_segments: int, seg_chars: int = 900) -> list[str]:
    """Comprehend DetectToxicContent 用に text を <=max_segments 個・各 <=1KB に分割する。"""
    segments = [text[i : i + seg_chars] for i in range(0, len(text), seg_chars)]
    return [s for s in segments if s][:max_segments]


def _moderate_text(comprehend, text: str) -> dict:
    """Comprehend DetectToxicContent でテキストの有害度を判定する。

    Returns:
        dict: {flagged, max_toxicity, labels}
    """
    max_segments = int(os.environ.get("MODERATION_MAX_SEGMENTS", "10"))
    threshold = _toxicity_threshold()
    segments = _chunk_text(text, max_segments)
    if not segments:
        return {"flagged": False, "max_toxicity": 0.0, "labels": []}

    resp = comprehend.detect_toxic_content(
        TextSegments=[{"Text": s} for s in segments],
        LanguageCode=_language_code(),
    )
    max_toxicity = 0.0
    labels: list[dict] = []
    for item in resp.get("ResultList", []):
        toxicity = float(item.get("Toxicity", 0.0))
        max_toxicity = max(max_toxicity, toxicity)
        for lbl in item.get("Labels", []):
            score = float(lbl.get("Score", 0.0))
            if score >= threshold:
                labels.append({"name": lbl.get("Name"), "score": score})
    return {"flagged": max_toxicity >= threshold or bool(labels), "max_toxicity": max_toxicity, "labels": labels}


def _moderate_captions(source: S3ApHelper, comprehend, keys: list[str]) -> dict:
    """録画パッケージ内の字幕ファイルを同期モデレーションする。"""
    suffixes = _caption_suffixes()
    max_files = int(os.environ.get("MODERATION_MAX_CAPTION_FILES", "3"))
    caption_keys = [k for k in keys if k.lower().endswith(suffixes)][:max_files]
    if not caption_keys:
        return {"checked": 0, "flagged": False, "labels": [], "note": "no_caption_files"}

    flagged = False
    labels: list[dict] = []
    max_toxicity = 0.0
    for key in caption_keys:
        raw = source.get_object(key)["Body"].read()
        text = _extract_caption_text(raw.decode("utf-8", errors="replace"))
        result = _moderate_text(comprehend, text)
        flagged = flagged or result["flagged"]
        max_toxicity = max(max_toxicity, result["max_toxicity"])
        for lbl in result["labels"]:
            labels.append({"key": key, **lbl})
    return {"checked": len(caption_keys), "flagged": flagged, "max_toxicity": max_toxicity, "labels": labels}


# ---------------------------------------------------------------------------
# Phase: start
# ---------------------------------------------------------------------------


def _start(event: dict, context) -> dict:
    """start フェーズ: 動画/音声の非同期ジョブを開始し、字幕は同期判定する。"""
    source_bucket = os.environ["S3_SOURCE"]
    recording_prefix = (event.get("recording_prefix") or "").rstrip("/")
    video_key = event.get("video_key")  # 例: MediaConvert が生成した MP4 のキー

    source = S3ApHelper(source_bucket)
    keys = [o["Key"] for o in source.list_objects(prefix=recording_prefix)] if recording_prefix else []

    # 字幕（同期）
    comprehend = boto3.client("comprehend")
    captions = _moderate_captions(source, comprehend, keys)

    rekognition_job_id = ""
    transcribe_job_name = ""
    transcribe_output_key = ""

    if video_key:
        # 動画（Rekognition 非同期）
        rek = boto3.client("rekognition")
        rek_resp = rek.start_content_moderation(
            Video={"S3Object": {"Bucket": source_bucket, "Name": video_key}},
            MinConfidence=_min_confidence(),
        )
        rekognition_job_id = rek_resp.get("JobId", "")

        # 音声（Transcribe 非同期）
        transcribe = boto3.client("transcribe")
        output_bucket = os.environ.get("TRANSCRIBE_OUTPUT_BUCKET") or source_bucket
        output_prefix = os.environ.get("TRANSCRIBE_OUTPUT_PREFIX", "moderation/transcripts/")
        transcribe_job_name = f"ivs-mod-{context.aws_request_id}"
        transcribe_output_key = f"{output_prefix}{transcribe_job_name}.json"
        transcribe.start_transcription_job(
            TranscriptionJobName=transcribe_job_name,
            Media={"MediaFileUri": f"s3://{source_bucket}/{video_key}"},
            LanguageCode=_language_code(),
            OutputBucketName=output_bucket,
            OutputKey=transcribe_output_key,
        )

    return {
        "moderation_phase": "start",
        "recording_prefix": recording_prefix,
        "video_key": video_key or "",
        "rekognition_job_id": rekognition_job_id,
        "transcribe_job_name": transcribe_job_name,
        "transcribe_output_key": transcribe_output_key,
        "captions": captions,
        "captions_flagged": captions["flagged"],
        "started": {"video": bool(rekognition_job_id), "audio": bool(transcribe_job_name)},
    }


# ---------------------------------------------------------------------------
# Phase: collect
# ---------------------------------------------------------------------------


def _collect_video(job_id: str) -> dict:
    """Rekognition 動画モデレーション結果を収集する。"""
    rek = boto3.client("rekognition")
    resp = rek.get_content_moderation(JobId=job_id)
    status = resp.get("JobStatus", "IN_PROGRESS")
    if status != "SUCCEEDED":
        return {"status": status, "flagged": False, "labels": [], "pending": status == "IN_PROGRESS"}
    min_conf = _min_confidence()
    labels: list[dict] = []
    for det in resp.get("ModerationLabels", []):
        ml = det.get("ModerationLabel", {})
        conf = float(ml.get("Confidence", 0.0))
        if conf >= min_conf:
            labels.append({"name": ml.get("Name"), "confidence": conf})
    return {"status": status, "flagged": bool(labels), "labels": labels, "pending": False}


def _collect_audio(job_name: str, output_key: str) -> dict:
    """Transcribe 完了を確認し、文字起こしを Comprehend で判定する。"""
    transcribe = boto3.client("transcribe")
    resp = transcribe.get_transcription_job(TranscriptionJobName=job_name)
    status = resp.get("TranscriptionJob", {}).get("TranscriptionJobStatus", "IN_PROGRESS")
    if status != "COMPLETED":
        return {"status": status, "flagged": False, "labels": [], "pending": status == "IN_PROGRESS"}

    output_bucket = os.environ.get("TRANSCRIBE_OUTPUT_BUCKET") or os.environ["S3_SOURCE"]
    s3 = boto3.client("s3")
    body = s3.get_object(Bucket=output_bucket, Key=output_key)["Body"].read()
    data = json.loads(body)
    transcript = ""
    transcripts = data.get("results", {}).get("transcripts", [])
    if transcripts:
        transcript = transcripts[0].get("transcript", "")

    comprehend = boto3.client("comprehend")
    result = _moderate_text(comprehend, transcript)
    return {
        "status": status,
        "flagged": result["flagged"],
        "max_toxicity": result["max_toxicity"],
        "labels": result["labels"],
        "pending": False,
    }


def _collect(event: dict, _context) -> dict:
    """collect フェーズ: 非同期ジョブ結果を集約し公開可否を判定する。"""
    rekognition_job_id = event.get("rekognition_job_id") or ""
    transcribe_job_name = event.get("transcribe_job_name") or ""
    transcribe_output_key = event.get("transcribe_output_key") or ""
    captions_flagged = bool(event.get("captions_flagged"))

    video = _collect_video(rekognition_job_id) if rekognition_job_id else {"status": "skipped", "flagged": False, "pending": False}
    audio = (
        _collect_audio(transcribe_job_name, transcribe_output_key)
        if transcribe_job_name
        else {"status": "skipped", "flagged": False, "pending": False}
    )

    pending = bool(video.get("pending")) or bool(audio.get("pending"))
    flagged = bool(video.get("flagged")) or bool(audio.get("flagged")) or captions_flagged

    if pending:
        return {
            "moderation_phase": "collect",
            "status": "pending",
            "video": video,
            "audio": audio,
            "captions_flagged": captions_flagged,
        }

    return {
        "moderation_phase": "collect",
        "status": "completed",
        "flagged": flagged,
        "decision": "BLOCK" if flagged else "ALLOW",
        "video": video,
        "audio": audio,
        "captions_flagged": captions_flagged,
    }


@trace_lambda_handler
@lambda_error_handler
def handler(event, context) -> dict:
    """Strict Moderation Lambda。`moderation_phase` で start / collect を切り替える。

    Returns:
        dict: フェーズ別の結果。collect フェーズは status（pending|completed）と、
              completed 時に decision（ALLOW|BLOCK）/ flagged を返す。
    """
    phase = event.get("moderation_phase", "start")
    logger.info("Strict moderation phase=%s", phase)
    if phase == "start":
        return _start(event, context)
    if phase == "collect":
        return _collect(event, context)
    return {"status": "error", "reason": f"unknown moderation_phase {phase!r}"}
