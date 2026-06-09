"""ONTAP REST API クライアント.

SnapMirror 関係の状態取得・転送トリガーを行う。
"""

import logging
from datetime import datetime, timezone
from enum import Enum

import httpx

from .config import settings

logger = logging.getLogger(__name__)


class TransferState(str, Enum):
    """SnapMirror 転送状態."""

    IDLE = "idle"
    TRANSFERRING = "transferring"
    QUEUED = "queued"
    SUCCESS = "success"
    FAILED = "failed"
    ABORTED = "aborted"


class SnapMirrorStatus:
    """SnapMirror 関係のステータス."""

    def __init__(
        self,
        state: TransferState,
        healthy: bool,
        last_transfer_end: str | None = None,
        bytes_transferred: int = 0,
        transfer_uuid: str | None = None,
        error_message: str | None = None,
    ):
        self.state = state
        self.healthy = healthy
        self.last_transfer_end = last_transfer_end
        self.bytes_transferred = bytes_transferred
        self.transfer_uuid = transfer_uuid
        self.error_message = error_message

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "healthy": self.healthy,
            "last_transfer_end": self.last_transfer_end,
            "bytes_transferred": self.bytes_transferred,
            "transfer_uuid": self.transfer_uuid,
            "error_message": self.error_message,
        }


