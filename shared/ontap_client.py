"""ONTAP REST API クライアント

FSx for NetApp ONTAP の REST API を呼び出す共通 Python クライアント。
Secrets Manager 認証、urllib3 PoolManager、TLS 検証、リトライ機能を備える。

既存リポジトリ FSx-for-ONTAP-Agentic-Access-Aware-RAG の検証済みパターンを
Python で再実装したもの。

Key patterns preserved:
- Secrets Manager authentication
- urllib3 PoolManager with TLS verification (default enabled)
- urllib3.Timeout(connect=10.0, read=30.0)
- urllib3.Retry(total=3, backoff_factor=0.5)
- OntapClientError exception class (status_code, response_body attributes)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import boto3
import urllib3

logger = logging.getLogger(__name__)

# Caller-supplied names reach request paths: a share name, a volume name, a
# relationship UUID. A value carrying a `..` segment redirects the request to a
# different endpoint, so a "delete this share" call can arrive at a cluster
# resource instead. Callers are expected to percent-encode each segment, but the
# check belongs here as well rather than in every call site — the portal handler
# learned this the same way and put it in the one function all its requests go
# through.
_UNSAFE_PATH_CHARS = re.compile(r"[\x00-\x1f\x7f\\]")


def is_unsafe_path(path: str) -> bool:
    """True if an assembled request path must not be sent.

    A `..` inside a name is fine ("my..share"); a whole segment of `..` is not.
    The query string is excluded from the traversal check because a value there
    cannot change which endpoint is addressed.
    """
    if _UNSAFE_PATH_CHARS.search(path):
        return True
    route = path.split("?", 1)[0]
    return any(segment == ".." for segment in route.split("/"))


class OntapClientError(Exception):
    """ONTAP REST API エラー"""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body

    @property
    def ontap_message(self) -> str:
        """The message ONTAP returned, or this exception's own message.

        ONTAP reports failures as {"error": {"message": ..., "code": ...}}. Callers
        that surface errors to a person want that text, not the HTTP status line.
        """
        if self.response_body:
            try:
                parsed = json.loads(self.response_body)
            except (json.JSONDecodeError, TypeError):
                parsed = None
            if isinstance(parsed, dict):
                message = parsed.get("error", {})
                if isinstance(message, dict) and message.get("message"):
                    return str(message["message"])
        return str(self)


class OntapClientConfig:
    """OntapClient 設定データクラス

    Attributes:
        management_ip: ONTAP クラスタ管理 IP アドレス
        secret_name: Secrets Manager のシークレット名
        verify_ssl: TLS 検証の有効/無効 (デフォルト: True)
        ca_cert_path: CA 証明書ファイルパス (オプション)
        connect_timeout: 接続タイムアウト秒数 (デフォルト: 10.0)
        read_timeout: 読み取りタイムアウト秒数 (デフォルト: 30.0)
        retry_total: リトライ回数 (デフォルト: 3)
        backoff_factor: リトライバックオフ係数 (デフォルト: 0.5)
    """

    def __init__(
        self,
        management_ip: str,
        secret_name: str,
        verify_ssl: bool = True,
        ca_cert_path: str | None = None,
        connect_timeout: float = 10.0,
        read_timeout: float = 30.0,
        retry_total: int = 3,
        backoff_factor: float = 0.5,
    ):
        self.management_ip = management_ip
        self.secret_name = secret_name
        self.verify_ssl = verify_ssl
        self.ca_cert_path = ca_cert_path
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.retry_total = retry_total
        self.backoff_factor = backoff_factor

    def to_dict(self) -> dict:
        """設定を辞書に変換"""
        return {
            "management_ip": self.management_ip,
            "secret_name": self.secret_name,
            "verify_ssl": self.verify_ssl,
            "ca_cert_path": self.ca_cert_path,
            "connect_timeout": self.connect_timeout,
            "read_timeout": self.read_timeout,
            "retry_total": self.retry_total,
            "backoff_factor": self.backoff_factor,
        }

    @classmethod
    def from_dict(cls, data: dict) -> OntapClientConfig:
        """辞書から設定を復元"""
        return cls(**data)


class OntapClient:
    """ONTAP REST API クライアント

    Secrets Manager から認証情報を取得し、urllib3 PoolManager を使用して
    ONTAP REST API を呼び出す。TLS 検証、タイムアウト、リトライを設定可能。

    Usage:
        config = OntapClientConfig(
            management_ip="10.0.0.1",
            secret_name="fsxn/ontap-credentials",
        )
        client = OntapClient(config)
        volumes = client.list_volumes()
    """

    BASE_API_PATH = "/api"

    def __init__(
        self,
        config: OntapClientConfig,
        session: boto3.Session | None = None,
    ):
        self._config = config
        self._session = session or boto3.Session()
        self._pool: urllib3.PoolManager | None = None
        self._credentials: dict | None = None

    def _get_credentials(self) -> dict:
        """Secrets Manager から認証情報を取得

        Returns:
            dict: {"username": str, "password": str}

        Raises:
            OntapClientError: Secrets Manager からの取得に失敗した場合
        """
        if self._credentials is not None:
            return self._credentials

        try:
            sm_client = self._session.client("secretsmanager")
            response = sm_client.get_secret_value(
                SecretId=self._config.secret_name,
            )
            self._credentials = json.loads(response["SecretString"])
            return self._credentials
        except Exception as e:
            raise OntapClientError(
                f"Failed to retrieve credentials from Secrets Manager (secret: {self._config.secret_name}): {e}"
            ) from e

    def _get_pool(self) -> urllib3.PoolManager:
        """urllib3 PoolManager を初期化（TLS 検証、タイムアウト、リトライ設定）

        Returns:
            urllib3.PoolManager: 設定済みの PoolManager

        Notes:
            - verify_ssl=True (デフォルト): TLS 検証有効
            - verify_ssl=False: TLS 検証無効（lab/PoC 用途のみ、警告ログ出力）
            - ca_cert_path: カスタム CA 証明書パス
        """
        if self._pool is not None:
            return self._pool

        timeout = urllib3.Timeout(
            connect=self._config.connect_timeout,
            read=self._config.read_timeout,
        )
        retry = urllib3.Retry(
            total=self._config.retry_total,
            backoff_factor=self._config.backoff_factor,
        )

        if self._config.verify_ssl:
            if self._config.ca_cert_path:
                self._pool = urllib3.PoolManager(
                    timeout=timeout,
                    retries=retry,
                    cert_reqs="CERT_REQUIRED",
                    ca_certs=self._config.ca_cert_path,
                )
            else:
                self._pool = urllib3.PoolManager(
                    timeout=timeout,
                    retries=retry,
                    cert_reqs="CERT_REQUIRED",
                )
        else:
            logger.warning(
                "TLS verification is disabled. "
                "This should only be used for lab/PoC environments. "
                "Set verify_ssl=True for production use."
            )
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            self._pool = urllib3.PoolManager(
                timeout=timeout,
                retries=retry,
                cert_reqs="CERT_NONE",
            )

        return self._pool

    def _make_headers(self) -> dict:
        """認証ヘッダーを生成"""
        creds = self._get_credentials()
        return urllib3.make_headers(
            basic_auth=f"{creds['username']}:{creds['password']}",
        )

    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        body: dict | None = None,
    ) -> dict:
        """ONTAP REST API リクエストを実行

        Args:
            method: HTTP メソッド (GET, POST, PATCH, DELETE)
            path: API パス (例: /storage/volumes)
            params: クエリパラメータ
            body: リクエストボディ (JSON)

        Returns:
            dict: レスポンスボディ (JSON パース済み)

        Raises:
            OntapClientError: 非 2xx レスポンスの場合、または path が不正な場合
        """
        if is_unsafe_path(path):
            logger.warning("Refused ONTAP request with unsafe path: %r", path[:200])
            raise OntapClientError(
                "Invalid characters in request path",
                status_code=400,
            )

        pool = self._get_pool()
        headers = self._make_headers()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"

        url = f"https://{self._config.management_ip}{self.BASE_API_PATH}{path}"

        kwargs: dict[str, Any] = {
            "method": method,
            "url": url,
            "headers": headers,
        }

        if params:
            # urllib3 uses 'fields' for query parameters on GET
            if method == "GET":
                kwargs["fields"] = params
            else:
                # For non-GET with params, append to URL
                query_string = "&".join(f"{k}={v}" for k, v in params.items())
                kwargs["url"] = f"{url}?{query_string}"

        if body is not None:
            kwargs["body"] = json.dumps(body).encode("utf-8")

        try:
            response = pool.request(**kwargs)
        except urllib3.exceptions.MaxRetryError as e:
            raise OntapClientError(f"Max retries exceeded for {method} {path}: {e}") from e
        except urllib3.exceptions.TimeoutError as e:
            raise OntapClientError(f"Request timeout for {method} {path}: {e}") from e
        except Exception as e:
            raise OntapClientError(f"Request failed for {method} {path}: {e}") from e

        response_body = response.data.decode("utf-8")

        if response.status < 200 or response.status >= 300:
            raise OntapClientError(
                f"ONTAP API error: {method} {path} returned {response.status}",
                status_code=response.status,
                response_body=response_body,
            )

        if not response_body:
            return {}

        try:
            return json.loads(response_body)
        except json.JSONDecodeError:
            return {"raw": response_body}

    # --- 汎用 REST メソッド ---

    def get(self, path: str, params: dict | None = None) -> dict:
        """GET リクエスト"""
        return self._request("GET", path, params=params)

    def post(self, path: str, body: dict | None = None) -> dict:
        """POST リクエスト"""
        return self._request("POST", path, body=body)

    def patch(self, path: str, body: dict | None = None) -> dict:
        """PATCH リクエスト"""
        return self._request("PATCH", path, body=body)

    def delete(self, path: str) -> dict:
        """DELETE リクエスト"""
        return self._request("DELETE", path)

    # --- ショートカットメソッド ---

    def list_volumes(self, svm_uuid: str | None = None) -> list[dict]:
        """ボリューム一覧取得

        Args:
            svm_uuid: SVM UUID でフィルタ (オプション)

        Returns:
            list[dict]: ボリューム情報のリスト
        """
        params = {"fields": "name,uuid,size,state,type,svm,nas,style"}
        if svm_uuid:
            params["svm.uuid"] = svm_uuid
        result = self.get("/storage/volumes", params=params)
        return result.get("records", [])

    def get_volume(self, volume_uuid: str) -> dict:
        """ボリューム詳細取得

        Args:
            volume_uuid: ボリューム UUID

        Returns:
            dict: ボリューム詳細情報
        """
        return self.get(
            f"/storage/volumes/{volume_uuid}",
            params={"fields": "name,uuid,size,state,type,svm,nas,style,snapshot_policy"},
        )

    def list_cifs_shares(self, svm_uuid: str) -> list[dict]:
        """CIFS 共有一覧取得

        Args:
            svm_uuid: SVM UUID

        Returns:
            list[dict]: CIFS 共有情報のリスト
        """
        result = self.get(
            "/protocols/cifs/shares",
            params={
                "svm.uuid": svm_uuid,
                "fields": "svm,name,path,volume,acls",
            },
        )
        return result.get("records", [])

    def list_nfs_exports(self, svm_uuid: str) -> list[dict]:
        """NFS エクスポートポリシー一覧取得

        Args:
            svm_uuid: SVM UUID

        Returns:
            list[dict]: NFS エクスポートポリシー情報のリスト
        """
        result = self.get(
            "/protocols/nfs/export-policies",
            params={
                "svm.uuid": svm_uuid,
                "fields": "name,rules",
            },
        )
        return result.get("records", [])

    def get_svm(self, svm_uuid: str) -> dict:
        """SVM 詳細取得

        Args:
            svm_uuid: SVM UUID

        Returns:
            dict: SVM 詳細情報
        """
        return self.get(
            f"/svm/svms/{svm_uuid}",
            params={"fields": "name,uuid,state,ip_interfaces,cifs,nfs,s3"},
        )

    def get_file_security(
        self,
        svm_uuid: str,
        volume_uuid: str,
        path: str,
    ) -> dict:
        """ファイルセキュリティ（ACL）情報取得

        Args:
            svm_uuid: SVM UUID
            volume_uuid: ボリューム UUID
            path: ファイルパス

        Returns:
            dict: ファイルセキュリティ情報（ACL 含む）
        """
        return self.get(
            f"/protocols/file-security/permissions/{svm_uuid}/{volume_uuid}/{path}",
        )

    # --- FlexCache 操作メソッド ---

    def list_flexcaches(
        self,
        name: str | None = None,
        svm_name: str | None = None,
    ) -> list[dict]:
        """FlexCache ボリューム一覧取得

        Args:
            name: FlexCache 名でフィルタ (オプション)
            svm_name: SVM 名でフィルタ (オプション)

        Returns:
            list[dict]: FlexCache ボリューム情報のリスト
        """
        params: dict[str, str] = {
            "fields": "name,uuid,svm,size,path,origins,state",
        }
        if name:
            params["name"] = name
        if svm_name:
            params["svm.name"] = svm_name
        result = self.get("/storage/flexcache/flexcaches", params=params)
        return result.get("records", [])

    def get_flexcache(self, uuid: str) -> dict:
        """FlexCache ボリューム詳細取得

        Args:
            uuid: FlexCache UUID

        Returns:
            dict: FlexCache 詳細情報
        """
        return self.get(
            f"/storage/flexcache/flexcaches/{uuid}",
            params={"fields": "name,uuid,svm,size,path,origins,state,prepopulate"},
        )

    def create_flexcache(
        self,
        name: str,
        svm_name: str,
        origin_volume: str,
        origin_svm: str,
        size_gb: int,
        junction_path: str | None = None,
        aggregate_name: str | None = None,
        prepopulate_dir_paths: list[str] | None = None,
    ) -> dict:
        """FlexCache ボリューム作成

        Args:
            name: FlexCache ボリューム名
            svm_name: キャッシュ SVM 名
            origin_volume: オリジンボリューム名
            origin_svm: オリジン SVM 名
            size_gb: サイズ (GB)
            junction_path: ジャンクションパス (デフォルト: /{name})
            aggregate_name: アグリゲート名 (オプション)
            prepopulate_dir_paths: Prepopulate 対象ディレクトリ (オプション)

        Returns:
            dict: 作成結果（job UUID 含む）

        Raises:
            OntapClientError: 作成失敗時
        """
        body: dict[str, Any] = {
            "name": name,
            "svm": {"name": svm_name},
            "origins": [
                {
                    "volume": {"name": origin_volume},
                    "svm": {"name": origin_svm},
                }
            ],
            "size": size_gb * 1024 * 1024 * 1024,  # GB → bytes
        }

        if junction_path:
            body["path"] = junction_path
        else:
            body["path"] = f"/{name}"

        if aggregate_name:
            body["aggregates"] = [{"name": aggregate_name}]

        if prepopulate_dir_paths:
            body["prepopulate"] = {"dir_paths": prepopulate_dir_paths}

        logger.info("Creating FlexCache: %s (origin: %s/%s)", name, origin_svm, origin_volume)
        return self.post("/storage/flexcache/flexcaches", body=body)

    def delete_flexcache(self, uuid: str) -> dict:
        """FlexCache ボリューム削除

        Args:
            uuid: FlexCache UUID

        Returns:
            dict: 削除結果（job UUID 含む）

        Raises:
            OntapClientError: 削除失敗時
        """
        logger.info("Deleting FlexCache: %s", uuid)
        return self.delete(f"/storage/flexcache/flexcaches/{uuid}")

    def prepopulate_flexcache(
        self,
        uuid: str,
        dir_paths: list[str],
        exclude_dir_paths: list[str] | None = None,
    ) -> dict:
        """FlexCache Prepopulate 実行

        指定ディレクトリのデータを事前にキャッシュにフェッチする。
        ONTAP 9.13.1+ が必要。

        Args:
            uuid: FlexCache UUID
            dir_paths: Prepopulate 対象ディレクトリパスのリスト
            exclude_dir_paths: 除外ディレクトリパスのリスト (オプション)

        Returns:
            dict: Prepopulate ジョブ結果
        """
        body: dict[str, Any] = {"dir_paths": dir_paths}
        if exclude_dir_paths:
            body["exclude_dir_paths"] = exclude_dir_paths

        logger.info("Prepopulating FlexCache %s: %s", uuid, dir_paths)
        return self.patch(
            f"/storage/flexcache/flexcaches/{uuid}",
            body={"prepopulate": body},
        )

    # --- SnapMirror 操作メソッド ---
    #
    # These carry only the request path, the payload and the field mapping. Input
    # validation, the confirm gate on the destructive ones, the audit log line and
    # the camelCase response shaping stay with the caller: whether a particular
    # operation needs a human to confirm it is a property of the surface exposing
    # it, not of the protocol.
    #
    # Field selections are the ones verified against a live cluster. Notably
    # `last_transfer_size` is NOT a field on the relationships endpoint -- ONTAP
    # 9.17 rejects the whole request with 'The value "last_transfer_size" is
    # invalid for field "fields"' and the list comes back empty. Per-transfer byte
    # counts come from list_snapmirror_transfers() instead.

    RELATIONSHIP_FIELDS = (
        "uuid,source.path,source.svm.name,destination.path,destination.svm.name,"
        "state,healthy,policy.name,lag_time,last_transfer_type"
    )
    TRANSFER_FIELDS = "state,bytes_transferred,end_time,total_duration"

    def list_snapmirror_relationships(self, max_records: int = 100) -> list[dict]:
        """SnapMirror リレーションシップ一覧取得

        ONTAP REST: GET /snapmirror/relationships

        Returns:
            list[dict]: リレーションシップの生レコード
        """
        result = self.get(
            "/snapmirror/relationships",
            params={"fields": self.RELATIONSHIP_FIELDS, "max_records": str(max_records)},
        )
        return result.get("records", [])

    def list_snapmirror_transfers(
        self,
        relationship_uuid: str,
        max_records: int = 20,
    ) -> list[dict]:
        """1 つのリレーションシップの転送履歴取得

        ONTAP REST: GET /snapmirror/relationships/{uuid}/transfers
        """
        result = self.get(
            f"/snapmirror/relationships/{relationship_uuid}/transfers",
            params={"fields": self.TRANSFER_FIELDS, "max_records": str(max_records)},
        )
        return result.get("records", [])

    def set_snapmirror_state(self, relationship_uuid: str, state: str) -> dict:
        """SnapMirror の state を変更

        ONTAP REST: PATCH /snapmirror/relationships/{uuid}

        `paused` で quiesce、`snapmirrored` で resume/resync、`broken_off` で break。
        break と resync は宛先のデータを不可逆に変えるため、呼び出し側で確認を取ること。
        """
        return self.patch(
            f"/snapmirror/relationships/{relationship_uuid}",
            body={"state": state},
        )

    def quiesce_snapmirror(self, relationship_uuid: str) -> dict:
        """転送を一時停止 (state=paused)"""
        return self.set_snapmirror_state(relationship_uuid, "paused")

    def resume_snapmirror(self, relationship_uuid: str) -> dict:
        """一時停止した転送を再開 (state=snapmirrored)"""
        return self.set_snapmirror_state(relationship_uuid, "snapmirrored")

    def break_snapmirror(self, relationship_uuid: str) -> dict:
        """リレーションシップを break して宛先を書き込み可能にする

        break 後、宛先はソースから乖離します。呼び出し側で確認を取ること。
        """
        return self.set_snapmirror_state(relationship_uuid, "broken_off")

    def resync_snapmirror(self, relationship_uuid: str) -> dict:
        """break したリレーションシップを再同期する

        break 後に宛先へ書き込まれた変更は破棄されます。呼び出し側で確認を取ること。
        """
        return self.set_snapmirror_state(relationship_uuid, "snapmirrored")

    def update_snapmirror_now(self, relationship_uuid: str) -> dict:
        """スケジュールを待たず即時転送を開始

        ONTAP REST: POST /snapmirror/relationships/{uuid}/transfers
        """
        return self.post(f"/snapmirror/relationships/{relationship_uuid}/transfers")

    def abort_snapmirror_transfer(self, relationship_uuid: str, transfer_uuid: str) -> dict:
        """進行中の転送を中断

        ONTAP REST: PATCH /snapmirror/relationships/{uuid}/transfers/{transfer_uuid}
        """
        return self.patch(
            f"/snapmirror/relationships/{relationship_uuid}/transfers/{transfer_uuid}",
            body={"state": "aborted"},
        )

    def delete_snapmirror(self, relationship_uuid: str) -> dict:
        """リレーションシップを削除

        ONTAP REST: DELETE /snapmirror/relationships/{uuid}

        宛先ボリュームは残りますが複製は止まります。呼び出し側で確認を取ること。
        """
        return self.delete(f"/snapmirror/relationships/{relationship_uuid}")

    def wait_ontap_job(
        self,
        job_uuid: str,
        timeout_seconds: int = 300,
        poll_interval: int = 5,
    ) -> dict:
        """ONTAP 非同期ジョブの完了を待機

        Args:
            job_uuid: ジョブ UUID
            timeout_seconds: タイムアウト秒数 (デフォルト: 300)
            poll_interval: ポーリング間隔秒数 (デフォルト: 5)

        Returns:
            dict: ジョブ最終状態

        Raises:
            OntapClientError: タイムアウトまたはジョブ失敗時
        """
        import time

        start_time = time.time()
        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                raise OntapClientError(f"ONTAP job {job_uuid} timed out after {timeout_seconds}s")

            job = self.get(f"/cluster/jobs/{job_uuid}")
            state = job.get("state", "unknown")

            if state == "success":
                logger.info("ONTAP job %s completed successfully", job_uuid)
                return job
            elif state in ("failure", "error"):
                error_msg = job.get("message", "Unknown error")
                raise OntapClientError(
                    f"ONTAP job {job_uuid} failed: {error_msg}",
                    response_body=json.dumps(job),
                )

            logger.debug(
                "ONTAP job %s state: %s (%.0fs elapsed)",
                job_uuid,
                state,
                elapsed,
            )
            time.sleep(poll_interval)
