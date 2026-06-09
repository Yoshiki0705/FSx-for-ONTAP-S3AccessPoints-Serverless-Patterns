from __future__ import annotations

"""アプリケーション設定."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """環境変数から読み込む設定."""

    # ONTAP REST API（FSx for ONTAP の管理エンドポイント）
    ontap_host: str = "192.168.1.100"
    ontap_user: str = "fsxadmin"
    ontap_password: str = "changeme"
    ontap_verify_ssl: bool = False

    # SnapMirror
    snapmirror_uuid: str = ""

    # サーバー
    server_host: str = "0.0.0.0"
    server_port: int = 8080

    # セキュリティ
    auth_token: str = ""  # 空 = 認証なし

    # デモモード（ONTAP 接続なしで UI 動作確認）
    demo_mode: bool = False

    # タイムアウト
    sync_timeout_seconds: int = 600  # 10分
    poll_interval_seconds: int = 2

    # ロギング
    log_level: str = "INFO"
    audit_log_file: str = "audit.jsonl"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
