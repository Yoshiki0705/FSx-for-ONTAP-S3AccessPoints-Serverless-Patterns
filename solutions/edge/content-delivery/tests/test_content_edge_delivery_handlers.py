"""content-edge-delivery Lambda ハンドラ ユニットテスト

publish / delivery_log_sync の入出力形式、配信モード分岐、
permission-aware フィルタ、PII マスクをテストする。
"""

from __future__ import annotations

import json
import os


# =========================================================================
# Publish Handler — 静的整合性
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

    def test_supports_both_delivery_modes(self):
        src = self._src()
        assert "ORIGIN_PULL" in src
        assert "PUBLISH_PUSH" in src

    def test_permission_aware_approved_prefix(self):
        # 承認済みプレフィックスに限定する permission-aware 設計
        assert "APPROVED_PREFIX" in self._src()

    def test_outputs_data_classification(self):
        assert "data_classification" in self._src()

    def test_records_approval_provenance(self):
        # Governance: 公開配信の承認証跡を記録する
        assert "provenance" in self._src()
        assert "_approval_provenance" in self._src()


# =========================================================================
# Publish Handler — 機能テスト
# =========================================================================


class TestPublishHandlerBehavior:
    def _set_env(self, monkeypatch, **overrides):
        env = {
            "S3_ACCESS_POINT": "vol-in-xxxxx-ext-s3alias",
            "S3_ACCESS_POINT_OUTPUT": "vol-out-xxxxx-ext-s3alias",
            "DATA_CLASSIFICATION": "PUBLIC",
        }
        env.update(overrides)
        for k, v in env.items():
            monkeypatch.setenv(k, v)

    def test_origin_pull_does_not_copy(self, monkeypatch, publish_handler, lambda_context, fake_s3ap_factory):
        self._set_env(monkeypatch, DELIVERY_MODE="ORIGIN_PULL", CDN_TARGET="AKAMAI")
        fake_in = fake_s3ap_factory(objects=[{"Key": "delivery-approved/clip.mp4", "Size": 10}])
        fake_out = fake_s3ap_factory()
        instances = iter([fake_in, fake_out])
        monkeypatch.setattr(publish_handler, "S3ApHelper", lambda *a, **k: next(instances))

        result = publish_handler.handler({}, lambda_context)

        assert result["delivery_mode"] == "ORIGIN_PULL"
        assert result["total_objects"] == 1
        assert result["published"][0]["cdn_target"] == "AKAMAI"
        # マニフェストが出力 AP に書き戻される
        assert len(fake_out.put_calls) == 1
        manifest = json.loads(fake_out.put_calls[0]["body"])
        assert manifest["data_classification"] == "PUBLIC"

    def test_publish_push_demo_mode_skips_external(
        self, monkeypatch, publish_handler, lambda_context, fake_s3ap_factory
    ):
        self._set_env(monkeypatch, DELIVERY_MODE="PUBLISH_PUSH", DEMO_MODE="true")
        fake_in = fake_s3ap_factory(objects=[{"Key": "delivery-approved/clip.mp4", "Size": 10}])
        fake_out = fake_s3ap_factory()
        instances = iter([fake_in, fake_out])
        monkeypatch.setattr(publish_handler, "S3ApHelper", lambda *a, **k: next(instances))

        result = publish_handler.handler({}, lambda_context)

        # DemoMode では外部 push をスキップ → published は空、skipped に記録
        assert result["total_objects"] == 0
        manifest = json.loads(fake_out.put_calls[0]["body"])
        assert len(manifest["skipped"]) == 1

    def test_only_approved_prefix_is_targeted(
        self, monkeypatch, publish_handler, lambda_context, fake_s3ap_factory
    ):
        self._set_env(monkeypatch, DELIVERY_MODE="ORIGIN_PULL")
        objs = [
            {"Key": "delivery-approved/ok.mp4", "Size": 1},
            {"Key": "master/secret.mov", "Size": 1},
        ]
        fake_in = fake_s3ap_factory(objects=objs)
        fake_out = fake_s3ap_factory()
        instances = iter([fake_in, fake_out])
        monkeypatch.setattr(publish_handler, "S3ApHelper", lambda *a, **k: next(instances))

        result = publish_handler.handler({}, lambda_context)

        keys = [p["key"] for p in result["published"]]
        assert "delivery-approved/ok.mp4" in keys
        assert "master/secret.mov" not in keys

    def test_records_approver_from_object_metadata(
        self, monkeypatch, publish_handler, lambda_context, fake_s3ap_factory
    ):
        self._set_env(monkeypatch, DELIVERY_MODE="ORIGIN_PULL")
        objs = [{"Key": "delivery-approved/ok.mp4", "Size": 1}]
        meta = {"delivery-approved/ok.mp4": {"approved-by": "release-mgr", "approval-id": "REL-42"}}
        fake_in = fake_s3ap_factory(objects=objs, metadata=meta)
        fake_out = fake_s3ap_factory()
        instances = iter([fake_in, fake_out])
        monkeypatch.setattr(publish_handler, "S3ApHelper", lambda *a, **k: next(instances))

        publish_handler.handler({}, lambda_context)

        manifest = json.loads(fake_out.put_calls[0]["body"])
        assert manifest["provenance"][0]["approver"] == "release-mgr"
        assert manifest["provenance"][0]["approval_id"] == "REL-42"

    def test_unrecorded_approver_is_surfaced_not_blocked(
        self, monkeypatch, publish_handler, lambda_context, fake_s3ap_factory
    ):
        self._set_env(monkeypatch, DELIVERY_MODE="ORIGIN_PULL")
        objs = [{"Key": "delivery-approved/ok.mp4", "Size": 1}]
        fake_in = fake_s3ap_factory(objects=objs)  # メタデータ無し
        fake_out = fake_s3ap_factory()
        instances = iter([fake_in, fake_out])
        monkeypatch.setattr(publish_handler, "S3ApHelper", lambda *a, **k: next(instances))

        result = publish_handler.handler({}, lambda_context)

        manifest = json.loads(fake_out.put_calls[0]["body"])
        # 承認元未記録は "unrecorded" として可視化（配信は止めない）
        assert manifest["provenance"][0]["approver"] == "unrecorded"
        assert result["total_objects"] == 1


