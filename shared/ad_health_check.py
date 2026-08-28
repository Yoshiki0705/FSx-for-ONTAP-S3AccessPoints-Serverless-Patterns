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

from shared.ontap_client import OntapClientError

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


def _unreachable_message(svm_label: str, ad_domain: str | None, evidence: str) -> str:
    """DC 到達不能と判定したときのメッセージ。

    Args:
        svm_label: ログとメッセージに出す SVM の表示名。
        ad_domain: AD ドメイン FQDN。
        evidence: そう判定した根拠。応答の形が違っても同じ結論に至るので、
                  どちらで判定したかを残さないと後から切り分けられない。

    Returns:
        str: 障害の内容と、次に確認すべきことを含むメッセージ。
    """
    return (
        f"AD CONNECTIVITY FAILURE: SVM '{svm_label}' (domain: {ad_domain}) "
        f"cannot reach any AD Domain Controllers. {evidence} "
        "S3 AP data operations (ListObjectsV2/GetObject/PutObject) will fail with AccessDenied. "
        "HeadBucket will still succeed (false positive). "
        "Verify: SVM DNS IPs point to active AD DCs, "
        "Security Groups allow ports 53/88/389/445/636 from SVM ENIs to DC IPs."
    )


def _resolve_absent_field_via_cli(
    ontap_client: OntapClient,
    status: AdHealthStatus,
    svm_label: str,
) -> AdHealthStatus:
    """`discovered_servers` が省略されていたとき、CLI で 0 件かどうかを確定する。

    REST がフィールドを省略する理由は 1 つではない。空だから省略されたのか、この
    リリースやこの権限では取得できないのか、応答の形は同じである。private CLI の
    `vserver cifs domain discovered-servers` は件数を `num_records` で返すため、
    「0 件」と「読めなかった」を区別できる。

    CLI 側が失敗した場合は本当に確認不可なので `dc_reachable=None` を返す。診断のために
    足した処理が新しい障害要因になってはいけない。

    Args:
        ontap_client: ONTAP REST API クライアント。
        status: ここまでに埋めた状態。SVM 名とドメインを保持している。
        svm_label: ログとメッセージに出す SVM の表示名。

    Returns:
        AdHealthStatus: 0 件と確定できた場合は `dc_reachable=False`、
        CLI が読めなかった場合は `dc_reachable=None`。
    """
    if svm_label.startswith("uuid="):
        # CLI は vserver を名前で取る。UUID しか分からないまま名前として渡すと、
        # 存在しない vserver に対する 0 件が返り、DC 不在と区別できない結果になる。
        status.dc_reachable = None
        status.message = (
            f"SVM {svm_label} is AD-joined (domain: {status.ad_domain}). "
            "The REST response omitted discovered_servers, and the CLI fallback needs "
            "the SVM name, which was not present in the response. Cannot verify."
        )
        logger.warning(status.message)
        return status

    try:
        cli = ontap_client.get(
            "/private/cli/vserver/cifs/domain/discovered-servers",
            params={"vserver": svm_label},
        )
    except OntapClientError as e:
        status.dc_reachable = None
        status.message = (
            f"SVM '{svm_label}' is AD-joined (domain: {status.ad_domain}). "
            "The REST response omitted discovered_servers, and the CLI fallback that "
            f"would distinguish 'none discovered' from 'not readable' failed: {e}. "
            "Cannot verify DC reachability."
        )
        logger.warning(status.message)
        return status

    num_records = cli.get("num_records")
    if num_records == 0 or (num_records is None and cli.get("records") == []):
        status.dc_reachable = False
        status.discovered_servers = []
        status.message = _unreachable_message(
            svm_label,
            status.ad_domain,
            "The REST field was omitted and the CLI reports 0 discovered servers.",
        )
        logger.error(status.message)
        return status

    # CLI が件数を返したが REST は省略した。DC は検出されているので到達性の問題では
    # ないが、REST と CLI で見えているものが違うため断定はしない。
    status.dc_reachable = None
    status.message = (
        f"SVM '{svm_label}' is AD-joined (domain: {status.ad_domain}). "
        f"The REST response omitted discovered_servers while the CLI reports "
        f"{num_records} server(s), so the two disagree — proceeding without a verdict."
    )
    logger.warning(status.message)
    return status


