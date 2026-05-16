"""shared.integrations.protobuf_integration — ProtobufFrameReader 統合ヘルパー

既存 FPolicy サーバーの read_fpolicy_message() を ProtobufFrameReader で
オプトインで置き換えるための統合ヘルパー。

環境変数 `PROTOBUF_FRAMING_MODE` による制御:
- 未設定: レガシー read_fpolicy_message() を使用（None を返す）
- AUTO_DETECT: 自動検出モードで ProtobufFrameReader を作成
- LENGTH_PREFIXED: 4バイト長さプレフィックスモード
- FRAMELESS: varint-delimited モード

Usage:
    from shared.integrations.protobuf_integration import (
        create_fpolicy_reader,
        read_fpolicy_message_v2,
    )

    # Factory: ProtobufFrameReader を作成（環境変数で制御）
    reader = create_fpolicy_reader(stream_reader)
    if reader is not None:
        message = await reader.read_message()

    # Wrapper: レガシーフォールバック付き読み取り
    message = await read_fpolicy_message_v2(reader_or_stream)
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Union

from shared.fpolicy.protobuf_reader import (
    FramingError,
    FramingMode,
    ProtobufFrameReader,
)

logger = logging.getLogger(__name__)

# 環境変数名
ENV_PROTOBUF_FRAMING_MODE = "PROTOBUF_FRAMING_MODE"

# 有効なモード値のマッピング
_MODE_MAP: dict[str, FramingMode] = {
    "AUTO_DETECT": FramingMode.AUTO_DETECT,
    "LENGTH_PREFIXED": FramingMode.LENGTH_PREFIXED,
    "FRAMELESS": FramingMode.FRAMELESS,
}


def create_fpolicy_reader(
    stream_reader: asyncio.StreamReader,
    *,
    max_message_size: int = 1_048_576,
) -> ProtobufFrameReader | None:
    """環境変数に基づいて ProtobufFrameReader を作成するファクトリ関数。

    環境変数 `PROTOBUF_FRAMING_MODE` を読み取り、設定されていれば
    対応するモードで ProtobufFrameReader を作成して返す。
    未設定の場合は None を返し、呼び出し元はレガシーの
    read_fpolicy_message() を使用すべきことを示す。

    Args:
        stream_reader: asyncio.StreamReader インスタンス
        max_message_size: メッセージサイズ上限（バイト、デフォルト: 1MB）

    Returns:
        ProtobufFrameReader インスタンス、または None（レガシーモード）

    Raises:
        ValueError: 無効な PROTOBUF_FRAMING_MODE 値が設定されている場合
    """
    mode_str = os.environ.get(ENV_PROTOBUF_FRAMING_MODE, "").strip().upper()

    if not mode_str:
        logger.debug(
            "PROTOBUF_FRAMING_MODE not set; using legacy read_fpolicy_message()"
        )
        return None

    if mode_str not in _MODE_MAP:
        raise ValueError(
            f"Invalid PROTOBUF_FRAMING_MODE: '{mode_str}'. "
            f"Valid values: {', '.join(_MODE_MAP.keys())}"
        )

    mode = _MODE_MAP[mode_str]
    logger.info("Creating ProtobufFrameReader with mode=%s", mode.value)

    return ProtobufFrameReader(
        reader=stream_reader,
        mode=mode,
        max_message_size=max_message_size,
    )


async def read_fpolicy_message_v2(
    reader_or_stream: Union[ProtobufFrameReader, asyncio.StreamReader],
) -> bytes | None:
    """ProtobufFrameReader またはレガシーストリームからメッセージを読み取るラッパー。

    ProtobufFrameReader が渡された場合はそのまま read_message() を使用する。
    asyncio.StreamReader が渡された場合は、環境変数を確認して
    ProtobufFrameReader を作成するか、レガシーフォールバックとして
    4バイト長さプレフィックス方式で読み取る。

    Args:
        reader_or_stream: ProtobufFrameReader または asyncio.StreamReader

    Returns:
        メッセージバイト列。EOF/コネクションクローズ時は None。

    Raises:
        FramingError: 不正なフレームデータまたはサイズ超過時
    """
    if isinstance(reader_or_stream, ProtobufFrameReader):
        return await reader_or_stream.read_message()

    # asyncio.StreamReader が渡された場合
    stream: asyncio.StreamReader = reader_or_stream

    # 環境変数で ProtobufFrameReader が有効か確認
    mode_str = os.environ.get(ENV_PROTOBUF_FRAMING_MODE, "").strip().upper()
    if mode_str and mode_str in _MODE_MAP:
        # ProtobufFrameReader を作成して読み取り
        reader = ProtobufFrameReader(
            reader=stream,
            mode=_MODE_MAP[mode_str],
        )
        return await reader.read_message()

    # レガシーフォールバック: 4バイト big-endian 長さプレフィックス方式
    return await _legacy_read_fpolicy_message(stream)


async def _legacy_read_fpolicy_message(
    stream: asyncio.StreamReader,
) -> bytes | None:
    """レガシー read_fpolicy_message() の async 版フォールバック。

    既存の同期版 read_fpolicy_message() と同等のロジックを
    asyncio.StreamReader 向けに実装する。

    Frame format: 4-byte big-endian length + payload
    （簡略化版 — 既存サーバーの quote-delimited フォーマットは
    同期ソケット専用のため、async 版では標準的な length-prefixed を使用）

    Args:
        stream: asyncio.StreamReader インスタンス

    Returns:
        メッセージバイト列。EOF 時は None。
    """
    try:
        header = await stream.readexactly(4)
    except asyncio.IncompleteReadError:
        return None

    msg_len = int.from_bytes(header, "big")

    if msg_len == 0 or msg_len > 10 * 1024 * 1024:
        logger.warning("Legacy reader: invalid message length: %d", msg_len)
        return None

    try:
        payload = await stream.readexactly(msg_len)
    except asyncio.IncompleteReadError:
        return None

    return payload
