"""Strict moderation Lambda（functions/moderation）ユニットテスト

start / collect の 2 フェーズと、動画（Rekognition）・音声（Transcribe→Comprehend）・
字幕（Comprehend）の各判定を、実 AWS を呼ばずにフェイクで検証する。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class FakeComprehend:
    def __init__(self, result_list):
        self._result_list = result_list
        self.calls = 0

    def detect_toxic_content(self, TextSegments, LanguageCode):  # noqa: N803 (boto3 kwargs)
        self.calls += 1
        return {"ResultList": self._result_list}


class FakeRekognition:
    def __init__(self, job_id="rek-1", get_resp=None):
        self.job_id = job_id
        self._get_resp = get_resp or {"JobStatus": "IN_PROGRESS"}
        self.started = None

    def start_content_moderation(self, Video, MinConfidence):  # noqa: N803
        self.started = {"Video": Video, "MinConfidence": MinConfidence}
        return {"JobId": self.job_id}

    def get_content_moderation(self, JobId):  # noqa: N803
        return self._get_resp


class FakeTranscribe:
    def __init__(self, get_resp=None):
        self._get_resp = get_resp or {"TranscriptionJob": {"TranscriptionJobStatus": "IN_PROGRESS"}}
        self.started = None

    def start_transcription_job(self, **kwargs):
        self.started = kwargs
        return {}

    def get_transcription_job(self, TranscriptionJobName):  # noqa: N803
        return self._get_resp


class FakeS3:
    def __init__(self, body: bytes):
        self._body = body

    def get_object(self, Bucket, Key):  # noqa: N803
        m = MagicMock()
        m.read.return_value = self._body
        return {"Body": m}


def _dispatcher(**fakes):
    def _client(name, **kwargs):
        return fakes[name]

    return _client


CLEAN = [{"Toxicity": 0.02, "Labels": []}]
TOXIC = [{"Toxicity": 0.94, "Labels": [{"Name": "PROFANITY", "Score": 0.95}]}]


def _set_env(monkeypatch, **overrides):
    env = {
        "S3_SOURCE": "test-ivs-recordings",
        "MODERATION_MIN_CONFIDENCE": "80",
        "MODERATION_TOXICITY_THRESHOLD": "0.5",
        "MODERATION_LANGUAGE_CODE": "en",
    }
    env.update(overrides)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


# --------------------------------------------------------------------------- #
# Static
# --------------------------------------------------------------------------- #


class TestStatic:
    def _src(self, moderation_handler):
        import inspect

        return inspect.getsource(moderation_handler)

    def test_two_phase_dispatch(self, moderation_handler):
        src = self._src(moderation_handler)
        assert 'phase == "start"' in src
        assert 'phase == "collect"' in src

    def test_uses_error_handler(self, moderation_handler):
        assert "@lambda_error_handler" in self._src(moderation_handler)


# --------------------------------------------------------------------------- #
# Caption / text helpers
# --------------------------------------------------------------------------- #


class TestCaptionHelpers:
    def test_extract_caption_text_strips_cues(self, moderation_handler):
        vtt = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:04.000\nHello world\n\n2\n00:00:05.000 --> 00:00:07.000\nSecond line"
        text = moderation_handler._extract_caption_text(vtt)
        assert "Hello world" in text
        assert "Second line" in text
        assert "-->" not in text
        assert "WEBVTT" not in text

    def test_chunk_text_caps_segments(self, moderation_handler):
        chunks = moderation_handler._chunk_text("a" * 5000, max_segments=3, seg_chars=900)
        assert len(chunks) == 3


# --------------------------------------------------------------------------- #
# Phase: start
# --------------------------------------------------------------------------- #


class TestStartPhase:
    def _ctx(self):
        ctx = MagicMock()
        ctx.aws_request_id = "req-1"
        return ctx

    def test_start_captions_flagged_no_video(
        self, monkeypatch, moderation_handler, fake_s3ap_factory
    ):
        _set_env(monkeypatch)
        prefix = "ivs/v1/a/b/c/rec1"
        fake_src = fake_s3ap_factory(
            objects=[{"Key": f"{prefix}/captions.vtt", "Size": 5}],
            bodies={f"{prefix}/captions.vtt": b"WEBVTT\n\n1\n00:00 --> 00:01\nbad words here"},
        )
        monkeypatch.setattr(moderation_handler, "S3ApHelper", lambda *a, **k: fake_src)
        monkeypatch.setattr(moderation_handler.boto3, "client", _dispatcher(comprehend=FakeComprehend(TOXIC)))

        event = {"moderation_phase": "start", "recording_prefix": prefix}
        result = moderation_handler.handler(event, self._ctx())

        assert result["captions_flagged"] is True
        assert result["started"] == {"video": False, "audio": False}
        assert result["rekognition_job_id"] == ""

    def test_start_with_video_starts_async_jobs(
        self, monkeypatch, moderation_handler, fake_s3ap_factory
    ):
        _set_env(monkeypatch)
        prefix = "ivs/v1/a/b/c/rec2"
        fake_src = fake_s3ap_factory(objects=[{"Key": f"{prefix}/master.m3u8", "Size": 1}])
        fake_rek = FakeRekognition(job_id="rek-42")
        fake_tr = FakeTranscribe()
        monkeypatch.setattr(moderation_handler, "S3ApHelper", lambda *a, **k: fake_src)
        monkeypatch.setattr(
            moderation_handler.boto3,
            "client",
            _dispatcher(comprehend=FakeComprehend(CLEAN), rekognition=fake_rek, transcribe=fake_tr),
        )

        event = {"moderation_phase": "start", "recording_prefix": prefix, "video_key": f"{prefix}/vod.mp4"}
        result = moderation_handler.handler(event, self._ctx())

        assert result["rekognition_job_id"] == "rek-42"
        assert result["transcribe_job_name"].startswith("ivs-mod-")
        assert result["started"] == {"video": True, "audio": True}
        assert result["captions_flagged"] is False
        # transcribe started with the correct media uri
        assert fake_tr.started["Media"]["MediaFileUri"].endswith("/vod.mp4")


# --------------------------------------------------------------------------- #
# Phase: collect
# --------------------------------------------------------------------------- #


class TestCollectPhase:
    def test_collect_video_flagged_blocks(self, monkeypatch, moderation_handler):
        _set_env(monkeypatch)
        rek = FakeRekognition(
            get_resp={
                "JobStatus": "SUCCEEDED",
                "ModerationLabels": [{"ModerationLabel": {"Name": "Explicit Nudity", "Confidence": 97.0}}],
            }
        )
        monkeypatch.setattr(moderation_handler.boto3, "client", _dispatcher(rekognition=rek))

        event = {"moderation_phase": "collect", "rekognition_job_id": "rek-1"}
        result = moderation_handler.handler(event, MagicMock())

        assert result["status"] == "completed"
        assert result["flagged"] is True
        assert result["decision"] == "BLOCK"

    def test_collect_pending_when_in_progress(self, monkeypatch, moderation_handler):
        _set_env(monkeypatch)
        rek = FakeRekognition(get_resp={"JobStatus": "IN_PROGRESS"})
        monkeypatch.setattr(moderation_handler.boto3, "client", _dispatcher(rekognition=rek))

        event = {"moderation_phase": "collect", "rekognition_job_id": "rek-1"}
        result = moderation_handler.handler(event, MagicMock())

        assert result["status"] == "pending"

    def test_collect_audio_toxic_blocks(self, monkeypatch, moderation_handler):
        _set_env(monkeypatch)
        transcript = json.dumps({"results": {"transcripts": [{"transcript": "some toxic transcript"}]}}).encode()
        transcribe = FakeTranscribe(get_resp={"TranscriptionJob": {"TranscriptionJobStatus": "COMPLETED"}})
        monkeypatch.setattr(
            moderation_handler.boto3,
            "client",
            _dispatcher(transcribe=transcribe, s3=FakeS3(transcript), comprehend=FakeComprehend(TOXIC)),
        )

        event = {
            "moderation_phase": "collect",
            "transcribe_job_name": "ivs-mod-x",
            "transcribe_output_key": "moderation/transcripts/ivs-mod-x.json",
        }
        result = moderation_handler.handler(event, MagicMock())

        assert result["status"] == "completed"
        assert result["audio"]["flagged"] is True
        assert result["decision"] == "BLOCK"

    def test_collect_allow_when_all_clean(self, monkeypatch, moderation_handler):
        _set_env(monkeypatch)
        rek = FakeRekognition(get_resp={"JobStatus": "SUCCEEDED", "ModerationLabels": []})
        transcript = json.dumps({"results": {"transcripts": [{"transcript": "hello friendly world"}]}}).encode()
        transcribe = FakeTranscribe(get_resp={"TranscriptionJob": {"TranscriptionJobStatus": "COMPLETED"}})
        monkeypatch.setattr(
            moderation_handler.boto3,
            "client",
            _dispatcher(rekognition=rek, transcribe=transcribe, s3=FakeS3(transcript), comprehend=FakeComprehend(CLEAN)),
        )

        event = {
            "moderation_phase": "collect",
            "rekognition_job_id": "rek-1",
            "transcribe_job_name": "ivs-mod-x",
            "transcribe_output_key": "moderation/transcripts/ivs-mod-x.json",
            "captions_flagged": False,
        }
        result = moderation_handler.handler(event, MagicMock())

        assert result["status"] == "completed"
        assert result["flagged"] is False
        assert result["decision"] == "ALLOW"
