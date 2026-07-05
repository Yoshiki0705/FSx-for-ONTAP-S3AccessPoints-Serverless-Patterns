"""Tests for FPolicy Engine IP Updater handler (Phase 13 Task 2).

ECS Task State Change イベントから ONTAP FPolicy engine IP を更新する
3ステップシーケンス (disable → update → re-enable) のユニットテスト。

moto (Secrets Manager) + unittest.mock (urllib3 / ONTAP REST API) でモック化。
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws


@pytest.fixture(autouse=True)
def _env_setup(monkeypatch):
    """テスト用環境変数を設定する。"""
    monkeypatch.setenv("FSXN_MGMT_IP", "10.0.1.100")
    monkeypatch.setenv("FSXN_SVM_UUID", "test-svm-uuid-1234")
    monkeypatch.setenv("FSXN_ENGINE_NAME", "fpolicy_aws_engine")
    monkeypatch.setenv("FSXN_POLICY_NAME", "fpolicy_aws")
    monkeypatch.setenv("FSXN_CREDENTIALS_SECRET", "ontap-admin-creds")
    monkeypatch.setenv("ECS_CLUSTER_NAME", "fpolicy-cluster")
    monkeypatch.setenv("ECS_SERVICE_NAME", "fpolicy-service")


@pytest.fixture
def mock_context():
    """Lambda コンテキストのモック。"""
    ctx = MagicMock()
    ctx.function_name = "fpolicy-ip-updater"
    ctx.aws_request_id = "test-req-456"
    return ctx


def _ecs_task_event(
    task_ip: str = "10.0.2.50",
    last_status: str = "RUNNING",
    desired_status: str = "RUNNING",
    cluster_arn: str = "arn:aws:ecs:ap-northeast-1:123456789012:cluster/fpolicy-cluster",
    group: str = "service:fpolicy-service",
) -> dict:
    """ECS Task State Change イベントを生成する。"""
    return {
        "source": "aws.ecs",
        "detail-type": "ECS Task State Change",
        "detail": {
            "lastStatus": last_status,
            "desiredStatus": desired_status,
            "clusterArn": cluster_arn,
            "group": group,
            "taskArn": "arn:aws:ecs:ap-northeast-1:123456789012:task/fpolicy-cluster/abc123",
            "attachments": [
                {
                    "type": "ElasticNetworkInterface",
                    "status": "ATTACHED",
                    "details": [
                        {"name": "subnetId", "value": "subnet-012345"},
                        {"name": "networkInterfaceId", "value": "eni-012345"},
                        {"name": "privateIPv4Address", "value": task_ip},
                    ],
                }
            ],
        },
    }


def _mock_ontap_response(status: int = 200, body: dict | None = None) -> MagicMock:
    """urllib3 のレスポンスモックを作成する。"""
    resp = MagicMock()
    resp.status = status
    resp.data = json.dumps(body or {}).encode()
    return resp


@mock_aws
class TestIPUpdaterSuccess:
    """正常系: 3ステップシーケンスの成功パス。"""

    def _setup_secrets(self):
        """Secrets Manager にテスト用クレデンシャルを作成する。"""
        sm = boto3.client("secretsmanager", region_name="ap-northeast-1")
        sm.create_secret(
            Name="ontap-admin-creds",
            SecretString=json.dumps({"username": "admin", "password": "test-pass"}),
        )

    @patch("shared.lambdas.fpolicy_engine.handler.urllib3.PoolManager")
    def test_full_update_sequence(self, mock_pool_cls, mock_context):
        """disable → update → re-enable の3ステップが正常に実行される。"""
        self._setup_secrets()
        mock_pool = MagicMock()
        mock_pool_cls.return_value = mock_pool
        mock_pool.request.return_value = _mock_ontap_response(200)

        from shared.lambdas.fpolicy_engine.handler import handler

        result = handler(_ecs_task_event(task_ip="10.0.2.99"), mock_context)

        assert result["statusCode"] == 200
        assert "10.0.2.99" in result["body"]

        # Verify 3 ONTAP API calls: disable, update engine, re-enable
        calls = mock_pool.request.call_args_list
        assert len(calls) == 3

        # Call 1: disable policy
        assert calls[0][0][0] == "PATCH"
        assert "policies/fpolicy_aws" in calls[0][0][1]
        body_1 = json.loads(calls[0][1]["body"])
        assert body_1["enabled"] is False

        # Call 2: update engine primary_servers
        assert calls[1][0][0] == "PATCH"
        assert "engines/fpolicy_aws_engine" in calls[1][0][1]
        body_2 = json.loads(calls[1][1]["body"])
        assert body_2["primary_servers"] == ["10.0.2.99"]

        # Call 3: re-enable policy
        assert calls[2][0][0] == "PATCH"
        assert "policies/fpolicy_aws" in calls[2][0][1]
        body_3 = json.loads(calls[2][1]["body"])
        assert body_3["enabled"] is True

    @patch("shared.lambdas.fpolicy_engine.handler.urllib3.PoolManager")
    def test_uses_correct_ontap_base_url(self, mock_pool_cls, mock_context):
        """ONTAP REST API の URL が正しく構築される。"""
        self._setup_secrets()
        mock_pool = MagicMock()
        mock_pool_cls.return_value = mock_pool
        mock_pool.request.return_value = _mock_ontap_response(200)

        from shared.lambdas.fpolicy_engine.handler import handler

        handler(_ecs_task_event(), mock_context)

        first_call_url = mock_pool.request.call_args_list[0][0][1]
        assert "https://10.0.1.100/api/protocols/fpolicy/test-svm-uuid-1234" in first_call_url


@mock_aws
class TestIPUpdaterSkipConditions:
    """イベントフィルタリング: 処理をスキップすべきイベント。"""

    def test_skips_non_running_status(self, mock_context):
        """lastStatus が RUNNING でない場合スキップ。"""
        from shared.lambdas.fpolicy_engine.handler import handler

        event = _ecs_task_event(last_status="STOPPED")
        result = handler(event, mock_context)

        assert result["statusCode"] == 200
        assert "Skipped" in result["body"]

    def test_skips_wrong_cluster(self, mock_context):
        """対象外クラスターのイベントをスキップ。"""
        from shared.lambdas.fpolicy_engine.handler import handler

        event = _ecs_task_event(cluster_arn="arn:aws:ecs:ap-northeast-1:123456789012:cluster/other-cluster")
        result = handler(event, mock_context)

        assert result["statusCode"] == 200
        assert "wrong cluster" in result["body"]

    def test_skips_wrong_service(self, mock_context):
        """対象外サービスのイベントをスキップ。"""
        from shared.lambdas.fpolicy_engine.handler import handler

        event = _ecs_task_event(group="service:other-service")
        result = handler(event, mock_context)

        assert result["statusCode"] == 200
        assert "wrong service" in result["body"]

    def test_skips_desired_status_stopped(self, mock_context):
        """desiredStatus が RUNNING でない場合スキップ。"""
        from shared.lambdas.fpolicy_engine.handler import handler

        event = _ecs_task_event(desired_status="STOPPED")
        result = handler(event, mock_context)

        assert result["statusCode"] == 200
        assert "Skipped" in result["body"]


@mock_aws
class TestIPUpdaterErrors:
    """異常系: ONTAP API 失敗やイベント不備。"""

    def _setup_secrets(self):
        sm = boto3.client("secretsmanager", region_name="ap-northeast-1")
        sm.create_secret(
            Name="ontap-admin-creds",
            SecretString=json.dumps({"username": "admin", "password": "test-pass"}),
        )

    def test_returns_500_when_no_task_ip(self, mock_context):
        """タスク IP が抽出できない場合に 500 を返す。"""
        from shared.lambdas.fpolicy_engine.handler import handler

        event = {
            "detail": {
                "lastStatus": "RUNNING",
                "desiredStatus": "RUNNING",
                "clusterArn": "arn:aws:ecs:ap-northeast-1:123456789012:cluster/fpolicy-cluster",
                "group": "service:fpolicy-service",
                "attachments": [],  # No ENI
            }
        }
        result = handler(event, mock_context)

        assert result["statusCode"] == 500
        assert "no task IP" in result["body"]

    @patch("shared.lambdas.fpolicy_engine.handler.urllib3.PoolManager")
    def test_returns_500_on_engine_update_failure(self, mock_pool_cls, mock_context):
        """engine update が失敗した場合に 500 を返す。"""
        self._setup_secrets()
        mock_pool = MagicMock()
        mock_pool_cls.return_value = mock_pool
        # disable succeeds, engine update fails
        mock_pool.request.side_effect = [
            _mock_ontap_response(200),  # disable
            _mock_ontap_response(500, {"error": {"message": "Internal error"}}),  # update
        ]

        from shared.lambdas.fpolicy_engine.handler import handler

        result = handler(_ecs_task_event(), mock_context)

        assert result["statusCode"] == 500
        assert "Engine update failed" in result["body"]


@mock_aws
class TestIPUpdaterOntapApiExtension:
    """ontap_api アクション（汎用 ONTAP REST API 呼び出し）。"""

    def _setup_secrets(self):
        sm = boto3.client("secretsmanager", region_name="ap-northeast-1")
        sm.create_secret(
            Name="ontap-admin-creds",
            SecretString=json.dumps({"username": "admin", "password": "test-pass"}),
        )

    def test_get_status_action(self, mock_context):
        """get_status アクションが 200 を返す。"""
        from shared.lambdas.fpolicy_engine.handler import handler

        result = handler({"action": "get_status"}, mock_context)
        assert result["statusCode"] == 200

    @patch("shared.lambdas.fpolicy_engine.handler.urllib3.PoolManager")
    def test_ontap_api_allowed_path(self, mock_pool_cls, mock_context):
        """許可されたパスへの ONTAP API 呼び出しが成功する。"""
        self._setup_secrets()
        mock_pool = MagicMock()
        mock_pool_cls.return_value = mock_pool
        mock_pool.request.return_value = _mock_ontap_response(200, {"records": [{"name": "fpolicy_aws"}]})

        from shared.lambdas.fpolicy_engine.handler import handler

        result = handler(
            {
                "action": "ontap_api",
                "method": "GET",
                "path": "/api/protocols/fpolicy/test-svm-uuid/policies",
            },
            mock_context,
        )
        assert result["statusCode"] == 200

    def test_ontap_api_denied_path(self, mock_context):
        """許可されていないパスは 403 を返す。"""
        from shared.lambdas.fpolicy_engine.handler import handler

        result = handler(
            {
                "action": "ontap_api",
                "method": "GET",
                "path": "/api/security/accounts",
            },
            mock_context,
        )
        assert result["statusCode"] == 403
        assert "not allowed" in result["body"]

    def test_ontap_api_delete_denied_by_default(self, mock_context):
        """DELETE メソッドはデフォルトで拒否される。"""
        from shared.lambdas.fpolicy_engine.handler import handler

        result = handler(
            {
                "action": "ontap_api",
                "method": "DELETE",
                "path": "/api/protocols/fpolicy/test-svm-uuid/policies/test",
            },
            mock_context,
        )
        assert result["statusCode"] == 403
        assert "DELETE method not allowed" in result["body"]

    @patch("shared.lambdas.fpolicy_engine.handler.urllib3.PoolManager")
    def test_ontap_api_delete_allowed_when_enabled(self, mock_pool_cls, mock_context, monkeypatch):
        """ONTAP_API_ALLOW_DELETE=true で DELETE が許可される。"""
        self._setup_secrets()
        monkeypatch.setenv("ONTAP_API_ALLOW_DELETE", "true")
        mock_pool = MagicMock()
        mock_pool_cls.return_value = mock_pool
        mock_pool.request.return_value = _mock_ontap_response(200)

        from shared.lambdas.fpolicy_engine.handler import handler

        result = handler(
            {
                "action": "ontap_api",
                "method": "DELETE",
                "path": "/api/protocols/fpolicy/test-svm-uuid/policies/test",
            },
            mock_context,
        )
        assert result["statusCode"] == 200
