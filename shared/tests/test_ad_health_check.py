"""AD DC 到達性チェックモジュールのテスト

shared/ad_health_check.py の check_ad_dc_reachability / require_ad_dc_reachability
の動作を検証する。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from shared.ad_health_check import (
    AdDcUnreachableError,
    AdHealthStatus,
    check_ad_dc_reachability,
    require_ad_dc_reachability,
)


# --- Fixtures ----------------------------------------------------------------


@pytest.fixture
def mock_ontap_client():
    """Mock OntapClient"""
    return MagicMock()


# --- AdHealthStatus Tests ----------------------------------------------------


class TestAdHealthStatus:
    """AdHealthStatus dataclass のプロパティテスト"""

    def test_not_ad_joined_is_healthy(self):
        """AD未参加SVM は常に healthy"""
        status = AdHealthStatus(is_ad_joined=False)
        assert status.is_healthy is True

    def test_ad_joined_dc_reachable_is_healthy(self):
        """AD参加SVM + DC到達可能 → healthy"""
        status = AdHealthStatus(is_ad_joined=True, dc_reachable=True)
        assert status.is_healthy is True

    def test_ad_joined_dc_unreachable_is_not_healthy(self):
        """AD参加SVM + DC到達不能 → unhealthy"""
        status = AdHealthStatus(is_ad_joined=True, dc_reachable=False)
        assert status.is_healthy is False

    def test_ad_joined_dc_unknown_is_healthy(self):
        """AD参加SVM + DC確認不可 → healthy (楽観的続行)"""
        status = AdHealthStatus(is_ad_joined=True, dc_reachable=None)
        assert status.is_healthy is True


# --- check_ad_dc_reachability Tests ------------------------------------------


class TestCheckAdDcReachability:
    """check_ad_dc_reachability 関数のテスト"""

    def test_no_cifs_service(self, mock_ontap_client):
        """CIFS サービスが存在しない SVM → AD未参加"""
        mock_ontap_client.get.return_value = {"records": [], "num_records": 0}

        status = check_ad_dc_reachability(mock_ontap_client, "svm-unix")

        assert status.is_ad_joined is False
        assert status.dc_reachable is None
        assert status.is_healthy is True
        assert "not AD-joined" in status.message

        # CIFS サービスチェックのみ呼ばれる
        mock_ontap_client.get.assert_called_once_with(
            "/protocols/cifs/services",
            params={"svm.name": "svm-unix", "fields": "enabled,ad_domain.fqdn"},
        )

    def test_cifs_disabled(self, mock_ontap_client):
        """CIFS サービスが存在するが disabled → AD未参加扱い"""
        mock_ontap_client.get.return_value = {
            "records": [{"enabled": False, "ad_domain": {"fqdn": "demo.fsx.local"}}],
            "num_records": 1,
        }

        status = check_ad_dc_reachability(mock_ontap_client, "svm-disabled")

        assert status.is_ad_joined is False
        assert status.is_healthy is True
        assert "disabled" in status.message

    def test_ad_joined_dc_reachable(self, mock_ontap_client):
        """AD参加SVM + DC到達可能"""
        mock_ontap_client.get.side_effect = [
            # CIFS services response
            {
                "records": [{"enabled": True, "ad_domain": {"fqdn": "demo.fsx.local"}}],
                "num_records": 1,
            },
            # CIFS domains response — the shape a live cluster returns.
            # Captured from an AD-joined SVM whose S3 AP data operations work: the
            # ms_ldap entries sit at state "undetermined" even when everything is
            # healthy, and only the ms_dc entries reach "ok". The earlier fixture
            # here carried neither field, which is why the check could report
            # "reachable" from a list of servers that were all unusable.
            {
                "records": [
                    {
                        "discovered_servers": [
                            {"server_type": "ms_ldap", "state": "undetermined", "preference": "favored"},
                            {"server_type": "ms_dc", "state": "ok", "preference": "favored"},
                            {"server_type": "ms_ldap", "state": "undetermined", "preference": "favored"},
                            {"server_type": "ms_dc", "state": "ok", "preference": "favored"},
                        ]
                    }
                ],
                "num_records": 1,
            },
        ]

        status = check_ad_dc_reachability(mock_ontap_client, "svm-ad")

        assert status.is_ad_joined is True
        assert status.dc_reachable is True
        assert status.ad_domain == "demo.fsx.local"
        assert len(status.discovered_servers) == 4
        assert status.is_healthy is True
        # The summary must not carry node UUIDs or server IPs into a log line.
        assert status.discovered_servers == [
            "ms_ldap/undetermined",
            "ms_dc/ok",
            "ms_ldap/undetermined",
            "ms_dc/ok",
        ]

    def test_ad_joined_dc_unreachable_empty_list(self, mock_ontap_client):
        """AD参加SVM + discovered_servers が空リスト → DC到達不能"""
        mock_ontap_client.get.side_effect = [
            # CIFS services response
            {
                "records": [{"enabled": True, "ad_domain": {"fqdn": "demo.fsx.local"}}],
                "num_records": 1,
            },
            # CIFS domains response — empty discovered_servers
            {
                "records": [{"discovered_servers": []}],
                "num_records": 1,
            },
        ]

        status = check_ad_dc_reachability(mock_ontap_client, "svm-broken")

        assert status.is_ad_joined is True
        assert status.dc_reachable is False
        assert status.is_healthy is False
        assert "AD CONNECTIVITY FAILURE" in status.message
        assert "AccessDenied" in status.message

    def test_cifs_enabled_without_ad_domain_is_not_ad_joined(self, mock_ontap_client):
        """CIFS 有効 + AD ドメインなし（ワークグループ運用）→ AD未参加として扱う

        検証環境に実在した構成。以前は「CIFS 有効 = AD参加」としていたため
        `is_ad_joined=True, ad_domain=None` という矛盾した結果になり、
        その後の DC チェックも意味を持たなかった。到達すべき DC が存在しない。
        """
        mock_ontap_client.get.side_effect = [
            {
                "records": [{"enabled": True, "ad_domain": None}],
                "num_records": 1,
            },
        ]

        status = check_ad_dc_reachability(mock_ontap_client, "svm-workgroup")

        assert status.is_ad_joined is False
        assert status.ad_domain is None
        assert status.dc_reachable is None
        assert status.is_healthy is True
        assert "workgroup" in status.message
        # ドメイン照会まで進んではいけない（CIFS サービスの 1 回だけ）。
        assert mock_ontap_client.get.call_count == 1

    def test_servers_listed_but_none_usable_is_unreachable(self, mock_ontap_client):
        """DC が列挙されていても ms_dc/ok が無ければ到達不能

        DC が落ちてもエントリ自体は残り得る。空判定だけでは、このチェックが
        検出するために作られた障害そのものを見逃す。
        """
        mock_ontap_client.get.side_effect = [
            {
                "records": [{"enabled": True, "ad_domain": {"fqdn": "demo.fsx.local"}}],
                "num_records": 1,
            },
            {
                "records": [
                    {
                        "discovered_servers": [
                            {"server_type": "ms_ldap", "state": "undetermined"},
                            {"server_type": "ms_dc", "state": "unavailable"},
                        ]
                    }
                ],
                "num_records": 1,
            },
        ]

        status = check_ad_dc_reachability(mock_ontap_client, "svm-degraded")

        assert status.is_ad_joined is True
        assert status.dc_reachable is False
        assert status.is_healthy is False
        assert "AD CONNECTIVITY FAILURE" in status.message
        assert "AccessDenied" in status.message

    def test_ldap_only_at_undetermined_is_not_enough(self, mock_ontap_client):
        """ms_ldap だけが undetermined で並ぶ状態は到達可能とみなさない"""
        mock_ontap_client.get.side_effect = [
            {
                "records": [{"enabled": True, "ad_domain": {"fqdn": "demo.fsx.local"}}],
                "num_records": 1,
            },
            {
                "records": [
                    {
                        "discovered_servers": [
                            {"server_type": "ms_ldap", "state": "undetermined"},
                            {"server_type": "ms_ldap", "state": "undetermined"},
                        ]
                    }
                ],
                "num_records": 1,
            },
        ]

        status = check_ad_dc_reachability(mock_ontap_client, "svm-ldap-only")

        assert status.dc_reachable is False
        assert status.is_healthy is False

    def test_ad_joined_discovered_servers_none(self, mock_ontap_client):
        """AD参加SVM + discovered_servers が None → 確認不可、楽観的続行"""
        mock_ontap_client.get.side_effect = [
            # CIFS services response
            {
                "records": [{"enabled": True, "ad_domain": {"fqdn": "demo.fsx.local"}}],
                "num_records": 1,
            },
            # CIFS domains response — discovered_servers is None
            {
                "records": [{"discovered_servers": None}],
                "num_records": 1,
            },
        ]

        status = check_ad_dc_reachability(mock_ontap_client, "svm-unknown")

        assert status.is_ad_joined is True
        assert status.dc_reachable is None
        assert status.is_healthy is True
        assert "cannot verify" in status.message

    def test_ad_joined_no_domain_records(self, mock_ontap_client):
        """AD参加SVM + ドメインレコードなし → 確認不可、楽観的続行"""
        mock_ontap_client.get.side_effect = [
            # CIFS services response
            {
                "records": [{"enabled": True, "ad_domain": {"fqdn": "demo.fsx.local"}}],
                "num_records": 1,
            },
            # CIFS domains response — no records
            {
                "records": [],
                "num_records": 0,
            },
        ]

        status = check_ad_dc_reachability(mock_ontap_client, "svm-no-domain")

        assert status.is_ad_joined is True
        assert status.dc_reachable is None
        assert status.is_healthy is True
        assert "no CIFS domain records" in status.message


# --- require_ad_dc_reachability Tests ----------------------------------------


class TestRequireAdDcReachability:
    """require_ad_dc_reachability 関数のテスト"""

    def test_healthy_returns_status(self, mock_ontap_client):
        """正常時は AdHealthStatus を返す"""
        mock_ontap_client.get.side_effect = [
            {"records": [{"enabled": True, "ad_domain": {"fqdn": "demo.fsx.local"}}]},
            {"records": [{"discovered_servers": [{"server_type": "ms_dc", "state": "ok"}]}]},
        ]

        status = require_ad_dc_reachability(mock_ontap_client, "svm-ok")

        assert status.is_healthy is True
        assert status.is_ad_joined is True

    def test_not_ad_joined_returns_status(self, mock_ontap_client):
        """AD未参加SVM は正常として返す"""
        mock_ontap_client.get.return_value = {"records": []}

        status = require_ad_dc_reachability(mock_ontap_client, "svm-unix")

        assert status.is_healthy is True
        assert status.is_ad_joined is False

    def test_dc_unreachable_raises(self, mock_ontap_client):
        """DC到達不能時は AdDcUnreachableError を投げる"""
        mock_ontap_client.get.side_effect = [
            {"records": [{"enabled": True, "ad_domain": {"fqdn": "demo.fsx.local"}}]},
            {"records": [{"discovered_servers": []}]},
        ]

        with pytest.raises(AdDcUnreachableError) as exc_info:
            require_ad_dc_reachability(mock_ontap_client, "svm-broken")

        assert exc_info.value.svm_name == "svm-broken"
        assert exc_info.value.status.dc_reachable is False
        assert "AD CONNECTIVITY FAILURE" in str(exc_info.value)

    def test_dc_unknown_does_not_raise(self, mock_ontap_client):
        """DC確認不可時は例外を投げない（楽観的続行）"""
        mock_ontap_client.get.side_effect = [
            {"records": [{"enabled": True, "ad_domain": {"fqdn": "demo.fsx.local"}}]},
            {"records": [{"discovered_servers": None}]},
        ]

        status = require_ad_dc_reachability(mock_ontap_client, "svm-unknown")

        assert status.is_healthy is True
        assert status.dc_reachable is None
