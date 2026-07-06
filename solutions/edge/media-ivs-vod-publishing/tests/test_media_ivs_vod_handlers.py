"""media-ivs-vod-publishing Publish Lambda ハンドラ ユニットテスト

Recording End 分岐、master manifest 検証、Human Review 判定、DemoMode、
permission-aware 取り込み境界、データ分類をテストする。
"""

from __future__ import annotations

import json
import os


def recording_end_event(prefix: str = "ivs/v1/123456789012/AbCdef1G2hij/2020/6/23/20/12/rec1"):
    """IVS Recording End EventBridge イベントのサンプルを生成する。"""
    return {
        "detail-type": "IVS Recording State Change",
        "source": "aws.ivs",
        "detail": {
            "channel_name": "Test Channel",
            "recording_status": "Recording End",
            "recording_s3_bucket_name": "test-ivs-recordings",
            "recording_s3_key_prefix": prefix,
            "recording_session_id": "sess-1",
        },
    }


# =========================================================================
# 静的整合性
# =========================================================================


class TestPublishHandlerStatic:
    def _src(self):
        path = os.path.join(os.path.dirname(__file__), "..", "functions", "publish", "handler.py")
        with open(path) as f:
            return f.read()

    def test_handler_entry_point(self):
        assert "def handler(event, context)" in self._src()

    def test_uses_lambda_error_handler(self):
        assert "@lambda_error_handler" in self._src()

    def test_uses_human_review(self):
        src = self._src()
        assert "evaluate_confidence" in src
        assert "human_review" in src

    def test_validates_recording_end(self):
        assert "Recording End" in self._src()

    def test_outputs_data_classification(self):
        assert "data_classification" in self._src()

    def test_validates_master_manifest(self):
        assert "master_manifest_present" in self._src()


# =========================================================================
# 機能テスト
# =========================================================================


def _set_env(monkeypatch, **overrides):
    env = {
        "S3_SOURCE": "test-ivs-recordings",
        "S3_ACCESS_POINT_OUTPUT": "vol-out-xxxxx-ext-s3alias",
        "DATA_CLASSIFICATION": "PUBLIC",
        "MASTER_MANIFEST_NAME": "master.m3u8",
    }
    env.update(overrides)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def _wire(monkeypatch, publish_handler, fake_in, fake_out):
    instances = iter([fake_in, fake_out])
    monkeypatch.setattr(publish_handler, "S3ApHelper", lambda *a, **k: next(instances))


