"""Property-Based Tests for UC7: ゲノミクス / バイオインフォマティクス

Hypothesis を使用したプロパティベーステスト。
QC Lambda および Variant Aggregation Lambda の不変条件（invariants）を
任意入力で検証する。

Testing Strategy:
- 最小 100 イテレーション/プロパティ
- 各テストにプロパティ番号タグを付与
- タグ形式: Feature: fsxn-s3ap-serverless-patterns-phase2, Property {number}: {property_text}
"""

from __future__ import annotations

import os
import sys

from hypothesis import given, settings, strategies as st

# shared モジュールと UC7 関数のパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from functions.qc.handler import _parse_fastq_records
from functions.variant_aggregation.handler import _parse_vcf_records


# ---------------------------------------------------------------------------
# Helper: FASTQ レコード生成
# ---------------------------------------------------------------------------

NUCLEOTIDES = "ATGCN"


def generate_fastq_lines(
    num_reads: int,
    seq_lengths: list[int],
    quality_chars: list[str],
) -> list[str]:
    """テスト用の有効な FASTQ テキスト行を生成する

    Args:
        num_reads: レコード数
        seq_lengths: 各レコードの配列長リスト
        quality_chars: 各レコードの品質スコア文字列リスト

    Returns:
        list[str]: FASTQ テキスト行のリスト
    """
    lines: list[str] = []
    for i in range(num_reads):
        seq_len = seq_lengths[i]
        # ヘッダー行
        lines.append(f"@READ_{i:06d}")
        # 塩基配列行
        lines.append(quality_chars[i][:0] + "A" * seq_len)  # placeholder
        # 実際の配列は呼び出し側で制御するため、ここでは seq_len 分の A を使用
        # → 呼び出し側で sequences を渡す方式に変更
        lines.append("+")
        # 品質スコア行
        lines.append(quality_chars[i][:seq_len])
    return lines


# ---------------------------------------------------------------------------
# Property 8: FASTQ QC metrics extraction
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    num_reads=st.integers(min_value=1, max_value=50),
    seq_length=st.integers(min_value=10, max_value=200),
    quality_offset=st.integers(min_value=33, max_value=73),
    gc_ratio=st.floats(min_value=0.0, max_value=1.0),
)
def test_fastq_qc_metrics_extraction(num_reads, seq_length, quality_offset, gc_ratio):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 8: FASTQ QC metrics extraction

    For any valid FASTQ data with N reads, each having a quality score
    sequence and nucleotide sequence, the QC_Lambda SHALL compute
    total_reads equal to N, average_quality_score within the valid Phred
    range (0–60), gc_content_percentage between 0 and 100, and
    sequence_length_distribution with min ≤ mean ≤ max.

    Strategy: Generate valid FASTQ records with random sequences and
    quality scores, pass to _parse_fastq_records, verify metrics are
    within valid ranges and total_reads matches input count.

    **Validates: Requirements 4.2**
    """
    # FASTQ テキスト行を生成
    lines: list[str] = []
    for i in range(num_reads):
        # ヘッダー行
        lines.append(f"@READ_{i:06d}")

        # 塩基配列行: gc_ratio に基づいて GC/AT を配分
        gc_count = int(seq_length * gc_ratio)
        at_count = seq_length - gc_count
        # G と C を半分ずつ
        g_count = gc_count // 2
        c_count = gc_count - g_count
        # A と T を半分ずつ
        a_count = at_count // 2
        t_count = at_count - a_count
        sequence = "G" * g_count + "C" * c_count + "A" * a_count + "T" * t_count
        lines.append(sequence)

        # セパレータ行
        lines.append("+")

        # 品質スコア行: 全文字同じ品質スコア
        quality_char = chr(quality_offset)
        lines.append(quality_char * seq_length)

    # イテレータとして渡す
    result = _parse_fastq_records(iter(lines), max_records=num_reads + 10)

    # total_reads は入力レコード数と一致する
    assert result["total_reads"] == num_reads

    # average_quality_score は有効な Phred 範囲 (0–60) 内
    assert 0 <= result["average_quality_score"] <= 60

    # gc_content_percentage は 0–100 の範囲内
    assert 0 <= result["gc_content_percentage"] <= 100

    # sequence_length_distribution: min ≤ mean ≤ max
    dist = result["sequence_length_distribution"]
    assert dist["min"] <= dist["mean"] <= dist["max"]

    # 全レコードが同じ配列長なので min == max == seq_length
    assert dist["min"] == seq_length
    assert dist["max"] == seq_length
    assert dist["mean"] == seq_length

    # 品質スコアの期待値を検証
    expected_quality = quality_offset - 33
    assert abs(result["average_quality_score"] - expected_quality) < 0.2


# ---------------------------------------------------------------------------
# Property 9: VCF variant statistics aggregation
# ---------------------------------------------------------------------------


def _generate_vcf_lines(snp_count: int, indel_count: int) -> list[str]:
    """テスト用の有効な VCF テキスト行を生成する

    Args:
        snp_count: SNP レコード数
        indel_count: Indel レコード数

    Returns:
        list[str]: VCF テキスト行のリスト
    """
    lines: list[str] = []

    # VCF ヘッダー行
    lines.append("##fileformat=VCFv4.2")
    lines.append("##source=test_generator")
    lines.append("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO")

    pos = 1

    # SNP レコード生成 (REF と ALT が共に 1 塩基)
    snp_pairs = [("A", "G"), ("C", "T"), ("G", "A"), ("T", "C"),
                 ("A", "C"), ("A", "T"), ("G", "C"), ("G", "T")]
    for i in range(snp_count):
        ref, alt = snp_pairs[i % len(snp_pairs)]
        lines.append(f"chr1\t{pos}\t.\t{ref}\t{alt}\t30\tPASS\t.")
        pos += 1

    # Indel レコード生成 (REF と ALT の長さが異なる)
    indel_pairs = [("A", "AT"), ("AT", "A"), ("G", "GCC"), ("TCC", "T"),
                   ("C", "CA"), ("GA", "G"), ("T", "TAA"), ("AAG", "A")]
    for i in range(indel_count):
        ref, alt = indel_pairs[i % len(indel_pairs)]
        lines.append(f"chr1\t{pos}\t.\t{ref}\t{alt}\t30\tPASS\t.")
        pos += 1

    return lines


@settings(max_examples=100)
@given(
    snp_count=st.integers(min_value=1, max_value=500),
    indel_count=st.integers(min_value=0, max_value=500),
)
def test_vcf_variant_statistics(snp_count, indel_count):
    """Feature: fsxn-s3ap-serverless-patterns-phase2, Property 9: VCF variant statistics aggregation

    For any valid VCF file with a set of variant records containing SNPs
    and indels, the Variant_Aggregation_Lambda SHALL compute total_variants
    equal to the sum of snp_count and indel_count, and ti_tv_ratio SHALL
    be non-negative.

    Strategy: Generate VCF records with known SNP/indel counts, pass to
    _parse_vcf_records, verify total_variants == snp_count + indel_count
    and ti_tv_ratio >= 0.

    **Validates: Requirements 4.3**
    """
    vcf_lines = _generate_vcf_lines(snp_count, indel_count)

    # イテレータとして渡す
    stats = _parse_vcf_records(iter(vcf_lines))

    # total_variants は snp_count + indel_count と一致する
    assert stats["total_variants"] == snp_count + indel_count

    # snp_count が一致する
    assert stats["snp_count"] == snp_count

    # indel_count が一致する
    assert stats["indel_count"] == indel_count

    # ti_tv_ratio は非負
    assert stats["ti_tv_ratio"] >= 0
