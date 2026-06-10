from __future__ import annotations

"""SSL 証明書の自動生成ユーティリティ.

サーバー起動時に自己署名証明書が存在しなければ自動生成する。
デモ/PoC 用途のため、本番環境では適切な CA 証明書を使用すること。
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

CERT_DIR = Path(__file__).parent.parent / "certs"
CERT_FILE = CERT_DIR / "server.crt"
KEY_FILE = CERT_DIR / "server.key"


def ensure_ssl_certs() -> tuple[Path, Path] | None:
    """SSL 証明書が存在しなければ自動生成する.

    Returns:
        (cert_path, key_path) のタプル。生成失敗時は None。
    """
    CERT_DIR.mkdir(parents=True, exist_ok=True)

    if CERT_FILE.exists() and KEY_FILE.exists():
        logger.info(f"SSL certs found: {CERT_FILE}")
        return CERT_FILE, KEY_FILE

    logger.info("Generating self-signed SSL certificate...")
    try:
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(KEY_FILE),
                "-out",
                str(CERT_FILE),
                "-days",
                "365",
                "-nodes",
                "-subj",
                "/CN=SnapMirror Sync Demo/O=Hybrid Cloud Demo",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info(f"SSL certificate generated: {CERT_FILE}")
        return CERT_FILE, KEY_FILE
    except FileNotFoundError:
        logger.warning("openssl not found — HTTPS disabled. Install openssl for HTTPS support.")
        return None
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to generate SSL cert: {e.stderr}")
        return None
