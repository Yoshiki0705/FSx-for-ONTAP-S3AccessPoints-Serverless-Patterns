"""HLS→MP4 Transcode Lambda（functions/transcode）ユニットテスト

start（MediaConvert ジョブ投入 / master 解決 / 前提エラー）と collect（COMPLETE / PROGRESSING /
ERROR）を、実 AWS を呼ばずにフェイクで検証する。
"""

from __future__ import annotations

from unittest.mock import MagicMock


class FakeMediaConvert:
    def __init__(self, job_id="mc-1", get_status="PROGRESSING"):
        self.job_id = job_id
        self._get_status = get_status
        self.created = None

    def create_job(self, **kwargs):
        self.created = kwargs
        return {"Job": {"Id": self.job_id, "Status": "SUBMITTED"}}

    def get_job(self, Id):  # noqa: N803
        return {"Job": {"Id": Id, "Status": self._get_status}}


def _dispatcher(mediaconvert):
    def _client(name, **kwargs):
        assert name == "mediaconvert"
        return mediaconvert

    return _client


def _ctx():
    ctx = MagicMock()
    ctx.aws_request_id = "req-xyz"
    return ctx


def _set_env(monkeypatch, **overrides):
    env = {
        "S3_SOURCE": "test-ivs-recordings",
        "MEDIACONVERT_ROLE_ARN": "arn:aws:iam::123456789012:role/MediaConvertRole",
        "MEDIACONVERT_ENDPOINT": "https://mc.example.com",
        "MEDIACONVERT_OUTPUT_PREFIX": "moderation/mp4/",
        "MASTER_MANIFEST_NAME": "master.m3u8",
    }
    env.update(overrides)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


class TestStatic:
    def _src(self, transcode_handler):
        import inspect

        return inspect.getsource(transcode_handler)

    def test_two_phase(self, transcode_handler):
        src = self._src(transcode_handler)
        assert 'phase == "start"' in src
        assert 'phase == "collect"' in src

    def test_error_handler(self, transcode_handler):
        assert "@lambda_error_handler" in self._src(transcode_handler)


class TestStart:
    def test_start_creates_job_and_returns_video_key(
        self, monkeypatch, transcode_handler, fake_s3ap_factory
    ):
        _set_env(monkeypatch)
        prefix = "ivs/v1/a/b/c/rec1"
        fake_src = fake_s3ap_factory(objects=[{"Key": f"{prefix}/master.m3u8", "Size": 1}])
        fake_mc = FakeMediaConvert(job_id="mc-99")
        monkeypatch.setattr(transcode_handler, "S3ApHelper", lambda *a, **k: fake_src)
        monkeypatch.setattr(transcode_handler.boto3, "client", _dispatcher(fake_mc))

        event = {"transcode_phase": "start", "recording_prefix": prefix}
        result = transcode_handler.handler(event, _ctx())

        assert result["status"] == "started"
        assert result["mediaconvert_job_id"] == "mc-99"
        assert result["video_key"] == "moderation/mp4/ivs-mp4-req-xyz.mp4"
        # input is the resolved master manifest
        assert fake_mc.created["Settings"]["Inputs"][0]["FileInput"].endswith("/master.m3u8")
        assert fake_mc.created["Role"].endswith("MediaConvertRole")

    def test_start_uses_explicit_master_key(
        self, monkeypatch, transcode_handler, fake_s3ap_factory
    ):
        _set_env(monkeypatch)
        fake_mc = FakeMediaConvert()
        # S3ApHelper should not be needed when master_key is explicit
        monkeypatch.setattr(transcode_handler.boto3, "client", _dispatcher(fake_mc))
        event = {"transcode_phase": "start", "master_key": "custom/path/index.m3u8"}
        result = transcode_handler.handler(event, _ctx())
        assert result["status"] == "started"
        assert fake_mc.created["Settings"]["Inputs"][0]["FileInput"].endswith("/custom/path/index.m3u8")

    def test_start_errors_without_role(self, monkeypatch, transcode_handler):
        _set_env(monkeypatch, MEDIACONVERT_ROLE_ARN="")
        event = {"transcode_phase": "start", "master_key": "p/master.m3u8"}
        result = transcode_handler.handler(event, _ctx())
        assert result["status"] == "error"
        assert result["reason"] == "mediaconvert_role_arn_not_set"

    def test_start_errors_without_master(self, monkeypatch, transcode_handler, fake_s3ap_factory):
        _set_env(monkeypatch)
        fake_src = fake_s3ap_factory(objects=[{"Key": "ivs/v1/a/b/c/rec1/0.ts", "Size": 1}])
        monkeypatch.setattr(transcode_handler, "S3ApHelper", lambda *a, **k: fake_src)
        event = {"transcode_phase": "start", "recording_prefix": "ivs/v1/a/b/c/rec1"}
        result = transcode_handler.handler(event, _ctx())
        assert result["status"] == "error"
        assert result["reason"] == "no_master_manifest_found"


class TestCollect:
    def test_collect_complete_returns_video_key(self, monkeypatch, transcode_handler):
        _set_env(monkeypatch)
        fake_mc = FakeMediaConvert(get_status="COMPLETE")
        monkeypatch.setattr(transcode_handler.boto3, "client", _dispatcher(fake_mc))
        event = {
            "transcode_phase": "collect",
            "mediaconvert_job_id": "mc-1",
            "video_key": "moderation/mp4/ivs-mp4-req-xyz.mp4",
        }
        result = transcode_handler.handler(event, _ctx())
        assert result["status"] == "completed"
        assert result["video_key"].endswith(".mp4")

    def test_collect_pending(self, monkeypatch, transcode_handler):
        _set_env(monkeypatch)
        fake_mc = FakeMediaConvert(get_status="PROGRESSING")
        monkeypatch.setattr(transcode_handler.boto3, "client", _dispatcher(fake_mc))
        event = {"transcode_phase": "collect", "mediaconvert_job_id": "mc-1"}
        result = transcode_handler.handler(event, _ctx())
        assert result["status"] == "pending"

    def test_collect_error(self, monkeypatch, transcode_handler):
        _set_env(monkeypatch)
        fake_mc = FakeMediaConvert(get_status="ERROR")
        monkeypatch.setattr(transcode_handler.boto3, "client", _dispatcher(fake_mc))
        event = {"transcode_phase": "collect", "mediaconvert_job_id": "mc-1"}
        result = transcode_handler.handler(event, _ctx())
        assert result["status"] == "error"
