"""AD DC 到達性チェックモジュール

AD参加SVM（CIFS有効）上で S3 Access Point データ操作を実行する前に、
AD Domain Controller への接続性を検証する。

背景:
- AD参加SVM では、S3 AP データ操作（ListObjectsV2/GetObject/PutObject）ごとに
  ONTAP が unix→win reverse name-mapping lookup を実行する
- AD DC が到達不能な場合、HeadBucket は成功するがデータ操作は全て AccessDenied
- IAM/ポリシー/ネットワーク層は全て正常なため、診断が非常に困難

使用パターン:
    from shared.ad_health_check import check_ad_dc_reachability, AdHealthStatus

    status = check_ad_dc_reachability(ontap_client, svm_name="svm1")
    if status.is_ad_joined and not status.dc_reachable:
        raise RuntimeError(f"AD DC unreachable: {status.message}")

検証済み環境: fsxn-observability-integrations (restore-verification workflow)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.ontap_client import OntapClient

logger = logging.getLogger(__name__)

# `/protocols/cifs/domains` の discovered_servers は server_type ごとにエントリを返す。
# Kerberos / 認証の到達性を示すのは ms_dc のエントリで、ms_ldap は健全な SVM でも
# state が undetermined のままになる（実機で確認）。
DC_SERVER_TYPE = "ms_dc"


def _describe_server(server: object) -> str:
    """discovered_servers の 1 エントリを、ログに載せて安全な短い文字列にする。

    生の dict をそのままメッセージに入れるとノード UUID やサーバー IP まで含まれる。
    障害の切り分けに必要なのは種別と状態なので、そこだけを残す。
    """
    if not isinstance(server, dict):
        return str(server)
    return "{}/{}".format(server.get("server_type", "unknown"), server.get("state", "unknown"))


@dataclass
class AdHealthStatus:
    """AD DC 到達性チェック結果

    Attributes:
        is_ad_joined: SVM が AD に参加しているか (CIFS 有効)
        dc_reachable: AD DC に到達可能か (None = 確認不可)
        ad_domain: AD ドメイン FQDN (AD参加時のみ)
        discovered_servers: 検出された DC サーバーリスト
        message: 人間向けステータスメッセージ
    """

    is_ad_joined: bool = False
    dc_reachable: bool | None = None
    ad_domain: str | None = None
    discovered_servers: list[str] = field(default_factory=list)
    message: str = ""

    @property
    def is_healthy(self) -> bool:
        """S3 AP データ操作が成功可能な状態か

        - AD未参加 SVM: 常に True (AD DC 不要)
        - AD参加 SVM: DC 到達可能時のみ True
        - 確認不可 (dc_reachable=None): True (楽観的続行)
        """
        if not self.is_ad_joined:
            return True
        if self.dc_reachable is None:
            return True  # 確認不可 — 楽観的に続行
        return self.dc_reachable


class AdDcUnreachableError(Exception):
    """AD DC 到達不能エラー

    AD参加SVM で AD DC に到達できないため、S3 AP データ操作が
    AccessDenied で失敗する状態。

    Attributes:
        status: AdHealthStatus — 詳細なチェック結果
        svm_name: 対象 SVM 名
    """

    def __init__(self, message: str, status: AdHealthStatus, svm_name: str):
        super().__init__(message)
        self.status = status
        self.svm_name = svm_name


def check_ad_dc_reachability(
    ontap_client: OntapClient,
    svm_name: str,
) -> AdHealthStatus:
    """AD DC 到達性チェック

    AD参加SVM の場合、CIFS ドメイン検出状態を確認して
    AD DC が到達可能かを判定する。

    Args:
        ontap_client: ONTAP REST API クライアント
        svm_name: 対象 SVM 名

    Returns:
        AdHealthStatus: チェック結果

    Raises:
        OntapClientError: ONTAP API 呼び出しに失敗した場合
            (ネットワーク不通、認証エラー等)

    Notes:
        - AD未参加 SVM (CIFS 無効) の場合は即座に
          is_ad_joined=False で返却
        - discovered_servers が None/未返却の場合は
          dc_reachable=None (確認不可) として楽観的に続行
    """
    status = AdHealthStatus()

    # Step 1: CIFS サービスの有無を確認 (= AD参加判定)
    logger.info("Checking CIFS service status for SVM '%s'...", svm_name)
    cifs_response = ontap_client.get(
        "/protocols/cifs/services",
        params={"svm.name": svm_name, "fields": "enabled,ad_domain.fqdn"},
    )

    cifs_records = cifs_response.get("records", [])
    if not cifs_records:
        status.is_ad_joined = False
        status.dc_reachable = None
        status.message = f"SVM '{svm_name}' is not AD-joined (no CIFS service). AD DC check skipped."
        logger.info(status.message)
        return status

    cifs_record = cifs_records[0]
    cifs_enabled = cifs_record.get("enabled", False)
    if not cifs_enabled:
        status.is_ad_joined = False
        status.dc_reachable = None
        status.message = f"SVM '{svm_name}' has CIFS service disabled. AD DC check skipped."
        logger.info(status.message)
        return status

    # CIFS 有効 かつ ad_domain.fqdn あり = AD参加
    #
    # CIFS が有効でも AD ドメインを持たない SVM が実在する（ワークグループ運用）。
    # 検証環境の 1 台がまさにこの状態で、以前の「CIFS 有効 = AD参加」判定は
    # `is_ad_joined=True, ad_domain=None` という矛盾した結果を返し、
    # その後の DC チェックも無意味になっていた。到達すべき DC が無いので、
    # ここは AD未参加として扱うのが正しい。
    ad_domain_info = cifs_record.get("ad_domain") or {}
    status.ad_domain = ad_domain_info.get("fqdn")
    if not status.ad_domain:
        status.is_ad_joined = False
        status.dc_reachable = None
        status.message = f"SVM '{svm_name}' has CIFS enabled but no AD domain (workgroup mode). AD DC check skipped."
        logger.info(status.message)
        return status

    status.is_ad_joined = True
    logger.info(
        "SVM '%s' is AD-joined (domain: %s). Checking DC reachability...",
        svm_name,
        status.ad_domain,
    )

    # Step 2: CIFS ドメイン検出サーバーを確認
    domains_response = ontap_client.get(
        "/protocols/cifs/domains",
        params={"svm.name": svm_name, "fields": "discovered_servers"},
    )

    domain_records = domains_response.get("records", [])
    if not domain_records:
        # ドメインレコード自体が無い — 異常状態だが確認不可として続行
        status.dc_reachable = None
        status.message = (
            f"SVM '{svm_name}' is AD-joined (domain: {status.ad_domain}) "
            "but no CIFS domain records found. Cannot verify DC reachability — proceeding optimistically."
        )
        logger.warning(status.message)
        return status

    discovered = domain_records[0].get("discovered_servers")

    if discovered is None:
        # フィールド自体が返されない場合 — 確認不可として続行
        status.dc_reachable = None
        status.message = (
            f"SVM '{svm_name}' is AD-joined (domain: {status.ad_domain}). "
            "discovered_servers field not available — cannot verify DC reachability."
        )
        logger.warning(status.message)
        return status

    if discovered == [] or (isinstance(discovered, list) and len(discovered) == 0):
        # 空リスト = DC 到達不能
        status.dc_reachable = False
        status.discovered_servers = []
        status.message = (
            f"AD CONNECTIVITY FAILURE: SVM '{svm_name}' (domain: {status.ad_domain}) "
            "cannot reach any AD Domain Controllers. discovered_servers is empty. "
            "S3 AP data operations (ListObjectsV2/GetObject/PutObject) will fail with AccessDenied. "
            "HeadBucket will still succeed (false positive). "
            "Verify: SVM DNS IPs point to active AD DCs, "
            "Security Groups allow ports 53/88/389/445/636 from SVM ENIs to DC IPs."
        )
        logger.error(status.message)
        return status

    if not isinstance(discovered, list):
        status.dc_reachable = None
        status.discovered_servers = [str(discovered)]
        status.message = (
            f"SVM '{svm_name}' (domain: {status.ad_domain}). "
            f"discovered_servers was not a list ({type(discovered).__name__}) — "
            "cannot verify DC reachability."
        )
        logger.warning(status.message)
        return status

    # 各エントリの state を見る。
    #
    # 以前はリストが空でなければ到達可能としていた。実機データはそれが不十分だと
    # 示している: 健全な SVM でも `ms_ldap` のエントリは `state: undetermined` で、
    # 到達性を示しているのは `ms_dc` かつ `state: ok` のエントリだけだった。
    # DC が落ちてもエントリ自体は残り得るため、空判定だけではこのチェックが
    # 検出するために作られた障害そのものを見逃す。
    #
    # 逆に「全エントリが ok」を要求するのも誤り。健全な状態で ms_ldap が
    # undetermined なので、それでは常に到達不能と判定してしまう。
    status.discovered_servers = [_describe_server(s) for s in discovered]
    usable = [
        s
        for s in discovered
        if isinstance(s, dict) and s.get("server_type") == DC_SERVER_TYPE and s.get("state") == "ok"
    ]

    if usable:
        status.dc_reachable = True
        status.message = (
            f"SVM '{svm_name}' (domain: {status.ad_domain}) — AD DC reachable. "
            f"{len(usable)} of {len(discovered)} discovered server(s) are "
            f"{DC_SERVER_TYPE} in state 'ok': {status.discovered_servers}"
        )
        logger.info(status.message)
        return status

    status.dc_reachable = False
    status.message = (
        f"AD CONNECTIVITY FAILURE: SVM '{svm_name}' (domain: {status.ad_domain}) "
        f"has {len(discovered)} discovered server(s) but none is a {DC_SERVER_TYPE} "
        f"in state 'ok': {status.discovered_servers}. "
        "S3 AP data operations (ListObjectsV2/GetObject/PutObject) will fail with AccessDenied. "
        "HeadBucket will still succeed (false positive). "
        "Verify: SVM DNS IPs point to active AD DCs, "
        "Security Groups allow ports 53/88/389/445/636 from SVM ENIs to DC IPs."
    )
    logger.error(status.message)
    return status


def require_ad_dc_reachability(
    ontap_client: OntapClient,
    svm_name: str,
) -> AdHealthStatus:
    """AD DC 到達性を検証し、到達不能なら例外を投げる

    Step Functions ワークフローの先頭で使用する。
    AD参加SVM で AD DC に到達できない場合、早期に失敗させて
    後続の S3 AP データ操作で AccessDenied になるのを防ぐ。

    Args:
        ontap_client: ONTAP REST API クライアント
        svm_name: 対象 SVM 名

    Returns:
        AdHealthStatus: 正常時のチェック結果

    Raises:
        AdDcUnreachableError: AD DC に到達不能な場合
        OntapClientError: ONTAP API 呼び出しに失敗した場合
    """
    status = check_ad_dc_reachability(ontap_client, svm_name)

    if not status.is_healthy:
        raise AdDcUnreachableError(
            message=status.message,
            status=status,
            svm_name=svm_name,
        )

    return status
