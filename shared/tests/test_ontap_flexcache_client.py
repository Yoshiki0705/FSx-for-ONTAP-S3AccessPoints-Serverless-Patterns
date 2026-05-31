"""FlexCache 操作のユニットテスト"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from shared.ontap_client import OntapClient, OntapClientConfig, OntapClientError


@pytest.fixture
def mock_client():
    """モック OntapClient を作成"""
    config = OntapClientConfig(
        management_ip="10.0.0.1",
        secret_name="test/secret",
        verify_ssl=False,
    )
    client = OntapClient(config)
    # 認証情報をモック
    client._credentials = {"username": "admin", "password": "test"}
    return client


class TestListFlexcaches:
    """list_flexcaches のテスト"""

    def test_list_all(self, mock_client):
        """全 FlexCache 一覧取得"""
        mock_response = {
            "records": [
                {"name": "cache1", "uuid": "uuid-1", "svm": {"name": "svm1"}},
                {"name": "cache2", "uuid": "uuid-2", "svm": {"name": "svm1"}},
            ]
        }
        with patch.object(mock_client, "get", return_value=mock_response):
            result = mock_client.list_flexcaches()
            assert len(result) == 2
            assert result[0]["name"] == "cache1"

    def test_list_by_name(self, mock_client):
        """名前フィルタ"""
        mock_response = {
            "records": [
                {"name": "cache1", "uuid": "uuid-1"},
            ]
        }
        with patch.object(mock_client, "get", return_value=mock_response) as mock_get:
            result = mock_client.list_flexcaches(name="cache1")
            assert len(result) == 1
            call_args = mock_get.call_args
            assert call_args[1]["params"]["name"] == "cache1"

    def test_list_by_svm(self, mock_client):
        """SVM フィルタ"""
        mock_response = {"records": []}
        with patch.object(mock_client, "get", return_value=mock_response) as mock_get:
            mock_client.list_flexcaches(svm_name="svm1")
            call_args = mock_get.call_args
            assert call_args[1]["params"]["svm.name"] == "svm1"


class TestCreateFlexcache:
    """create_flexcache のテスト"""

    def test_create_basic(self, mock_client):
        """基本的な FlexCache 作成"""
        mock_response = {"job": {"uuid": "job-uuid-1"}}
        with patch.object(mock_client, "post", return_value=mock_response) as mock_post:
            result = mock_client.create_flexcache(
                name="test_cache",
                svm_name="svm1",
                origin_volume="origin_vol",
                origin_svm="svm1",
                size_gb=100,
            )
            assert result["job"]["uuid"] == "job-uuid-1"
            call_args = mock_post.call_args
            body = call_args[1]["body"]
            assert body["name"] == "test_cache"
            assert body["svm"]["name"] == "svm1"
            assert body["size"] == 100 * 1024 * 1024 * 1024
            assert body["path"] == "/test_cache"

    def test_create_with_junction_path(self, mock_client):
        """カスタムジャンクションパス"""
        mock_response = {"job": {"uuid": "job-uuid-2"}}
        with patch.object(mock_client, "post", return_value=mock_response) as mock_post:
            mock_client.create_flexcache(
                name="test_cache",
                svm_name="svm1",
                origin_volume="origin_vol",
                origin_svm="svm1",
                size_gb=200,
                junction_path="/custom/path",
            )
            body = mock_post.call_args[1]["body"]
            assert body["path"] == "/custom/path"

    def test_create_with_prepopulate(self, mock_client):
        """Prepopulate 付き作成"""
        mock_response = {"job": {"uuid": "job-uuid-3"}}
        with patch.object(mock_client, "post", return_value=mock_response) as mock_post:
            mock_client.create_flexcache(
                name="test_cache",
                svm_name="svm1",
                origin_volume="origin_vol",
                origin_svm="svm1",
                size_gb=100,
                prepopulate_dir_paths=["/data/hot/", "/tools/"],
            )
            body = mock_post.call_args[1]["body"]
            assert body["prepopulate"]["dir_paths"] == ["/data/hot/", "/tools/"]

    def test_create_with_aggregate(self, mock_client):
        """アグリゲート指定"""
        mock_response = {"job": {"uuid": "job-uuid-4"}}
        with patch.object(mock_client, "post", return_value=mock_response) as mock_post:
            mock_client.create_flexcache(
                name="test_cache",
                svm_name="svm1",
                origin_volume="origin_vol",
                origin_svm="svm1",
                size_gb=100,
                aggregate_name="aggr1",
            )
            body = mock_post.call_args[1]["body"]
            assert body["aggregates"] == [{"name": "aggr1"}]


class TestDeleteFlexcache:
    """delete_flexcache のテスト"""

    def test_delete_success(self, mock_client):
        """正常削除"""
        mock_response = {"job": {"uuid": "delete-job-1"}}
        with patch.object(mock_client, "delete", return_value=mock_response):
            result = mock_client.delete_flexcache(uuid="uuid-to-delete")
            assert result["job"]["uuid"] == "delete-job-1"

    def test_delete_not_found(self, mock_client):
        """存在しない FlexCache の削除"""
        with patch.object(
            mock_client, "delete",
            side_effect=OntapClientError("Not found", status_code=404),
        ):
            with pytest.raises(OntapClientError) as exc_info:
                mock_client.delete_flexcache(uuid="nonexistent")
            assert exc_info.value.status_code == 404


class TestPrepopulateFlexcache:
    """prepopulate_flexcache のテスト"""

    def test_prepopulate_basic(self, mock_client):
        """基本的な Prepopulate"""
        mock_response = {"job": {"uuid": "prepop-job-1"}}
        with patch.object(mock_client, "patch", return_value=mock_response) as mock_patch:
            result = mock_client.prepopulate_flexcache(
                uuid="cache-uuid-1",
                dir_paths=["/data/hot/"],
            )
            assert result["job"]["uuid"] == "prepop-job-1"
            call_args = mock_patch.call_args
            body = call_args[1]["body"]
            assert body["prepopulate"]["dir_paths"] == ["/data/hot/"]

    def test_prepopulate_with_exclude(self, mock_client):
        """除外パス付き Prepopulate"""
        mock_response = {"job": {"uuid": "prepop-job-2"}}
        with patch.object(mock_client, "patch", return_value=mock_response) as mock_patch:
            mock_client.prepopulate_flexcache(
                uuid="cache-uuid-1",
                dir_paths=["/data/"],
                exclude_dir_paths=["/data/temp/"],
            )
            body = mock_patch.call_args[1]["body"]
            assert body["prepopulate"]["exclude_dir_paths"] == ["/data/temp/"]


class TestWaitOntapJob:
    """wait_ontap_job のテスト"""

    def test_job_success(self, mock_client):
        """ジョブ成功"""
        mock_response = {"state": "success", "uuid": "job-1"}
        with patch.object(mock_client, "get", return_value=mock_response):
            result = mock_client.wait_ontap_job("job-1", timeout_seconds=10)
            assert result["state"] == "success"

    def test_job_failure(self, mock_client):
        """ジョブ失敗"""
        mock_response = {"state": "failure", "uuid": "job-2", "message": "Disk full"}
        with patch.object(mock_client, "get", return_value=mock_response):
            with pytest.raises(OntapClientError) as exc_info:
                mock_client.wait_ontap_job("job-2", timeout_seconds=10)
            assert "Disk full" in str(exc_info.value)

    def test_job_timeout(self, mock_client):
        """ジョブタイムアウト"""
        mock_response = {"state": "running", "uuid": "job-3"}
        with patch.object(mock_client, "get", return_value=mock_response):
            with pytest.raises(OntapClientError) as exc_info:
                mock_client.wait_ontap_job("job-3", timeout_seconds=1, poll_interval=0.1)
            assert "timed out" in str(exc_info.value)