class OntapClient:
    """ONTAP REST API クライアント."""

    def __init__(self):
        self._base_url = f"https://{settings.ontap_host}/api"
        self._auth = (settings.ontap_user, settings.ontap_password)
        self._verify_ssl = settings.ontap_verify_ssl
        self._relationship_uuid = settings.snapmirror_uuid

    def _get_client(self) -> httpx.AsyncClient:
        """HTTP クライアントを生成."""
        return httpx.AsyncClient(
            base_url=self._base_url,
            auth=self._auth,
            verify=self._verify_ssl,
            timeout=30.0,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )

    async def get_relationship_status(self) -> SnapMirrorStatus:
        """SnapMirror 関係の現在のステータスを取得.

        ONTAP REST API: GET /api/snapmirror/relationships/{uuid}
        """
        async with self._get_client() as client:
            try:
                response = await client.get(
                    f"/snapmirror/relationships/{self._relationship_uuid}",
                    params={"fields": "state,healthy,transfer"},
                )
                response.raise_for_status()
                data = response.json()

                # 転送中かどうかを判定
                transfer = data.get("transfer", {})
                relationship_state = data.get("state", "")
                healthy = data.get("healthy", False)

                if transfer and transfer.get("state") in ("transferring", "queued"):
                    state = TransferState(transfer["state"])
                    return SnapMirrorStatus(
                        state=state,
                        healthy=healthy,
                        bytes_transferred=transfer.get("bytes_transferred", 0),
                        transfer_uuid=transfer.get("uuid"),
                    )

                # 前回の転送終了時刻
                # transfer.end_time に含まれる（transfer が success の場合）
                last_end = None
                if transfer and transfer.get("state") == "success":
                    last_end = transfer.get("end_time")

                return SnapMirrorStatus(
                    state=TransferState.IDLE,
                    healthy=healthy,
                    last_transfer_end=last_end,
                )

            except httpx.HTTPStatusError as e:
                logger.error(f"ONTAP API error: {e.response.status_code} - {e.response.text}")
                return SnapMirrorStatus(
                    state=TransferState.FAILED,
                    healthy=False,
                    error_message=f"API Error: {e.response.status_code}",
                )
            except httpx.RequestError as e:
                logger.error(f"ONTAP connection error: {e}")
                return SnapMirrorStatus(
                    state=TransferState.FAILED,
                    healthy=False,
                    error_message=f"接続エラー: ONTAP に接続できません",
                )

    async def trigger_update(self) -> SnapMirrorStatus:
        """SnapMirror 更新（転送）をトリガー.

        ONTAP REST API: POST /api/snapmirror/relationships/{uuid}/transfers
        """
        async with self._get_client() as client:
            try:
                response = await client.post(
                    f"/snapmirror/relationships/{self._relationship_uuid}/transfers",
                    json={},
                )

                # 202 Accepted or 201 Created = 転送開始成功
                if response.status_code in (201, 202):
                    logger.info("SnapMirror transfer triggered successfully")
                    return SnapMirrorStatus(
                        state=TransferState.TRANSFERRING,
                        healthy=True,
                    )

                # 409 Conflict = 既に転送中
                if response.status_code == 409:
                    logger.warning("SnapMirror transfer already in progress")
                    return SnapMirrorStatus(
                        state=TransferState.TRANSFERRING,
                        healthy=True,
                        error_message="同期は既に実行中です",
                    )

                response.raise_for_status()

                return SnapMirrorStatus(
                    state=TransferState.TRANSFERRING,
                    healthy=True,
                )

            except httpx.HTTPStatusError as e:
                logger.error(f"ONTAP API error on trigger: {e.response.status_code} - {e.response.text}")
                return SnapMirrorStatus(
                    state=TransferState.FAILED,
                    healthy=False,
                    error_message=f"同期の開始に失敗しました (HTTP {e.response.status_code})",
                )
            except httpx.RequestError as e:
                logger.error(f"ONTAP connection error on trigger: {e}")
                return SnapMirrorStatus(
                    state=TransferState.FAILED,
                    healthy=False,
                    error_message="ONTAP に接続できません。ネットワークを確認してください。",
                )

    async def get_transfer_status(self) -> SnapMirrorStatus:
        """進行中の転送のステータスを取得.

        ONTAP REST API: GET /api/snapmirror/relationships/{uuid}/transfers
        """
        async with self._get_client() as client:
            try:
                response = await client.get(
                    f"/snapmirror/relationships/{self._relationship_uuid}/transfers",
                    params={"order_by": "end_time desc", "limit": 1},
                )
                response.raise_for_status()
                data = response.json()

                records = data.get("records", [])
                if not records:
                    return SnapMirrorStatus(state=TransferState.IDLE, healthy=True)

                latest = records[0]
                state_str = latest.get("state", "idle")

                if state_str in ("transferring", "queued"):
                    return SnapMirrorStatus(
                        state=TransferState(state_str),
                        healthy=True,
                        bytes_transferred=latest.get("bytes_transferred", 0),
                        transfer_uuid=latest.get("uuid"),
                    )
                elif state_str == "success":
                    return SnapMirrorStatus(
                        state=TransferState.SUCCESS,
                        healthy=True,
                        bytes_transferred=latest.get("bytes_transferred", 0),
                        last_transfer_end=latest.get("end_time"),
                    )
                elif state_str in ("failed", "aborted"):
                    return SnapMirrorStatus(
                        state=TransferState(state_str),
                        healthy=False,
                        error_message=latest.get("error_info", {}).get("message", "不明なエラー"),
                    )
                else:
                    return SnapMirrorStatus(state=TransferState.IDLE, healthy=True)

            except httpx.HTTPStatusError as e:
                logger.error(f"Transfer status error: {e.response.status_code}")
                return SnapMirrorStatus(
                    state=TransferState.FAILED,
                    healthy=False,
                    error_message=f"ステータス取得エラー (HTTP {e.response.status_code})",
                )
            except httpx.RequestError as e:
                logger.error(f"Transfer status connection error: {e}")
                return SnapMirrorStatus(
                    state=TransferState.FAILED,
                    healthy=False,
                    error_message="ONTAP に接続できません",
                )


# デモモードならモッククライアント、通常は本物のクライアント
from .config import settings as _settings

if _settings.demo_mode:
    from .mock_client import MockOntapClient
    ontap_client = MockOntapClient()  # type: ignore[assignment]
else:
    ontap_client = OntapClient()
