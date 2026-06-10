from __future__ import annotations

"""モック ONTAP クライアント.

DEMO_MODE=true で起動した場合に使用する。
実際の ONTAP 接続なしで UI の動作確認・リハーサルが可能。
"""

import asyncio
import logging
import random

from .ontap_client import SnapMirrorStatus, TransferState

logger = logging.getLogger(__name__)


class MockOntapClient:
    """ONTAP REST API のモッククライアント.

    実際の ONTAP に接続せず、リアルなタイミングで状態遷移をシミュレートする。
    """

    def __init__(self):
        self._is_transferring = False
        self._transfer_started = False
        self._transfer_progress = 0  # 0-100
        self._transfer_bytes = 0
        self._demo_file_size = 5 * 1024 * 1024  # 5 MB のデモデータ

    async def get_relationship_status(self) -> SnapMirrorStatus:
        """SnapMirror 関係のモックステータスを返す."""
        if self._is_transferring:
            return SnapMirrorStatus(
                state=TransferState.TRANSFERRING,
                healthy=True,
                bytes_transferred=self._transfer_bytes,
                transfer_uuid="mock-transfer-uuid-0001",
            )

        return SnapMirrorStatus(
            state=TransferState.IDLE,
            healthy=True,
            last_transfer_end="2026-06-09T10:00:00Z",
        )

    async def trigger_update(self) -> SnapMirrorStatus:
        """SnapMirror 更新のモックトリガー.

        バックグラウンドで 5-12 秒かけて転送を完了させる。
        """
        if self._is_transferring:
            return SnapMirrorStatus(
                state=TransferState.TRANSFERRING,
                healthy=True,
                error_message="同期は既に実行中です",
            )

        self._is_transferring = True
        self._transfer_progress = 0
        self._transfer_bytes = 0

        logger.info("[DEMO MODE] Mock SnapMirror transfer triggered")

        # バックグラウンドで転送をシミュレート
        asyncio.create_task(self._simulate_transfer())

        return SnapMirrorStatus(
            state=TransferState.TRANSFERRING,
            healthy=True,
        )

    async def _simulate_transfer(self):
        """転送をシミュレート（5-12秒で完了）."""
        total_duration = random.uniform(5.0, 12.0)
        steps = int(total_duration / 0.5)

        for i in range(steps):
            await asyncio.sleep(0.5)
            self._transfer_progress = min(100, int((i + 1) / steps * 100))
            self._transfer_bytes = int(self._demo_file_size * self._transfer_progress / 100)

        # 完了
        self._is_transferring = False
        self._transfer_progress = 100
        self._transfer_bytes = self._demo_file_size
        logger.info(f"[DEMO MODE] Mock transfer completed ({self._demo_file_size} bytes)")

    async def get_transfer_status(self) -> SnapMirrorStatus:
        """進行中の転送のモックステータスを返す."""
        return await self.get_relationship_status()