def _svm_filter(svm_name: str | None, svm_uuid: str | None) -> tuple[dict[str, str], str]:
    """SVM の指定方法を ONTAP のクエリパラメータと表示名に変換する。

    このモジュールは当初 SVM 名しか受け付けなかった。しかしパターン側の Lambda が
    環境変数で持っているのは `SVM_UUID` であり、名前は持っていない。名前しか
    受け付けないままだと、呼び出し側に SVM_NAME を追加する（= 全テンプレート変更）
    以外に統合手段が無くなる。

    実機で確認したところ、`/protocols/cifs/services` と `/protocols/cifs/domains`
    はいずれも `svm.uuid` をフィルタとして受け付け、`svm.name` と同一のレコードを
    返す。したがって UUID をそのまま渡せる。

    Returns:
        (クエリパラメータ, ログ/メッセージ用の表示名)
    """
    if bool(svm_name) == bool(svm_uuid):
        raise ValueError("Specify exactly one of svm_name or svm_uuid")
    if svm_name:
        return {"svm.name": svm_name}, svm_name
    return {"svm.uuid": svm_uuid or ""}, f"uuid={svm_uuid}"


def check_ad_dc_reachability(
    ontap_client: OntapClient,
    svm_name: str | None = None,
    *,
    svm_uuid: str | None = None,
) -> AdHealthStatus:
    """AD DC 到達性チェック

    AD参加SVM の場合、CIFS ドメイン検出状態を確認して
    AD DC が到達可能かを判定する。

    Args:
        ontap_client: ONTAP REST API クライアント
        svm_name: 対象 SVM 名（svm_uuid とどちらか一方を指定）
        svm_uuid: 対象 SVM UUID（svm_name とどちらか一方を指定）。
                  パターン側の Lambda は環境変数 SVM_UUID を持つため、
                  こちらを使えばテンプレート変更なしで呼び出せる。

    Returns:
        AdHealthStatus: チェック結果

    Raises:
        ValueError: svm_name と svm_uuid の指定が 0 個または 2 個の場合
        OntapClientError: ONTAP API 呼び出しに失敗した場合
            (ネットワーク不通、認証エラー等)

    Notes:
        - AD未参加 SVM (CIFS 無効) の場合は即座に
          is_ad_joined=False で返却
        - discovered_servers が None/未返却の場合は
          dc_reachable=None (確認不可) として楽観的に続行
    """
    svm_filter, svm_label = _svm_filter(svm_name, svm_uuid)
    status = AdHealthStatus()

    # Step 1: CIFS サービスの有無を確認 (= AD参加判定)
    logger.info("Checking CIFS service status for SVM '%s'...", svm_label)
    cifs_response = ontap_client.get(
        "/protocols/cifs/services",
        params={**svm_filter, "fields": "enabled,ad_domain.fqdn"},
    )

    cifs_records = cifs_response.get("records", [])

    # UUID で問い合わせた場合、応答に SVM 名が入っている。以降のメッセージは人が
    # 読むものなので、`uuid=...` より名前のほうが役に立つ。
    if svm_uuid and cifs_records:
        resolved = (cifs_records[0].get("svm") or {}).get("name")
        if resolved:
            svm_label = resolved

    if not cifs_records:
        status.is_ad_joined = False
        status.dc_reachable = None
        status.message = f"SVM '{svm_label}' is not AD-joined (no CIFS service). AD DC check skipped."
        logger.info(status.message)
        return status

    cifs_record = cifs_records[0]
    cifs_enabled = cifs_record.get("enabled", False)
    if not cifs_enabled:
        status.is_ad_joined = False
        status.dc_reachable = None
        status.message = f"SVM '{svm_label}' has CIFS service disabled. AD DC check skipped."
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
        status.message = f"SVM '{svm_label}' has CIFS enabled but no AD domain (workgroup mode). AD DC check skipped."
        logger.info(status.message)
        return status

    status.is_ad_joined = True
    logger.info(
        "SVM '%s' is AD-joined (domain: %s). Checking DC reachability...",
        svm_label,
        status.ad_domain,
    )

    # Step 2: CIFS ドメイン検出サーバーを確認
    domains_response = ontap_client.get(
        "/protocols/cifs/domains",
        params={**svm_filter, "fields": "discovered_servers"},
    )

    domain_records = domains_response.get("records", [])
    if not domain_records:
        # ドメインレコード自体が無い — 異常状態だが確認不可として続行
        status.dc_reachable = None
        status.message = (
            f"SVM '{svm_label}' is AD-joined (domain: {status.ad_domain}) "
            "but no CIFS domain records found. Cannot verify DC reachability — proceeding optimistically."
        )
        logger.warning(status.message)
        return status

    discovered = domain_records[0].get("discovered_servers")

    if discovered is None:
        # **フィールドの不在は「確認不可」ではない。**
        #
        # 実測（2026-08-26 / ONTAP 9.18.1P3D1）: `/protocols/cifs/domains` は
        # `discovered_servers` が空のときフィールドごと省略し、`[]` を返さない。
        # `fields=**` でも現れない。フィールド名自体は有効で（存在しないフィールド名は
        # `262197` で拒否されるのに、この名前は拒否されない）、DC が実際に 0 件だった
        # ことは private CLI が `num_records: 0` を返すことで別途確認した。
        #
        # つまり下の `discovered == []` の枝はこのリリースでは到達不能で、DC が 1 台も
        # 検出されていない SVM はすべてここに落ちていた。**このモジュールが検出する
        # ために作られた障害を、確認不可として楽観的に通していた。**
        #
        # フィールドの不在だけでは「空」と「取得できなかった」を区別できないので、
        # 区別できる問い方に切り替える。
        return _resolve_absent_field_via_cli(ontap_client, status, svm_label)

    if discovered == [] or (isinstance(discovered, list) and len(discovered) == 0):
        # 空リスト = DC 到達不能。
        #
        # 9.18.1P3D1 ではフィールドが省略されるためこの枝には入らないが、残してある。
        # 省略はリリースごとの表現の違いであって規約ではないので、`[]` を返すリリースが
        # あればそちらが正しい入口になる。上の CLI 経路と同じ結論に至る 2 つの入口を
        # 別々のメッセージで書くと、どちらで判定したのか後から分からなくなる。
        status.dc_reachable = False
        status.discovered_servers = []
        status.message = _unreachable_message(svm_label, status.ad_domain, "discovered_servers is an empty list.")
        logger.error(status.message)
        return status

    if not isinstance(discovered, list):
        status.dc_reachable = None
        status.discovered_servers = [str(discovered)]
        status.message = (
            f"SVM '{svm_label}' (domain: {status.ad_domain}). "
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
            f"SVM '{svm_label}' (domain: {status.ad_domain}) — AD DC reachable. "
            f"{len(usable)} of {len(discovered)} discovered server(s) are "
            f"{DC_SERVER_TYPE} in state 'ok': {status.discovered_servers}"
        )
        logger.info(status.message)
        return status

    status.dc_reachable = False
    status.message = _unreachable_message(
        svm_label,
        status.ad_domain,
        f"{len(discovered)} server(s) discovered but none is a {DC_SERVER_TYPE} "
        f"in state 'ok': {status.discovered_servers}.",
    )
    logger.error(status.message)
    return status


