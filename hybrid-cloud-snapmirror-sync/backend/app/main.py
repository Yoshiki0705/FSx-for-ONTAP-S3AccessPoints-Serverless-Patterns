"""SnapMirror One-Click Sync — メインアプリケーション."""

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from .config import settings
from .ontap_client import TransferState, ontap_client
from .sync_manager import sync_manager

# ロギング設定
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# 監査ログ
AUDIT_LOG_PATH = Path(settings.audit_log_file)


def get_client_ip(request: Request) -> str:
    """クライアント IP を取得（プロキシ経由対応）."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def write_audit_log(action: str, client_ip: str, result: str, detail: str = ""):
    """監査ログを JSON Lines 形式で出力."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "client_ip": client_ip,
        "result": result,
        "detail": detail,
    }
    try:
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning(f"Failed to write audit log: {e}")


# --- 起動時ヘルスチェック ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーション起動時に SnapMirror 関係の健全性を確認."""
    logger.info("=" * 60)
    logger.info("SnapMirror One-Click Sync — Starting")
    logger.info(f"  ONTAP Host: {settings.ontap_host}")
    logger.info(f"  SnapMirror UUID: {settings.snapmirror_uuid[:8]}...")
    logger.info(f"  Auth: {'Enabled' if settings.auth_token else 'Disabled'}")
    logger.info(f"  Timeout: {settings.sync_timeout_seconds}s")
    logger.info(f"  Demo Mode: {'✅ ON (no ONTAP connection)' if settings.demo_mode else 'OFF'}")
    logger.info("=" * 60)

    if settings.demo_mode:
        logger.info("🎭 DEMO MODE — ONTAP 接続なしで UI 動作確認が可能です")
    elif not settings.snapmirror_uuid:
        logger.error("❌ SNAPMIRROR_UUID が未設定です。.env を確認してください。")
    else:
        # SnapMirror 関係の状態を確認
        try:
            status = await ontap_client.get_relationship_status()
            if status.healthy:
                logger.info(f"✅ SnapMirror relationship healthy (state: {status.state.value})")
            else:
                logger.warning(
                    f"⚠️ SnapMirror relationship unhealthy (state: {status.state.value})"
                )
                if status.error_message:
                    logger.warning(f"   Error: {status.error_message}")
        except Exception as e:
            logger.error(f"❌ ONTAP 接続失敗: {e}")
            logger.error("   ONTAP_HOST と認証情報を確認してください。")

    yield
    logger.info("SnapMirror One-Click Sync — Shutting down")


app = FastAPI(
    title="SnapMirror One-Click Sync",
    description="ハイブリッドクラウド SnapMirror ワンクリック同期デモツール",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS（同一ネットワーク内のデバイスからのアクセス許可）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# フロントエンド静的ファイル
# Docker内: /app/frontend、ローカル実行: ../frontend (backendディレクトリから相対)
_app_dir = Path(__file__).parent.parent  # /app (Docker) or backend/ (local)
FRONTEND_DIR = _app_dir / "frontend"
if not FRONTEND_DIR.exists():
    # ローカル実行時 (backend/ から起動): 一つ上の frontend/
    FRONTEND_DIR = _app_dir.parent / "frontend"


# --- 認証ミドルウェア ---
async def verify_auth(request: Request, authorization: str | None = None):
    """Bearer Token 認証（AUTH_TOKEN が設定されている場合のみ有効）.

    同一オリジンからのブラウザリクエスト（Referer が自身）は認証スキップ。
    これにより AUTH_TOKEN 設定時も UI は正常に動作する。
    """
    if not settings.auth_token:
        return  # 認証無効

    # 同一オリジンのブラウザリクエストは認証スキップ
    referer = request.headers.get("referer", "")
    host = request.headers.get("host", "")
    if host and referer:
        # Referer が同一ホストならフロントエンドからのリクエスト
        if host in referer:
            return

    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization[7:]
    if token != settings.auth_token:
        raise HTTPException(status_code=403, detail="Invalid token")


# --- API エンドポイント ---


@app.post("/api/sync")
async def trigger_sync(request: Request, authorization: str | None = Header(default=None)):
    """SnapMirror 同期をトリガー.

    二重実行防止機構付き。同期中に呼ばれた場合は即座にエラーを返す。
    """
    await verify_auth(request, authorization)
    client_ip = get_client_ip(request)
    logger.info(f"Sync trigger requested from {client_ip}")

    result = await sync_manager.trigger_sync()

    write_audit_log(
        action="sync_triggered",
        client_ip=client_ip,
        result="success" if result["success"] else "rejected",
        detail=result.get("message", ""),
    )

    return result


@app.get("/api/status")
async def get_status(request: Request, authorization: str | None = Header(default=None)):
    """現在の同期状態を取得.

    フロントエンドはこのエンドポイントをポーリングして進捗を表示する。
    """
    await verify_auth(request, authorization)
    state = await sync_manager.get_current_state()
    return {"state": state}


@app.post("/api/reset")
async def reset_state(request: Request, authorization: str | None = Header(default=None)):
    """状態をリセット（デバッグ・リカバリ用）."""
    await verify_auth(request, authorization)
    client_ip = get_client_ip(request)
    logger.info(f"State reset requested from {client_ip}")
    sync_manager.reset()

    write_audit_log(action="state_reset", client_ip=client_ip, result="success")

    return {"message": "状態をリセットしました", "state": sync_manager.to_dict()}


@app.get("/api/health")
async def health_check():
    """ヘルスチェック（認証不要）.

    ONTAP ホスト名は部分的にマスクして返す（情報漏洩防止）。
    """
    relationship_ok = False
    relationship_state = "unknown"
    try:
        status = await ontap_client.get_relationship_status()
        relationship_ok = status.healthy
        relationship_state = status.state.value
    except Exception:
        pass

    # ホスト名をマスク（先頭15文字 + ...）
    masked_host = settings.ontap_host[:15] + "..." if len(settings.ontap_host) > 15 else settings.ontap_host

    return {
        "status": "ok" if relationship_ok else "degraded",
        "ontap_host": masked_host,
        "snapmirror_uuid_configured": bool(settings.snapmirror_uuid),
        "snapmirror_healthy": relationship_ok,
        "snapmirror_state": relationship_state,
        "demo_mode": settings.demo_mode,
    }


# --- フロントエンド配信 ---


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """メインページを配信."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>Frontend not found</h1><p>frontend/index.html が見つかりません</p>")


@app.get("/style.css")
async def serve_css():
    """CSS を配信."""
    css_path = FRONTEND_DIR / "style.css"
    if css_path.exists():
        return FileResponse(css_path, media_type="text/css")
    return HTMLResponse("", status_code=404)


@app.get("/app.js")
async def serve_js():
    """JavaScript を配信."""
    js_path = FRONTEND_DIR / "app.js"
    if js_path.exists():
        return FileResponse(js_path, media_type="application/javascript")
    return HTMLResponse("", status_code=404)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=True,
    )
