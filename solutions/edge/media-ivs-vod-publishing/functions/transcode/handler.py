"""Media IVS VOD Publishing — HLS→MP4 Transcode Lambda（opt-in, async）

厳密モデレーション（動画）は S3 上の**単一動画ファイル**を必要とする。IVS の録画は HLS
（`.m3u8` + `.ts`/`.m4s` セグメント群）であり Rekognition `StartContentModeration` の直接入力に
できないため、AWS Elemental MediaConvert で HLS→MP4 に変換してから moderation へ渡す。

**2 フェーズ（start / collect）** で動作し、Step Functions の
`transcode start → Wait → transcode collect → moderation start → ...` から呼び出す想定。

- start: MediaConvert `create_job`（入力: HLS master `.m3u8`、出力: 単一 MP4 を S3 へ）。
  Job ID と、生成される MP4 のキー（moderation の `video_key`）を返す。
- collect: `get_job` で状態を確認し、`COMPLETE` なら `video_key` を返す（`ERROR`/`CANCELED` は error、
  それ以外は pending）。

Environment Variables:
    S3_SOURCE: HLS が存在し MP4 を出力する標準 S3 バケット名
    MEDIACONVERT_ROLE_ARN: MediaConvert がジョブ実行時に assume する IAM ロール ARN（start に必須）
    MEDIACONVERT_ENDPOINT: MediaConvert アカウントエンドポイント（未設定ならリージョン既定を使用）
    MEDIACONVERT_QUEUE_ARN: 使用するキュー ARN（任意）
    MEDIACONVERT_OUTPUT_PREFIX: MP4 出力プレフィックス（既定 "moderation/mp4/"）
    MASTER_MANIFEST_NAME: 入力に使う HLS master manifest 名（既定 "master.m3u8"）
"""

from __future__ import annotations

import logging
import os

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import trace_lambda_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

DEFAULT_MASTER_MANIFEST = "master.m3u8"
DEFAULT_OUTPUT_PREFIX = "moderation/mp4/"
# MediaConvert Job.Status の終了状態
COMPLETE_STATUS = "COMPLETE"
FAILED_STATUSES = ("ERROR", "CANCELED")


def _mediaconvert_client():
    """MediaConvert クライアントを返す。

    アカウント固有エンドポイントが `MEDIACONVERT_ENDPOINT` にあればそれを使い、無ければ
    リージョン既定エンドポイントを使う（現行の MediaConvert はリージョンエンドポイントに直接
    送信可能で DescribeEndpoints は必須ではない）。
    """
    endpoint = os.environ.get("MEDIACONVERT_ENDPOINT")
    if endpoint:
        return boto3.client("mediaconvert", endpoint_url=endpoint)
    return boto3.client("mediaconvert")


def _resolve_master_key(event: dict) -> str:
    """入力に使う HLS master manifest のキーを解決する。"""
    if event.get("master_key"):
        return event["master_key"]
    recording_prefix = (event.get("recording_prefix") or "").rstrip("/")
    if not recording_prefix:
        return ""
    master_name = os.environ.get("MASTER_MANIFEST_NAME", DEFAULT_MASTER_MANIFEST)
    source = S3ApHelper(os.environ["S3_SOURCE"])
    keys = [o["Key"] for o in source.list_objects(prefix=recording_prefix)]
    masters = [k for k in keys if k.endswith(master_name)]
    if masters:
        return masters[0]
    playlists = [k for k in keys if k.endswith(".m3u8")]
    return playlists[0] if playlists else ""