def require_ad_dc_reachability(
    ontap_client: OntapClient,
    svm_name: str | None = None,
    *,
    svm_uuid: str | None = None,
) -> AdHealthStatus:
    """AD DC 到達性を検証し、到達不能なら例外を投げる

    AD参加SVM で AD DC に到達できない場合、早期に失敗させて
    後続の S3 AP データ操作で AccessDenied になるのを防ぐ。

    ONTAP API 自体が失敗した場合は `OntapClientError` がそのまま伝播する。
    ワークフローの先頭に無条件で挟む用途では `preflight_ad_dc_reachability()`
    を使うこと。

    Args:
        ontap_client: ONTAP REST API クライアント
        svm_name: 対象 SVM 名（svm_uuid とどちらか一方を指定）
        svm_uuid: 対象 SVM UUID（svm_name とどちらか一方を指定）

    Returns:
        AdHealthStatus: 正常時のチェック結果

    Raises:
        AdDcUnreachableError: AD DC に到達不能な場合
        ValueError: svm_name と svm_uuid の指定が 0 個または 2 個の場合
        OntapClientError: ONTAP API 呼び出しに失敗した場合
    """
    status = check_ad_dc_reachability(ontap_client, svm_name, svm_uuid=svm_uuid)

    if not status.is_healthy:
        raise AdDcUnreachableError(
            message=status.message,
            status=status,
            svm_name=svm_name or f"uuid={svm_uuid}",
        )

    return status


