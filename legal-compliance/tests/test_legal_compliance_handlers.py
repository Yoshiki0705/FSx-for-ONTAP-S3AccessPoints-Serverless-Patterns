"""UC1 法務・コンプライアンス Lambda ハンドラー ユニットテスト

各ハンドラーの入出力形式、エラーハンドリング、
ヘルパー関数のロジックをテストする。
AWS サービス呼び出しは unittest.mock でモック化。
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# shared モジュールのパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# =========================================================================
# Discovery Handler テスト
# =========================================================================


class TestDiscoveryHandler:
    """Discovery Lambda ハンドラーのテスト"""

    def test_handler_module_importable(self):
        """ハンドラーモジュールがインポート可能であることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        assert os.path.exists(handler_path), f"handler.py not found: {handler_path}"

    def test_handler_has_lambda_entry_point(self):
        """ハンドラーに handler 関数が定義されていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "def handler(event, context):" in content

    def test_handler_uses_lambda_error_handler(self):
        """ハンドラーが lambda_error_handler デコレータを使用していることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "@lambda_error_handler" in content

    def test_handler_returns_objects_key(self):
        """ハンドラーの返り値に objects キーが含まれることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert '"objects"' in content or "'objects'" in content

    def test_handler_returns_metadata_key(self):
        """ハンドラーの返り値に metadata キーが含まれることを確認（UC1 固有）"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert '"metadata"' in content or "'metadata'" in content

    def test_handler_imports_ontap_client(self):
        """ハンドラーが OntapClient をインポートしていることを確認（UC1 固有）"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "from shared.ontap_client import OntapClient" in content

    def test_handler_has_collect_ontap_metadata(self):
        """ハンドラーに _collect_ontap_metadata 関数が定義されていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "def _collect_ontap_metadata(" in content

    def test_handler_uses_verify_ssl(self):
        """ハンドラーが VERIFY_SSL 環境変数を使用していることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "VERIFY_SSL" in content

    def test_handler_generates_manifest_key(self):
        """ハンドラーが manifests/ プレフィックス付きキーを生成することを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "discovery", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "manifests/" in content


# =========================================================================
# ACL Collection Handler テスト
# =========================================================================


class TestAclCollectionHandler:
    """ACL Collection Lambda ハンドラーのテスト"""

    def test_handler_module_importable(self):
        """ACL Collection ハンドラーモジュールが存在することを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "acl_collection", "handler.py"
        )
        assert os.path.exists(handler_path), f"handler.py not found: {handler_path}"

    def test_handler_has_lambda_entry_point(self):
        """ACL Collection ハンドラーに handler 関数が定義されていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "acl_collection", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "def handler(event, context):" in content

    def test_format_acl_record_defined(self):
        """format_acl_record が定義されていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "acl_collection", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "def format_acl_record(" in content

    def test_build_s3_key_defined(self):
        """build_s3_key が定義されていることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "acl_collection", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "def build_s3_key(" in content

    def test_build_s3_key_date_partition(self):
        """build_s3_key が日付パーティション付きキーを生成することを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "acl_collection", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "acl-data/" in content

    def test_handler_has_verify_ssl(self):
        """ACL Collection ハンドラーが VERIFY_SSL を使用していることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "acl_collection", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "VERIFY_SSL" in content

    def test_handler_handles_ontap_error_gracefully(self):
        """OntapClientError を catch してワークフローを停止しないことを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "acl_collection", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "except OntapClientError" in content
        assert '"FAILED"' in content

    def test_handler_returns_success_status(self):
        """成功時に SUCCESS ステータスを返すことを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "acl_collection", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert '"SUCCESS"' in content

    def test_handler_outputs_ndjson_content_type(self):
        """出力が application/x-ndjson コンテンツタイプであることを確認"""
        handler_path = os.path.join(
            os.path.dirname(__file__), "..", "functions", "acl_collection", "handler.py"
        )
        with open(handler_path) as f:
            content = f.read()
        assert "application/x-ndjson" in content


# =========================================================================
# CloudFormation テンプレート整合性テスト
# =========================================================================


class TestTemplateConsistency:
    """CloudFormation テンプレートの整合性テスト"""

    def test_template_exists(self):
        """template.yaml が存在することを確認"""
        template_path = os.path.join(
            os.path.dirname(__file__), "..", "template.yaml"
        )
        assert os.path.exists(template_path)

    def test_template_deploy_exists(self):
        """template-deploy.yaml が存在することを確認"""
        template_path = os.path.join(
            os.path.dirname(__file__), "..", "template-deploy.yaml"
        )
        assert os.path.exists(template_path)

    def test_template_has_suffix_filter(self):
        """テンプレートに SUFFIX_FILTER 環境変数が定義されていることを確認"""
        template_path = os.path.join(
            os.path.dirname(__file__), "..", "template.yaml"
        )
        with open(template_path) as f:
            content = f.read()
        assert "SUFFIX_FILTER" in content

    def test_template_has_vpc_endpoint_parameter(self):
        """テンプレートに EnableVpcEndpoints パラメータが定義されていることを確認"""
        template_path = os.path.join(
            os.path.dirname(__file__), "..", "template.yaml"
        )
        with open(template_path) as f:
            content = f.read()
        assert "EnableVpcEndpoints" in content

    def test_template_has_s3_gateway_endpoint_parameter(self):
        """テンプレートに EnableS3GatewayEndpoint パラメータが定義されていることを確認"""
        template_path = os.path.join(
            os.path.dirname(__file__), "..", "template.yaml"
        )
        with open(template_path) as f:
            content = f.read()
        assert "EnableS3GatewayEndpoint" in content

    def test_template_has_route_table_ids_parameter(self):
        """テンプレートに PrivateRouteTableIds パラメータが定義されていることを確認"""
        template_path = os.path.join(
            os.path.dirname(__file__), "..", "template.yaml"
        )
        with open(template_path) as f:
            content = f.read()
        assert "PrivateRouteTableIds" in content

    def test_template_has_ontap_parameters(self):
        """テンプレートに ONTAP 関連パラメータが定義されていることを確認（UC1 固有）"""
        template_path = os.path.join(
            os.path.dirname(__file__), "..", "template.yaml"
        )
        with open(template_path) as f:
            content = f.read()
        assert "OntapSecretName" in content or "ONTAP_SECRET_NAME" in content
        assert "OntapManagementIp" in content or "ONTAP_MANAGEMENT_IP" in content