# =========================================================================
# Delivery Log Sync Handler
# =========================================================================


class TestDeliveryLogSyncHandler:
    def _set_env(self, monkeypatch, **overrides):
        env = {
            "S3_ACCESS_POINT_OUTPUT": "vol-out-xxxxx-ext-s3alias",
            "DATA_CLASSIFICATION": "INTERNAL",
            "DEMO_MODE": "true",
        }
        env.update(overrides)
        for k, v in env.items():
            monkeypatch.setenv(k, v)

    def test_redacts_client_ip_by_default(
        self, monkeypatch, delivery_log_sync_handler, lambda_context, fake_s3ap_factory
    ):
        self._set_env(monkeypatch)
        fake_out = fake_s3ap_factory()
        monkeypatch.setattr(delivery_log_sync_handler, "S3ApHelper", lambda *a, **k: fake_out)

        event = {"log_records": [{"timestamp": "t", "key": "clip.mp4", "status": "200", "bytes": 100, "client_ip": "203.0.113.5"}]}
        result = delivery_log_sync_handler.handler(event, lambda_context)

        assert result["record_count"] == 1
        assert result["total_bytes"] == 100
        summary = json.loads(fake_out.put_calls[0]["body"])
        assert summary["records"][0]["client_ip"] == "203.0.x.x"

    def test_no_redaction_when_disabled(
        self, monkeypatch, delivery_log_sync_handler, lambda_context, fake_s3ap_factory
    ):
        self._set_env(monkeypatch, REDACT_CLIENT_IP="false")
        fake_out = fake_s3ap_factory()
        monkeypatch.setattr(delivery_log_sync_handler, "S3ApHelper", lambda *a, **k: fake_out)

        event = {"log_records": [{"client_ip": "203.0.113.5", "bytes": 1}]}
        result = delivery_log_sync_handler.handler(event, lambda_context)

        summary = json.loads(fake_out.put_calls[0]["body"])
        assert summary["records"][0]["client_ip"] == "203.0.113.5"
        assert result["record_count"] == 1