def preflight_ad_dc_reachability(
    ontap_client: OntapClient,
    svm_name: str | None = None,
    *,
    svm_uuid: str | None = None,
) -> AdHealthStatus:
    """ワークフロー先頭に無条件で挟める AD DC 到達性チェック

    `require_ad_dc_reachability()` との違いは、チェック自体が実行できなかった
    場合の扱いにある。

    - AD DC に到達できないと**判定できた**場合: `AdDcUnreachableError` を投げる。
      後続の S3 AP データ操作は AccessDenied になるので、ここで落ちたほうが早い。
    - チェック自体が失敗した場合（ONTAP API がタイムアウトした、認証が切れた等）:
      警告ログを残して「確認不可」の status を返し、例外は投げない。

    この 2 つ目が重要。診断のために足した処理が新しい障害要因になってはいけない。
    ONTAP API の一時的な失敗でワークフロー全体を止めるのは、防ごうとしている
    問題より大きい害になる。`require_ad_dc_reachability()` は
    `OntapClientError` をそのまま通すため、そのまま各パターンの先頭に置くと
    まさにそれが起きる。

    Args:
        ontap_client: ONTAP REST API クライアント
        svm_name: 対象 SVM 名（svm_uuid とどちらか一方を指定）
        svm_uuid: 対象 SVM UUID（svm_name とどちらか一方を指定）。
                  パターン側の Lambda は環境変数 SVM_UUID を持つため、
                  こちらを使えばテンプレート変更なしで呼び出せる。

    Returns:
        AdHealthStatus: チェック結果。チェック不可の場合は dc_reachable=None。

    Raises:
        AdDcUnreachableError: AD DC に到達不能と判定できた場合
        ValueError: svm_name と svm_uuid の指定が 0 個または 2 個の場合
    """
    # 指定不正はプログラムの誤りなので、ここは黙って続行してはいけない。
    svm_filter, svm_label = _svm_filter(svm_name, svm_uuid)
    del svm_filter

    try:
        return require_ad_dc_reachability(ontap_client, svm_name, svm_uuid=svm_uuid)
    except AdDcUnreachableError:
        raise
    except OntapClientError as e:
        status = AdHealthStatus(
            dc_reachable=None,
            message=(
                f"AD DC reachability could not be checked for SVM '{svm_label}': {e}. "
                "Proceeding. If a later S3 AP data operation fails with AccessDenied, "
                "the AD domain controllers are the first thing to check."
            ),
        )
        logger.warning(status.message)
        return status
