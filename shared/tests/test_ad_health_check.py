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
    preflight_ad_dc_reachability,
    require_ad_dc_reachability,
)
from shared.ontap_client import OntapClientError


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


# --- SVM を UUID で指定する ---------------------------------------------------


def _healthy_responses():
    """AD 参加 + DC 到達可能な SVM の応答を返す side_effect を作る"""

    def side_effect(path, params=None):
        if path == "/protocols/cifs/services":
            return {
                "records": [
                    {
                        "svm": {"name": "svm-from-response", "uuid": "u-1"},
                        "enabled": True,
                        "ad_domain": {"fqdn": "EXAMPLE.LOCAL"},
                    }
                ]
            }
        return {
            "records": [
                {
                    "discovered_servers": [
                        {"server_type": "ms_ldap", "state": "undetermined"},
                        {"server_type": "ms_dc", "state": "ok"},
                    ]
                }
            ]
        }

    return side_effect


class TestSvmIdentification:
    """svm_name / svm_uuid のどちらでも呼べることを検証する

    パターン側の Lambda が環境変数で持っているのは SVM_UUID であり名前ではない。
    名前しか受け付けないままだと、全テンプレートに SVM_NAME を追加しない限り
    このチェックを組み込めなかった。

    ONTAP の `/protocols/cifs/services` と `/protocols/cifs/domains` はいずれも
    `svm.uuid` をフィルタとして受け付ける（実機で確認済み）。
    """

    def test_uuid_is_sent_as_svm_uuid_filter(self, mock_ontap_client):
        """svm_uuid 指定時は svm.uuid でクエリすることを検証する"""
        mock_ontap_client.get.side_effect = _healthy_responses()

        check_ad_dc_reachability(mock_ontap_client, svm_uuid="u-1")

        for call in mock_ontap_client.get.call_args_list:
            params = call.kwargs["params"]
            assert params.get("svm.uuid") == "u-1"
            assert "svm.name" not in params

    def test_name_is_sent_as_svm_name_filter(self, mock_ontap_client):
        """svm_name 指定時は svm.name でクエリすることを検証する"""
        mock_ontap_client.get.side_effect = _healthy_responses()

        check_ad_dc_reachability(mock_ontap_client, "svm-a")

        for call in mock_ontap_client.get.call_args_list:
            params = call.kwargs["params"]
            assert params.get("svm.name") == "svm-a"
            assert "svm.uuid" not in params

    def test_uuid_query_uses_resolved_name_in_message(self, mock_ontap_client):
        """UUID 指定時は応答の SVM 名をメッセージに使うことを検証する

        メッセージは人が読むものなので、`uuid=...` より名前のほうが有用。
        """
        mock_ontap_client.get.side_effect = _healthy_responses()

        status = check_ad_dc_reachability(mock_ontap_client, svm_uuid="u-1")

        assert "svm-from-response" in status.message
        assert "uuid=u-1" not in status.message

    def test_uuid_falls_back_to_uuid_label_when_no_records(self, mock_ontap_client):
        """レコードが無ければ UUID をそのまま表示に使うことを検証する"""
        mock_ontap_client.get.return_value = {"records": []}

        status = check_ad_dc_reachability(mock_ontap_client, svm_uuid="u-9")

        assert "uuid=u-9" in status.message

    @pytest.mark.parametrize(
        "args,kwargs",
        [
            ((), {}),
            (("svm-a",), {"svm_uuid": "u-1"}),
            ((None,), {"svm_uuid": None}),
        ],
        ids=["neither", "both", "both-none"],
    )
    def test_rejects_ambiguous_identification(self, mock_ontap_client, args, kwargs):
        """名前と UUID の指定が 0 個/2 個なら ValueError を投げることを検証する"""
        with pytest.raises(ValueError, match="exactly one"):
            check_ad_dc_reachability(mock_ontap_client, *args, **kwargs)

    def test_require_accepts_uuid(self, mock_ontap_client):
        """require_ad_dc_reachability も UUID で呼べることを検証する"""
        mock_ontap_client.get.side_effect = _healthy_responses()

        status = require_ad_dc_reachability(mock_ontap_client, svm_uuid="u-1")

        assert status.dc_reachable is True

    def test_require_error_carries_uuid_label(self, mock_ontap_client):
        """UUID 指定で到達不能なら例外の svm_name に UUID 表記が入ることを検証する"""

        def side_effect(path, params=None):
            if path == "/protocols/cifs/services":
                return {
                    "records": [
                        {"enabled": True, "ad_domain": {"fqdn": "EXAMPLE.LOCAL"}},
                    ]
                }
            return {"records": [{"discovered_servers": []}]}

        mock_ontap_client.get.side_effect = side_effect

        with pytest.raises(AdDcUnreachableError) as exc_info:
            require_ad_dc_reachability(mock_ontap_client, svm_uuid="u-7")

        assert exc_info.value.svm_name == "uuid=u-7"


# --- preflight_ad_dc_reachability --------------------------------------------


class TestPreflightAdDcReachability:
    """ワークフロー先頭に無条件で置ける版のテスト

    require_ad_dc_reachability との違いは、チェック自体が失敗したときの扱い。
    診断のために足した処理が新しい障害要因になってはいけない。
    """

    def test_raises_when_dc_definitively_unreachable(self, mock_ontap_client):
        """DC 到達不能と判定できた場合は例外を投げることを検証する"""

        def side_effect(path, params=None):
            if path == "/protocols/cifs/services":
                return {"records": [{"enabled": True, "ad_domain": {"fqdn": "EXAMPLE.LOCAL"}}]}
            return {"records": [{"discovered_servers": []}]}

        mock_ontap_client.get.side_effect = side_effect

        with pytest.raises(AdDcUnreachableError):
            preflight_ad_dc_reachability(mock_ontap_client, svm_uuid="u-1")

    def test_does_not_raise_when_check_itself_fails(self, mock_ontap_client):
        """ONTAP API が失敗しても例外を投げないことを検証する

        これがこの関数の存在理由。ONTAP API の一時的な失敗でワークフロー全体を
        止めるのは、防ごうとしている問題より大きい害になる。
        """
        mock_ontap_client.get.side_effect = OntapClientError("connection timed out")

        status = preflight_ad_dc_reachability(mock_ontap_client, svm_uuid="u-1")

        assert status.dc_reachable is None
        assert status.is_healthy is True
        assert "could not be checked" in status.message
        # 後続で AccessDenied が出たときの手がかりを残す
        assert "AccessDenied" in status.message

    def test_passes_through_for_non_ad_joined_svm(self, mock_ontap_client):
        """AD 未参加 SVM では何も止めないことを検証する"""
        mock_ontap_client.get.return_value = {"records": []}

        status = preflight_ad_dc_reachability(mock_ontap_client, svm_uuid="u-1")

        assert status.is_ad_joined is False
        assert status.is_healthy is True

    def test_returns_healthy_status_when_reachable(self, mock_ontap_client):
        """DC 到達可能なら健全な status を返すことを検証する"""
        mock_ontap_client.get.side_effect = _healthy_responses()

        status = preflight_ad_dc_reachability(mock_ontap_client, svm_uuid="u-1")

        assert status.dc_reachable is True
        assert status.is_ad_joined is True

    def test_rejects_ambiguous_identification(self, mock_ontap_client):
        """指定不正はプログラムの誤りなので黙って続行しないことを検証する"""
        with pytest.raises(ValueError, match="exactly one"):
            preflight_ad_dc_reachability(mock_ontap_client)

        mock_ontap_client.get.assert_not_called()