class TestPublishBehavior:
    def _package(self, prefix):
        return [
            {"Key": f"{prefix}/master.m3u8", "Size": 1},
            {"Key": f"{prefix}/playlist.m3u8", "Size": 1},
            {"Key": f"{prefix}/0.ts", "Size": 10},
            {"Key": f"{prefix}/1.ts", "Size": 10},
        ]

    def test_recording_end_auto_approves_complete_package(
        self, monkeypatch, publish_handler, lambda_context, fake_s3ap_factory
    ):
        _set_env(monkeypatch, DEMO_MODE="false")
        prefix = "ivs/v1/123456789012/AbCdef1G2hij/2020/6/23/20/12/rec1"
        fake_in = fake_s3ap_factory(objects=self._package(prefix))
        fake_out = fake_s3ap_factory()
        _wire(monkeypatch, publish_handler, fake_in, fake_out)

        result = publish_handler.handler(recording_end_event(prefix), lambda_context)

        assert result["status"] == "completed"
        assert result["master_manifest_present"] is True
        assert result["human_review"]["action"] == "AUTO_APPROVE"
        # 4 objects copied + 1 manifest write == 5 puts
        assert len(fake_out.put_calls) == 5
        manifest = json.loads(fake_out.put_calls[-1]["body"])
        assert manifest["data_classification"] == "PUBLIC"

    def test_non_recording_end_is_skipped(
        self, monkeypatch, publish_handler, lambda_context, fake_s3ap_factory
    ):
        _set_env(monkeypatch)
        fake_in = fake_s3ap_factory(objects=[])
        fake_out = fake_s3ap_factory()
        _wire(monkeypatch, publish_handler, fake_in, fake_out)

        event = recording_end_event()
        event["detail"]["recording_status"] = "Recording Start"
        result = publish_handler.handler(event, lambda_context)

        assert result["status"] == "skipped"
        # nothing written
        assert fake_out.put_calls == []

    def test_demo_mode_skips_copy_but_writes_manifest(
        self, monkeypatch, publish_handler, lambda_context, fake_s3ap_factory
    ):
        _set_env(monkeypatch, DEMO_MODE="true")
        prefix = "ivs/v1/acct/chan/rec2"
        fake_in = fake_s3ap_factory(objects=self._package(prefix))
        fake_out = fake_s3ap_factory()
        _wire(monkeypatch, publish_handler, fake_in, fake_out)

        result = publish_handler.handler(recording_end_event(prefix), lambda_context)

        assert result["status"] == "completed"
        assert result["total_objects"] == 0  # no real copy
        # only the manifest write
        assert len(fake_out.put_calls) == 1
        manifest = json.loads(fake_out.put_calls[0]["body"])
        assert len(manifest["skipped"]) == 4
        assert all(s["reason"] == "demo_mode" for s in manifest["skipped"])

    def test_missing_master_manifest_triggers_human_review(
        self, monkeypatch, publish_handler, lambda_context, fake_s3ap_factory
    ):
        _set_env(monkeypatch, DEMO_MODE="true")
        prefix = "ivs/v1/acct/chan/rec3"
        # segments only, no manifest at all
        objs = [{"Key": f"{prefix}/0.ts", "Size": 10}]
        fake_in = fake_s3ap_factory(objects=objs)
        fake_out = fake_s3ap_factory()
        _wire(monkeypatch, publish_handler, fake_in, fake_out)

        result = publish_handler.handler(recording_end_event(prefix), lambda_context)

        assert result["master_manifest_present"] is False
        assert result["human_review"]["action"] == "HUMAN_REVIEW"

    def test_empty_package_is_rejected(
        self, monkeypatch, publish_handler, lambda_context, fake_s3ap_factory
    ):
        _set_env(monkeypatch, DEMO_MODE="false")
        prefix = "ivs/v1/acct/chan/rec4"
        fake_in = fake_s3ap_factory(objects=[])
        fake_out = fake_s3ap_factory()
        _wire(monkeypatch, publish_handler, fake_in, fake_out)

        result = publish_handler.handler(recording_end_event(prefix), lambda_context)

        assert result["human_review"]["action"] == "REJECT"
        assert result["total_objects"] == 0
        # only manifest write, no copy
        assert len(fake_out.put_calls) == 1

    def test_only_recording_prefix_is_ingested(
        self, monkeypatch, publish_handler, lambda_context, fake_s3ap_factory
    ):
        _set_env(monkeypatch, DEMO_MODE="false")
        prefix = "ivs/v1/acct/chan/rec5"
        objs = self._package(prefix) + [{"Key": "other/secret.mov", "Size": 5}]
        fake_in = fake_s3ap_factory(objects=objs)
        fake_out = fake_s3ap_factory()
        _wire(monkeypatch, publish_handler, fake_in, fake_out)

        result = publish_handler.handler(recording_end_event(prefix), lambda_context)

        copied_keys = [p["key"] for p in result["published"]]
        assert "other/secret.mov" not in copied_keys
        assert f"{prefix}/master.m3u8" in copied_keys

    def test_large_object_uses_streaming_multipart(
        self, monkeypatch, publish_handler, lambda_context, fake_s3ap_factory
    ):
        # Storage lens: > threshold(既定 100MB) は streaming multipart で書き込む（skip しない）
        _set_env(monkeypatch, DEMO_MODE="false")
        prefix = "ivs/v1/acct/chan/recBig"
        objs = [
            {"Key": f"{prefix}/master.m3u8", "Size": 1},  # small -> putobject
            {"Key": f"{prefix}/0.ts", "Size": 10},  # small -> putobject
            {"Key": f"{prefix}/big.ts", "Size": 200 * 1024 * 1024},  # 200MB -> multipart
        ]
        fake_in = fake_s3ap_factory(objects=objs)
        fake_out = fake_s3ap_factory()
        _wire(monkeypatch, publish_handler, fake_in, fake_out)

        result = publish_handler.handler(recording_end_event(prefix), lambda_context)

        by_key = {p["key"]: p for p in result["published"]}
        assert by_key[f"{prefix}/big.ts"]["method"] == "multipart"
        assert by_key[f"{prefix}/master.m3u8"]["method"] == "putobject"
        # multipart write recorded on output
        assert any(c.get("multipart") for c in fake_out.put_calls)

    def test_exceeds_lambda_ceiling_is_skipped(
        self, monkeypatch, publish_handler, lambda_context, fake_s3ap_factory
    ):
        # Reliability lens: MAX_LAMBDA_INGEST_GB 超は skip して DataSync/ECS を推奨
        _set_env(monkeypatch, DEMO_MODE="false", MAX_LAMBDA_INGEST_GB="0.1")  # ~107 MB ceiling
        prefix = "ivs/v1/acct/chan/recCeil"
        objs = [
            {"Key": f"{prefix}/master.m3u8", "Size": 1},
            {"Key": f"{prefix}/toobig.ts", "Size": 200 * 1024 * 1024},  # 200MB > 0.1GB
        ]
        fake_in = fake_s3ap_factory(objects=objs)
        fake_out = fake_s3ap_factory()
        _wire(monkeypatch, publish_handler, fake_in, fake_out)

        result = publish_handler.handler(recording_end_event(prefix), lambda_context)

        published_keys = [p["key"] for p in result["published"]]
        assert f"{prefix}/toobig.ts" not in published_keys
        manifest = json.loads(fake_out.put_calls[-1]["body"])
        skipped = [s for s in manifest["skipped"] if s.get("reason", "").startswith("exceeds_lambda_ingest_limit")]
        assert len(skipped) == 1

    def test_manifest_written_under_vod_publish_prefix(
        self, monkeypatch, publish_handler, lambda_context, fake_s3ap_factory
    ):
        _set_env(monkeypatch, DEMO_MODE="true")
        prefix = "ivs/v1/acct/chan/rec6"
        fake_in = fake_s3ap_factory(objects=self._package(prefix))
        fake_out = fake_s3ap_factory()
        _wire(monkeypatch, publish_handler, fake_in, fake_out)

        result = publish_handler.handler(recording_end_event(prefix), lambda_context)

        assert result["manifest_key"].startswith("vod-publish-manifests/")
        assert result["manifest_key"].endswith(".json")


