"""shared.streaming - Kinesis Data Streams ヘルパーモジュール

Kinesis Data Streams 操作を抽象化するヘルパークラスを提供する。
ニアリアルタイム処理パターンで使用する。

Usage:
    from shared.streaming import StreamingHelper, StreamingConfig
"""

from shared.streaming.streaming_helper import StreamingConfig, StreamingHelper

__all__ = [
    "StreamingConfig",
    "StreamingHelper",
]