# =========================================================================
# Publish Handler — External store push (Security/QA)
# =========================================================================


class TestExternalStorePush:
    def _set_env(self, monkeypatch, **overrides):
        env = {
            "S3_ACCESS_POINT": "vol-in-xxxxx-ext-s3alias",
            "S3_ACCESS_POINT_OUTPUT": "vol-out-xxxxx-ext-s3alias",
            "DATA_CLASSIFICATION": "PUBLIC",
        }
        env.update(overrides)
        for k, v in env.items():
            monkeypatch.setenv(k, v)

    def test_publish_push_copies_to_external_store(
        self, monkeypatch, publish_handler, lambda_context, fake_s3ap_factory
    ):
        self._set_env(
            monkeypatch,
            DELIVERY_MODE="PUBLISH_PUSH",
            DEMO_MODE="false",
            EXTERNAL_STORE_BUCKET="cdn-bucket",
            EXTERNAL_STORE_ENDPOINT="https://obj.example.com",
        )
        fake_in = fake_s3ap_factory(
            objects=[{"Key": "delivery-approved/clip.mp4", "Size": 3}],
            bodies={"delivery-approved/clip.mp4": b"abc"},
        )
        fake_out = fake_s3ap_factory()
        instances = iter([fake_in, fake_out])
        monkeypatch.setattr(publish_handler, "S3ApHelper", lambda *a, **k: next(instances))

        put_calls = []

        class FakeClient:
            def put_object(self, **kw):
                put_calls.append(kw)
                return {}

        class FakeSession:
            def client(self, name, **kw):
                return FakeClient()

        monkeypatch.setattr(publish_handler.boto3, "Session", lambda *a, **k: FakeSession())

        result = publish_handler.handler({}, lambda_context)

        assert result["total_objects"] == 1
        assert put_calls and put_calls[0]["Bucket"] == "cdn-bucket"
        assert put_calls[0]["Key"] == "delivery-approved/clip.mp4"

    def test_external_store_session_uses_secret(self, monkeypatch, publish_handler):
        monkeypatch.setenv("EXTERNAL_STORE_SECRET_NAME", "ext-store")
        captured = {}

        class FakeSM:
            def get_secret_value(self, SecretId):
                captured["secret_id"] = SecretId
                return {"SecretString": json.dumps({"access_key_id": "AKIAEXAMPLE", "secret_access_key": "sk"})}

        def fake_client(name, **kw):
            assert name == "secretsmanager"
            return FakeSM()

        def fake_session(**kw):
            captured["session_kwargs"] = kw
            return "SESSION"

        monkeypatch.setattr(publish_handler.boto3, "client", fake_client)
        monkeypatch.setattr(publish_handler.boto3, "Session", fake_session)

        sess = publish_handler._external_store_session()

        assert sess == "SESSION"
        assert captured["secret_id"] == "ext-store"
        assert captured["session_kwargs"]["aws_access_key_id"] == "AKIAEXAMPLE"

    def test_external_store_session_none_without_secret(self, monkeypatch, publish_handler):
        monkeypatch.delenv("EXTERNAL_STORE_SECRET_NAME", raising=False)
        assert publish_handler._external_store_session() is None

    def test_suffix_filter_limits_targets(self, publish_handler):
        objs = [{"Key": "delivery-approved/a.mp4"}, {"Key": "delivery-approved/b.txt"}]
        out = publish_handler._filter_targets(objs, ".mp4")
        assert [o["Key"] for o in out] == ["delivery-approved/a.mp4"]
        # 空サフィックスは全件
        assert publish_handler._filter_targets(objs, "") == objs