# =========================================================================
# Content moderation (opt-in, Rekognition) — Governance
# =========================================================================


class _FakeRekognition:
    def __init__(self, labels=None):
        self._labels = labels or []
        self.calls = 0

    def detect_moderation_labels(self, Image, MinConfidence):  # noqa: N803 (boto3 kwarg casing)
        self.calls += 1
        return {"ModerationLabels": self._labels}


class TestModeration:
    def _pkg_with_thumb(self, prefix):
        return [
            {"Key": f"{prefix}/master.m3u8", "Size": 1},
            {"Key": f"{prefix}/0.ts", "Size": 10},
            {"Key": f"{prefix}/thumbnails/thumb0.jpg", "Size": 2},
        ]

    def test_moderation_disabled_by_default(
        self, monkeypatch, publish_handler, lambda_context, fake_s3ap_factory
    ):
        _set_env(monkeypatch, DEMO_MODE="false")  # ENABLE_MODERATION unset
        prefix = "ivs/v1/acct/chan/recModOff"
        fake_in = fake_s3ap_factory(objects=self._pkg_with_thumb(prefix))
        fake_out = fake_s3ap_factory()
        _wire(monkeypatch, publish_handler, fake_in, fake_out)

        # if rekognition were called it would raise
        monkeypatch.setattr(publish_handler.boto3, "client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("rekognition should not be called")))

        result = publish_handler.handler(recording_end_event(prefix), lambda_context)
        assert result["moderation"]["enabled"] is False
        assert result["blocked_by_moderation"] is False
        assert result["total_objects"] == 3

    def test_moderation_clean_allows_publish(
        self, monkeypatch, publish_handler, lambda_context, fake_s3ap_factory
    ):
        _set_env(monkeypatch, DEMO_MODE="false", ENABLE_MODERATION="true")
        prefix = "ivs/v1/acct/chan/recModClean"
        fake_in = fake_s3ap_factory(objects=self._pkg_with_thumb(prefix))
        fake_out = fake_s3ap_factory()
        _wire(monkeypatch, publish_handler, fake_in, fake_out)
        fake_rek = _FakeRekognition(labels=[])  # no moderation labels
        monkeypatch.setattr(publish_handler.boto3, "client", lambda *a, **k: fake_rek)

        result = publish_handler.handler(recording_end_event(prefix), lambda_context)

        assert result["moderation"]["enabled"] is True
        assert result["moderation"]["flagged"] is False
        assert result["moderation"]["images_checked"] == 1
        assert result["blocked_by_moderation"] is False
        assert result["total_objects"] == 3
        assert fake_rek.calls == 1

    def test_moderation_flagged_blocks_publish(
        self, monkeypatch, publish_handler, lambda_context, fake_s3ap_factory
    ):
        _set_env(monkeypatch, DEMO_MODE="false", ENABLE_MODERATION="true")
        prefix = "ivs/v1/acct/chan/recModFlag"
        fake_in = fake_s3ap_factory(objects=self._pkg_with_thumb(prefix))
        fake_out = fake_s3ap_factory()
        _wire(monkeypatch, publish_handler, fake_in, fake_out)
        fake_rek = _FakeRekognition(labels=[{"Name": "Explicit Nudity", "Confidence": 96.5}])
        monkeypatch.setattr(publish_handler.boto3, "client", lambda *a, **k: fake_rek)

        result = publish_handler.handler(recording_end_event(prefix), lambda_context)

        assert result["moderation"]["flagged"] is True
        assert result["blocked_by_moderation"] is True
        assert result["total_objects"] == 0  # nothing published
        manifest = json.loads(fake_out.put_calls[-1]["body"])
        assert all(s["reason"] == "blocked_by_moderation" for s in manifest["skipped"])
        assert manifest["moderation"]["max_confidence"] == 96.5

    def test_moderation_skipped_in_demo_mode(
        self, monkeypatch, publish_handler, lambda_context, fake_s3ap_factory
    ):
        _set_env(monkeypatch, DEMO_MODE="true", ENABLE_MODERATION="true")
        prefix = "ivs/v1/acct/chan/recModDemo"
        fake_in = fake_s3ap_factory(objects=self._pkg_with_thumb(prefix))
        fake_out = fake_s3ap_factory()
        _wire(monkeypatch, publish_handler, fake_in, fake_out)
        # rekognition must NOT be called in demo mode
        monkeypatch.setattr(publish_handler.boto3, "client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no rekognition in demo mode")))

        result = publish_handler.handler(recording_end_event(prefix), lambda_context)
        assert result["moderation"]["skipped"] == "demo_mode"
        assert result["blocked_by_moderation"] is False


# =========================================================================
# パッケージ完全性スコア（内部関数）
# =========================================================================


class TestScorePackage:
    def test_complete_package_high_confidence(self, publish_handler):
        keys = ["p/master.m3u8", "p/0.ts"]
        confidence, has_master, master_key = publish_handler._score_package(keys, "master.m3u8")
        assert confidence >= 0.85
        assert has_master is True
        assert master_key == "p/master.m3u8"

    def test_playlist_without_master_name(self, publish_handler):
        keys = ["p/index.m3u8", "p/0.ts"]
        confidence, has_master, _ = publish_handler._score_package(keys, "master.m3u8")
        assert 0.30 <= confidence < 0.85
        assert has_master is False

    def test_empty_package_low_confidence(self, publish_handler):
        confidence, has_master, _ = publish_handler._score_package([], "master.m3u8")
        assert confidence < 0.30
        assert has_master is False
