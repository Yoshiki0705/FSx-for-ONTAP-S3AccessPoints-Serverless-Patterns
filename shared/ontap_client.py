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
from typing import Any

import boto3
import urllib3

logger = logging.getLogger(__name__)


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
                f"Failed to retrieve credentials from Secrets Manager "
                f"(secret: {self._config.secret_name}): {e}"
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
            OntapClientError: 非 2xx レスポンスの場合
        """
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
            raise OntapClientError(
                f"Max retries exceeded for {method} {path}: {e}"
            ) from e
        except urllib3.exceptions.TimeoutError as e:
            raise OntapClientError(
                f"Request timeout for {method} {path}: {e}"
            ) from e
        except Exception as e:
            raise OntapClientError(
                f"Request failed for {method} {path}: {e}"
            ) from e

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
