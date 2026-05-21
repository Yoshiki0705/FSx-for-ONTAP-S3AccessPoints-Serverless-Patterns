"""Replay Storm Test Harness — Metrics Calculation Functions

リプレイストームテストで使用するメトリクス計算関数のテストハーネス。
Out-of-Order Distance、重複検出、イベントロス率計算を含む。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ReplayStormScenario:
    """リプレイストームテストシナリオ定義。"""

    event_count: int  # 1000 or 10000
    protocol: str  # "NFSv3" | "NFSv4.1" | "SMB"
    operation: str  # "create" | "modify" | "delete" | "rename"
    file_size: str  # "small_1KB" | "large_100MB"
    downtime_minutes: int  # 5, 30, or 120


@dataclass
class ReplayStormResult:
    """テスト結果。"""

    scenario: ReplayStormScenario
    persistent_store_bytes: int
    events_queued: int
    events_replayed: int
    replay_throughput_eps: float  # events per second
    replay_duration_seconds: float
    out_of_order_distance: int  # max positional displacement
    duplicate_count: int
    duplication_rate: float  # duplicate_count / events_queued
    event_loss_rate: float  # (queued - replayed) / queued
    flagged_as_risk: bool  # True if event_loss_rate > 0.001


# =============================================================================
# Metrics Calculation Functions
# =============================================================================


def calculate_out_of_order_distance(
    original_sequence: list[str],
    replayed_sequence: list[str],
) -> int:
    """最大位置変位を計算する。

    リプレイ時にイベントが本来の順序からどれだけ離れて配信されたかの最大値。

    Args:
        original_sequence: イベント ID の元の順序
        replayed_sequence: イベント ID のリプレイ順序

    Returns:
        最大位置変位（0 = 完全順序保持）
    """
    if not original_sequence or not replayed_sequence:
        return 0

    original_positions = {eid: i for i, eid in enumerate(original_sequence)}
    max_distance = 0

    for replay_pos, eid in enumerate(replayed_sequence):
        if eid in original_positions:
            distance = abs(replay_pos - original_positions[eid])
            max_distance = max(max_distance, distance)

    return max_distance


def count_duplicates(event_ids: list[str]) -> int:
    """重複イベント数をカウントする。

    各イベント ID の最初の出現以降の追加出現回数を合計する。

    Args:
        event_ids: イベント ID のリスト

    Returns:
        重複数（0 = 重複なし）
    """
    seen: set[str] = set()
    duplicates = 0

    for eid in event_ids:
        if eid in seen:
            duplicates += 1
        else:
            seen.add(eid)

    return duplicates


def calculate_event_loss_rate(events_queued: int, events_replayed: int) -> float:
    """イベントロス率を計算する。

    Args:
        events_queued: キューに入ったイベント数
        events_replayed: リプレイされたイベント数

    Returns:
        ロス率（0.0 = ロスなし、1.0 = 全ロス）
    """
    if events_queued == 0:
        return 0.0
    return max(0.0, (events_queued - events_replayed) / events_queued)


def is_flagged_as_risk(event_loss_rate: float, threshold: float = 0.001) -> bool:
    """イベントロス率が閾値を超えているか判定する。

    Args:
        event_loss_rate: イベントロス率
        threshold: リスクフラグ閾値（デフォルト 0.1%）

    Returns:
        True if risk, False otherwise
    """
    return event_loss_rate > threshold


# =============================================================================
# Tests
# =============================================================================


class TestOutOfOrderDistance:
    """Out-of-Order Distance 計算のテスト。"""

    def test_identical_order(self):
        """完全に同じ順序 → distance = 0。"""
        original = ["a", "b", "c", "d", "e"]
        replayed = ["a", "b", "c", "d", "e"]
        assert calculate_out_of_order_distance(original, replayed) == 0

    def test_reversed_order(self):
        """完全に逆順 → distance = len - 1。"""
        original = ["a", "b", "c", "d", "e"]
        replayed = ["e", "d", "c", "b", "a"]
        assert calculate_out_of_order_distance(original, replayed) == 4

    def test_single_swap(self):
        """隣接要素の入れ替え → distance = 1。"""
        original = ["a", "b", "c"]
        replayed = ["b", "a", "c"]
        assert calculate_out_of_order_distance(original, replayed) == 1

    def test_empty_sequences(self):
        """空シーケンス → distance = 0。"""
        assert calculate_out_of_order_distance([], []) == 0

    def test_partial_overlap(self):
        """部分的に重複するシーケンス。"""
        original = ["a", "b", "c", "d"]
        replayed = ["c", "a", "d", "b"]
        # c: |0-2| = 2, a: |1-0| = 1, d: |2-3| = 1, b: |3-1| = 2
        assert calculate_out_of_order_distance(original, replayed) == 2

    def test_phase12_observed_pattern(self):
        """Phase 12 で観測されたパターン: 3, 1, 2, 5, 4。"""
        original = ["1", "2", "3", "4", "5"]
        replayed = ["3", "1", "2", "5", "4"]
        # 3: |0-2|=2, 1: |1-0|=1, 2: |2-1|=1, 5: |3-4|=1, 4: |4-3|=1
        assert calculate_out_of_order_distance(original, replayed) == 2


class TestCountDuplicates:
    """重複イベント検出のテスト。"""

    def test_no_duplicates(self):
        """重複なし → 0。"""
        assert count_duplicates(["a", "b", "c", "d"]) == 0

    def test_single_duplicate(self):
        """1 つの重複 → 1。"""
        assert count_duplicates(["a", "b", "a", "c"]) == 1

    def test_multiple_duplicates(self):
        """複数の重複。"""
        assert count_duplicates(["a", "b", "a", "b", "a"]) == 3

    def test_all_same(self):
        """全て同じ → n-1。"""
        assert count_duplicates(["x", "x", "x", "x"]) == 3

    def test_empty_list(self):
        """空リスト → 0。"""
        assert count_duplicates([]) == 0


class TestEventLossRate:
    """イベントロス率計算のテスト。"""

    def test_zero_loss(self):
        """ロスなし → 0.0。"""
        assert calculate_event_loss_rate(100, 100) == 0.0

    def test_total_loss(self):
        """全ロス → 1.0。"""
        assert calculate_event_loss_rate(100, 0) == 1.0

    def test_partial_loss(self):
        """部分ロス。"""
        assert calculate_event_loss_rate(1000, 999) == pytest.approx(0.001)

    def test_zero_queued(self):
        """キュー 0 → 0.0（ゼロ除算回避）。"""
        assert calculate_event_loss_rate(0, 0) == 0.0

    def test_more_replayed_than_queued(self):
        """リプレイ > キュー（重複含む）→ 0.0（負にならない）。"""
        assert calculate_event_loss_rate(100, 105) == 0.0


class TestRiskFlagging:
    """リスクフラグ判定のテスト。"""

    def test_below_threshold(self):
        """閾値以下 → False。"""
        assert is_flagged_as_risk(0.0005) is False

    def test_at_threshold(self):
        """閾値ちょうど → False（> であり >= ではない）。"""
        assert is_flagged_as_risk(0.001) is False

    def test_above_threshold(self):
        """閾値超過 → True。"""
        assert is_flagged_as_risk(0.002) is True

    def test_zero_loss(self):
        """ロスなし → False。"""
        assert is_flagged_as_risk(0.0) is False

    def test_custom_threshold(self):
        """カスタム閾値。"""
        assert is_flagged_as_risk(0.05, threshold=0.1) is False
        assert is_flagged_as_risk(0.15, threshold=0.1) is True
