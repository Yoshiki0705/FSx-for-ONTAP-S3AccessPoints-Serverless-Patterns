"""同期状態管理.

二重実行防止、状態遷移管理を行う。
"""

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum

from .config import settings
from .ontap_client import TransferState, ontap_client

logger = logging.getLogger(__name__)


class SyncPhase(str, Enum):
    """同期の表示フェーズ（ユーザー向け）."""

    READY = "ready"  # 待機中 — 同期可能
    STARTING = "starting"  # 開始処理中
    SYNCING = "syncing"  # SnapMirror 転送中
    COMPLETING = "completing"  # 完了処理中
    DONE = "done"  # 完了
    ERROR = "error"  # エラー


class SyncState:
    """現在の同期状態."""

    def __init__(self):
        self.phase: SyncPhase = SyncPhase.READY
        self.message: str = "同期可能な状態です"
        self.started_at: str | None = None
        self.completed_at: str | None = None
        self.bytes_transferred: int = 0
        self.error_message: str | None = None
        self._lock = asyncio.Lock()
        self._is_running = False

    def to_dict(self) -> dict:
        return {
            "phase": self.phase.value,
            "message": self.message,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "bytes_transferred": self.bytes_transferred,
            "error_message": self.error_message,
            "can_trigger": self.phase in (SyncPhase.READY, SyncPhase.DONE, SyncPhase.ERROR),
        }

    async def trigger_sync(self) -> dict:
        """同期をトリガー（二重実行防止付き）."""
        async with self._lock:
            if self._is_running:
                return {
                    "success": False,
                    "message": "同期は既に実行中です。完了までお待ちください。",
                    "state": self.to_dict(),
                }

            self._is_running = True

        # 状態を「開始中」に更新
        self.phase = SyncPhase.STARTING
        self.message = "同期を開始しています..."
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.completed_at = None
        self.bytes_transferred = 0
        self.error_message = None

        # SnapMirror 更新をトリガー
        result = await ontap_client.trigger_update()

        if result.state == TransferState.FAILED:
            self.phase = SyncPhase.ERROR
            self.message = "同期の開始に失敗しました"
            self.error_message = result.error_message
            async with self._lock:
                self._is_running = False
            return {
                "success": False,
                "message": result.error_message or "同期の開始に失敗しました",
                "state": self.to_dict(),
            }

        # 転送開始成功
        self.phase = SyncPhase.SYNCING
        self.message = "データを同期中..."

        # バックグラウンドで進捗監視を開始
        asyncio.create_task(self._monitor_transfer())

        return {
            "success": True,
            "message": "同期を開始しました",
            "state": self.to_dict(),
        }

    async def _monitor_transfer(self):
        """バックグラウンドで転送状態を監視."""
        try:
            poll_interval = settings.poll_interval_seconds
            max_polls = settings.sync_timeout_seconds // poll_interval

            for i in range(max_polls):
                await asyncio.sleep(poll_interval)

                status = await ontap_client.get_relationship_status()

                if status.state == TransferState.TRANSFERRING:
                    self.bytes_transferred = status.bytes_transferred
                    transferred_mb = self.bytes_transferred / (1024 * 1024)
                    self.message = f"データを同期中... ({transferred_mb:.1f} MB 転送済み)"
                    continue

                if status.state == TransferState.QUEUED:
                    self.message = "同期がキューに入りました。開始を待っています..."
                    continue

                if status.state == TransferState.IDLE:
                    # 転送完了
                    self.phase = SyncPhase.DONE
                    self.message = "同期が完了しました ✓"
                    self.completed_at = datetime.now(timezone.utc).isoformat()
                    logger.info(
                        f"SnapMirror transfer completed. Bytes: {self.bytes_transferred}"
                    )
                    break

                if status.state == TransferState.FAILED:
                    self.phase = SyncPhase.ERROR
                    self.message = "同期中にエラーが発生しました"
                    self.error_message = status.error_message
                    logger.error(f"SnapMirror transfer failed: {status.error_message}")
                    break

            else:
                # タイムアウト
                timeout_min = settings.sync_timeout_seconds // 60
                self.phase = SyncPhase.ERROR
                self.message = "同期がタイムアウトしました"
                self.error_message = f"{timeout_min}分以内に完了しませんでした。手動で確認してください。"
                logger.warning("SnapMirror transfer monitoring timed out")

        except Exception as e:
            self.phase = SyncPhase.ERROR
            self.message = "監視中にエラーが発生しました"
            self.error_message = str(e)
            logger.exception("Error monitoring SnapMirror transfer")

        finally:
            async with self._lock:
                self._is_running = False

    async def get_current_state(self) -> dict:
        """現在の状態を取得（ONTAP に問い合わせ含む）."""
        # 実行中でなければ ONTAP の最新状態を確認
        if not self._is_running and self.phase in (SyncPhase.READY, SyncPhase.DONE, SyncPhase.ERROR):
            status = await ontap_client.get_relationship_status()

            # ONTAP 側で転送が進行中の場合（別の手段でトリガーされた等）
            if status.state in (TransferState.TRANSFERRING, TransferState.QUEUED):
                self.phase = SyncPhase.SYNCING
                self.message = "データを同期中...（外部トリガー検出）"
                self._is_running = True
                asyncio.create_task(self._monitor_transfer())

        return self.to_dict()

    def reset(self):
        """状態をリセット（デバッグ用）."""
        self.phase = SyncPhase.READY
        self.message = "同期可能な状態です"
        self.started_at = None
        self.completed_at = None
        self.bytes_transferred = 0
        self.error_message = None
        self._is_running = False


# シングルトン
sync_manager = SyncState()
