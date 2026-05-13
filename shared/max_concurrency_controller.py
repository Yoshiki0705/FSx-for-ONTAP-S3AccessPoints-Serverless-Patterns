"""MaxConcurrency Controller — 動的並列度算出.

Discovery Lambda がファイル一覧を取得した後、ONTAP API レートリミットと
検出ファイル数に基づいて最適な MaxConcurrency 値を算出する。

算出ロジック:
    optimal = min(
        detected_file_count,
        ontap_rate_limit // api_calls_per_file,
        max_concurrency_upper_bound
    )
    result = max(optimal, 1)  # 最低 1 を保証

Usage:
    from shared.max_concurrency_controller import calculate_max_concurrency

    concurrency = calculate_max_concurrency(
        detected_file_count=150,
        ontap_rate_limit=100,
        api_calls_per_file=2,
        max_concurrency_upper_bound=40,
    )
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def calculate_max_concurrency(
    detected_file_count: int,
    ontap_rate_limit: int = 100,
    api_calls_per_file: int = 2,
    max_concurrency_upper_bound: int = 40,
) -> int:
    """最適な MaxConcurrency 値を算出する.

    Args:
        detected_file_count: Discovery Lambda が検出したファイル数
        ontap_rate_limit: ONTAP API の秒間リクエスト上限
        api_calls_per_file: 1 ファイルあたりの ONTAP API 呼び出し回数
        max_concurrency_upper_bound: MaxConcurrency の上限値

    Returns:
        int: 算出された MaxConcurrency 値 (1 以上、upper_bound 以下)

    Raises:
        ValueError: 入力パラメータが不正な場合
    """
    if detected_file_count < 0:
        raise ValueError(
            f"detected_file_count must be >= 0, got {detected_file_count}"
        )
    if ontap_rate_limit <= 0:
        raise ValueError(
            f"ontap_rate_limit must be > 0, got {ontap_rate_limit}"
        )
    if api_calls_per_file <= 0:
        raise ValueError(
            f"api_calls_per_file must be > 0, got {api_calls_per_file}"
        )
    if max_concurrency_upper_bound <= 0:
        raise ValueError(
            f"max_concurrency_upper_bound must be > 0, got {max_concurrency_upper_bound}"
        )

    # Calculate rate-limited concurrency
    rate_limited = ontap_rate_limit // api_calls_per_file

    # Take the minimum of all constraints
    optimal = min(detected_file_count, rate_limited, max_concurrency_upper_bound)

    # Ensure at least 1 (handles detected_file_count=0 case)
    result = max(optimal, 1)

    logger.info(
        "MaxConcurrency calculated: %d (files=%d, rate_limit=%d, "
        "calls_per_file=%d, upper_bound=%d)",
        result,
        detected_file_count,
        ontap_rate_limit,
        api_calls_per_file,
        max_concurrency_upper_bound,
    )

    return result