def _build_job_settings(bucket: str, master_key: str, destination: str) -> dict:
    """HLS→MP4 の最小 MediaConvert Job Settings を構築する（H.264/AAC の単一 MP4）。"""
    return {
        "Inputs": [
            {
                "FileInput": f"s3://{bucket}/{master_key}",
                "AudioSelectors": {"Audio Selector 1": {"DefaultSelection": "DEFAULT"}},
            }
        ],
        "OutputGroups": [
            {
                "Name": "File Group",
                "OutputGroupSettings": {
                    "Type": "FILE_GROUP_SETTINGS",
                    "FileGroupSettings": {"Destination": destination},
                },
                "Outputs": [
                    {
                        "ContainerSettings": {"Container": "MP4"},
                        "VideoDescription": {
                            "CodecSettings": {
                                "Codec": "H_264",
                                "H264Settings": {"RateControlMode": "QVBR", "MaxBitrate": 5000000},
                            }
                        },
                        "AudioDescriptions": [
                            {
                                "CodecSettings": {
                                    "Codec": "AAC",
                                    "AacSettings": {
                                        "Bitrate": 96000,
                                        "CodingMode": "CODING_MODE_2_0",
                                        "SampleRate": 48000,
                                    },
                                }
                            }
                        ],
                    }
                ],
            }
        ],
    }


def _start(event: dict, context) -> dict:
    """start フェーズ: MediaConvert HLS→MP4 ジョブを投入する。"""
    bucket = os.environ["S3_SOURCE"]
    role_arn = os.environ.get("MEDIACONVERT_ROLE_ARN", "")
    output_prefix = os.environ.get("MEDIACONVERT_OUTPUT_PREFIX", DEFAULT_OUTPUT_PREFIX)

    master_key = _resolve_master_key(event)
    if not master_key:
        return {"moderation_phase": "transcode", "status": "error", "reason": "no_master_manifest_found"}
    if not role_arn:
        return {"moderation_phase": "transcode", "status": "error", "reason": "mediaconvert_role_arn_not_set"}

    base = f"ivs-mp4-{context.aws_request_id}"
    destination = f"s3://{bucket}/{output_prefix}{base}"
    video_key = f"{output_prefix}{base}.mp4"

    params = {"Role": role_arn, "Settings": _build_job_settings(bucket, master_key, destination)}
    queue_arn = os.environ.get("MEDIACONVERT_QUEUE_ARN")
    if queue_arn:
        params["Queue"] = queue_arn

    client = _mediaconvert_client()
    resp = client.create_job(**params)
    job_id = resp.get("Job", {}).get("Id", "")

    logger.info("MediaConvert job started: id=%s, input=%s, video_key=%s", job_id, master_key, video_key)
    return {
        "moderation_phase": "transcode",
        "status": "started",
        "mediaconvert_job_id": job_id,
        "video_key": video_key,
        "output_bucket": bucket,
        "master_key": master_key,
    }


def _collect(event: dict, _context) -> dict:
    """collect フェーズ: MediaConvert ジョブ状態を確認し、完了なら video_key を返す。"""
    job_id = event.get("mediaconvert_job_id") or ""
    video_key = event.get("video_key") or ""
    if not job_id:
        return {"moderation_phase": "transcode", "status": "error", "reason": "no_mediaconvert_job_id"}

    client = _mediaconvert_client()
    resp = client.get_job(Id=job_id)
    status = resp.get("Job", {}).get("Status", "PROGRESSING")

    if status == COMPLETE_STATUS:
        return {"moderation_phase": "transcode", "status": "completed", "video_key": video_key, "job_status": status}
    if status in FAILED_STATUSES:
        return {"moderation_phase": "transcode", "status": "error", "job_status": status}
    return {"moderation_phase": "transcode", "status": "pending", "job_status": status}


@trace_lambda_handler
@lambda_error_handler
def handler(event, context) -> dict:
    """HLS→MP4 Transcode Lambda。`transcode_phase` で start / collect を切り替える。

    Returns:
        dict: start は mediaconvert_job_id / video_key を返す。collect は status
              （pending|completed|error）と、completed 時に video_key を返す。
    """
    phase = event.get("transcode_phase", "start")
    logger.info("Transcode phase=%s", phase)
    if phase == "start":
        return _start(event, context)
    if phase == "collect":
        return _collect(event, context)
    return {"moderation_phase": "transcode", "status": "error", "reason": f"unknown transcode_phase {phase!r}"}
