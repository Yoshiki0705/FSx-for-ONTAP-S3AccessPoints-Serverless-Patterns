"""Textract ヘルパー — 日本語文書 OCR パターン用

Amazon Textract が Asia Pacific (Tokyo) で提供開始された（2026-11-02）ことを受け、
同一リージョンで Textract を呼ぶパターンが共通で使う部品を置く。

提供するもの:
- エラーの分類（`TextractThrottled` / `TextractTransient` / `TextractRejected`）。
  Step Functions の Retry は例外のクラス名で照合するため、再試行する失敗と、しない失敗を
  クラスで分けて raise する
- `build_client`: `adaptive` リトライとタイムアウトを明示した boto3 クライアント
- `client_request_token`: `Start*` の冪等性トークン（再試行で二重課金しない）
- `BlockAccumulator`: `Get*` のページごとに Block を足し、行・表・レイアウト・品質指標に正規化する
- `decide_review`: 品質指標から Human Review の要否を判定する
- `finalize_document`: 正規化 → 判定 → 結果の書き込み → 小さな記録、までをまとめる

実 API の応答で確認した事実（ap-northeast-1、2026-11-03、架空の文書）:
- WORD は空白で区切られた断片（`部品A`、`(精密加工)`）。LINE は WORD を空白 1 つで連結した文字列
- 全角の括弧・コロン・ハイフンは半角で返る（`（` → `(`、`：` → `:`）
- 単一ページの応答には `Page` が付かない
- 表の外にある合計欄が `MERGED_CELL`（信頼度 45）に飲み込まれることがある。表の下の行は
  `TABLE_FOOTER` で返る
- 「括弧」→「括孤」のような誤読が、行の信頼度 98 のまま返ることがある。信頼度だけでは検出できない

Textract の言語サポートは API ごとに違う（Developer Guide の Set Quotas）。日本語は
DetectDocumentText と、AnalyzeDocument の Tables / Layout / Signatures で使える。Forms は
英・西・伊・葡・仏・独に限られ、手書きは英語のみ。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from shared.exceptions import (
    S3ApHelperError,
    TextractError,
    TextractRejected,
    TextractThrottled,
    TextractTransient,
)
from shared.human_review import HumanReviewDecision, evaluate_confidence
from shared.output_writer import STANDARD_S3, OutputWriter
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# エラーの分類
# ---------------------------------------------------------------------------


# Textract の API モデル（botocore 1.43）に載っているエラーだけを列挙する。
_THROTTLED_CODES = frozenset(
    {"ThrottlingException", "ProvisionedThroughputExceededException", "LimitExceededException"}
)
_TRANSIENT_CODES = frozenset({"InternalServerError", "InternalFailure", "ServiceUnavailable"})
_TRANSIENT_EXCEPTIONS = (ConnectTimeoutError, ReadTimeoutError, EndpointConnectionError)


def classify_client_error(error: Exception) -> TextractError:
    """boto3 / botocore の例外を、再試行の可否を表す `TextractError` に変換する。

    未知のコードは `TextractRejected` にする。理由の分からない失敗を無限に再試行しないため。

    Args:
        error: Textract 呼び出しで発生した例外。

    Returns:
        `TextractThrottled`、`TextractTransient`、`TextractRejected` のいずれか。
    """
    if isinstance(error, _TRANSIENT_EXCEPTIONS):
        return TextractTransient(f"{type(error).__name__}: {error}")
    if isinstance(error, ClientError):
        code = error.response.get("Error", {}).get("Code", "Unknown")
        message = error.response.get("Error", {}).get("Message", str(error))
        if code in _THROTTLED_CODES:
            return TextractThrottled(f"{code}: {message}", error_code=code)
        if code in _TRANSIENT_CODES:
            return TextractTransient(f"{code}: {message}", error_code=code)
        return TextractRejected(f"{code}: {message}", error_code=code)
    return TextractRejected(f"{type(error).__name__}: {error}")


# ---------------------------------------------------------------------------
# クライアントとトークン
# ---------------------------------------------------------------------------


def build_client(region_name: str | None = None, session: boto3.Session | None = None) -> Any:
    """Textract クライアントを作る。

    `adaptive` リトライ（最大 5 回）は、クライアント側で送信速度を絞る。東京の同期 API は
    1 TPS なので、並列呼び出しがスロットリングされたときに自動で間隔を取る。

    Args:
        region_name: リージョン。None なら実行環境のリージョン（Lambda と同一）。
        session: boto3 セッション（テスト用）。

    Returns:
        boto3 の Textract クライアント。
    """
    config = Config(
        retries={"max_attempts": 5, "mode": "adaptive"},
        connect_timeout=10,
        read_timeout=60,
    )
    return (session or boto3.Session()).client("textract", region_name=region_name, config=config)


def client_request_token(*parts: str) -> str:
    """`Start*` の `ClientRequestToken` を決定的に作る。

    同じ入力からは同じトークンになる。Step Functions がタスクを再試行しても、Textract は
    同じジョブとして扱い、二重にジョブを起動（二重課金）しない。

    Args:
        *parts: トークンの元になる文字列（実行名、文書 ID、プロファイルなど）。

    Returns:
        64 文字の `[0-9a-f]`。API の制約は `^[a-zA-Z0-9-_]+$` で 64 文字以下。
    """
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return digest[:64]


# ---------------------------------------------------------------------------
# 正規化
# ---------------------------------------------------------------------------

#: プロファイル → `AnalyzeDocument` / `StartDocumentAnalysis` の FeatureTypes。
#: `text` は DetectDocumentText / StartDocumentTextDetection（FeatureTypes なし）。
#: FORMS と QUERIES は日本語に非対応のため提供しない。
FEATURE_PROFILES: dict[str, list[str]] = {"text": [], "structure": ["TABLES", "LAYOUT"]}

#: 受け付けるエラーの上限など、ページ送りの歯止め。
MAX_RESULT_PAGES = 1000

_WS = re.compile(r"\s+")


def normalize_for_match(text: str) -> str:
    """照合用に NFKC で正規化し、空白をすべて除く。

    全角と半角の違い（`１２３` と `123`）、全角括弧、`℃` と `°C` を同じ文字として扱う。
    項目抽出の根拠の照合と、サンプルの採点で使う。

    Args:
        text: 元の文字列。

    Returns:
        比較用の文字列。
    """
    return _WS.sub("", unicodedata.normalize("NFKC", text))


def _join_fragments(fragments: Iterable[str]) -> str:
    """断片を空白 1 つで連結する。Textract が LINE を作るときと同じ規則。"""
    return " ".join(f for f in fragments if f)


def _children(block: dict[str, Any], relation: str = "CHILD") -> list[str]:
    ids: list[str] = []
    for rel in block.get("Relationships", []) or []:
        if rel.get("Type") == relation:
            ids.extend(rel.get("Ids", []))
    return ids


@dataclass
class QualityMetrics:
    """文書の品質指標（Textract の信頼度は 0〜100）。"""

    pages: int = 0
    line_count: int = 0
    char_count: int = 0
    word_count: int = 0
    mean_confidence: float = 0.0
    min_confidence: float = 0.0
    low_confidence_lines: int = 0
    low_confidence_char_ratio: float = 0.0
    handwriting_word_ratio: float = 0.0
    table_count: int = 0
    low_confidence_tables: int = 0

    def to_dict(self) -> dict[str, Any]:
        """JSON にできる辞書へ変換する。"""
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


@dataclass
class BlockAccumulator:
    """`Get*` のページごとに Block を足し、最後に正規化する。

    結果は複数のレスポンスに分かれて届き、親と子が別のレスポンスに入りうる。そのため
    WORD と LINE は ID で保持し、表やレイアウトの本文は `result()` で組み立てる。

    Attributes:
        low_confidence_threshold: これ未満の行を低信頼度として数える（0〜100）。
        table_confidence_floor: これ未満の表を「構造が疑わしい」として数える（0〜100）。
    """

    low_confidence_threshold: float = 90.0
    table_confidence_floor: float = 80.0
    _lines: list[dict[str, Any]] = field(default_factory=list, init=False)
    _words: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _line_by_id: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _tables: list[dict[str, Any]] = field(default_factory=list, init=False)
    _cells: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _merged: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _layout: list[dict[str, Any]] = field(default_factory=list, init=False)
    _page_numbers: set[int] = field(default_factory=set, init=False)
    _declared_pages: int = field(default=0, init=False)

    def declare_pages(self, pages: int) -> None:
        """レスポンスの `DocumentMetadata.Pages` を記録する。

        Args:
            pages: 文書全体のページ数。
        """
        self._declared_pages = max(self._declared_pages, int(pages or 0))

    def add(self, blocks: Iterable[dict[str, Any]]) -> None:
        """Block を足す。1 回のレスポンスごとに呼ぶ。

        Args:
            blocks: レスポンスの `Blocks`。
        """
        for block in blocks:
            kind = block.get("BlockType")
            page = int(block.get("Page") or 1)  # 単一ページの応答には Page が付かない
            self._page_numbers.add(page)
            if kind == "LINE":
                entry = {
                    "id": block.get("Id"),
                    "order": len(self._lines),
                    "page": page,
                    "text": block.get("Text", ""),
                    "confidence": float(block.get("Confidence", 0.0)),
                }
                self._lines.append(entry)
                if entry["id"]:
                    self._line_by_id[entry["id"]] = entry
            elif kind == "WORD":
                self._words[block.get("Id", "")] = {
                    "text": block.get("Text", ""),
                    "confidence": float(block.get("Confidence", 0.0)),
                    "handwriting": block.get("TextType") == "HANDWRITING",
                }
            elif kind == "TABLE":
                self._tables.append(
                    {
                        "id": block.get("Id"),
                        "page": page,
                        "confidence": float(block.get("Confidence", 0.0)),
                        "cell_ids": _children(block),
                        "merged_ids": _children(block, "MERGED_CELL"),
                    }
                )
            elif kind == "CELL":
                self._cells[block.get("Id", "")] = {
                    "row": int(block.get("RowIndex", 1)),
                    "col": int(block.get("ColumnIndex", 1)),
                    "row_span": int(block.get("RowSpan", 1)),
                    "col_span": int(block.get("ColumnSpan", 1)),
                    "confidence": float(block.get("Confidence", 0.0)),
                    "word_ids": _children(block),
                    "header": "COLUMN_HEADER" in (block.get("EntityTypes") or []),
                }
            elif kind == "MERGED_CELL":
                self._merged[block.get("Id", "")] = {
                    "row": int(block.get("RowIndex", 1)),
                    "col": int(block.get("ColumnIndex", 1)),
                    "confidence": float(block.get("Confidence", 0.0)),
                }
            elif isinstance(kind, str) and kind.startswith("LAYOUT_"):
                self._layout.append(
                    {
                        "type": kind,
                        "page": page,
                        "confidence": float(block.get("Confidence", 0.0)),
                        "line_ids": _children(block),
                    }
                )

    def result(self) -> dict[str, Any]:
        """足した Block を、ページ・行・表・レイアウト・品質指標に正規化する。

        Returns:
            `pages`（行・表・レイアウト）と `quality` を持つ辞書。JSON にできる。
        """
        pages: dict[int, dict[str, Any]] = {}

        def page_entry(number: int) -> dict[str, Any]:
            return pages.setdefault(number, {"page": number, "lines": [], "tables": [], "layout": []})

        for number in sorted(self._page_numbers) or ([1] if self._declared_pages else []):
            page_entry(number)
        for line in self._lines:
            page_entry(line["page"])["lines"].append({"text": line["text"], "confidence": round(line["confidence"], 2)})
        for table in self._tables:
            page_entry(table["page"])["tables"].append(self._build_table(table))
        for item in self._layout:
            members = [self._line_by_id[i] for i in item["line_ids"] if i in self._line_by_id]
            texts = [m["text"] for m in sorted(members, key=lambda m: m["order"])]
            page_entry(item["page"])["layout"].append(
                {
                    "type": item["type"],
                    "confidence": round(item["confidence"], 2),
                    "text": _join_fragments(texts),
                }
            )
        ordered = [pages[n] for n in sorted(pages)]
        return {"pages": ordered, "quality": self._quality(len(ordered)).to_dict()}

    # -- 内部 ---------------------------------------------------------------

    def _cell_text(self, cell: dict[str, Any]) -> str:
        return _join_fragments(self._words[i]["text"] for i in cell["word_ids"] if i in self._words)

    def _build_table(self, table: dict[str, Any]) -> dict[str, Any]:
        cells = [self._cells[i] for i in table["cell_ids"] if i in self._cells]
        rows: dict[int, dict[int, str]] = {}
        for cell in cells:
            rows.setdefault(cell["row"], {})[cell["col"]] = self._cell_text(cell)
        width = max((c["col"] + c["col_span"] - 1 for c in cells), default=0)
        grid = [[rows.get(r, {}).get(c, "") for c in range(1, width + 1)] for r in sorted(rows)]
        merged = [self._merged[i] for i in table["merged_ids"] if i in self._merged]
        suspicious = bool(merged) and min(m["confidence"] for m in merged) < self.table_confidence_floor
        return {
            "confidence": round(table["confidence"], 2),
            "rows": grid,
            "merged_cells": len(merged),
            "structure_suspect": suspicious,
        }

    def _quality(self, page_count: int) -> QualityMetrics:
        lines = self._lines
        chars = [len(re.sub(r"\s", "", ln["text"])) for ln in lines]
        total_chars = sum(chars)
        words = list(self._words.values())
        metrics = QualityMetrics(
            pages=max(page_count, self._declared_pages),
            line_count=len(lines),
            char_count=total_chars,
            word_count=len(words),
            table_count=len(self._tables),
        )
        if lines:
            weights = [c or 1 for c in chars]
            weighted = sum(ln["confidence"] * w for ln, w in zip(lines, weights, strict=True))
            metrics.mean_confidence = weighted / sum(weights)
            metrics.min_confidence = min(ln["confidence"] for ln in lines)
            low = [
                (ln, c) for ln, c in zip(lines, chars, strict=True) if ln["confidence"] < self.low_confidence_threshold
            ]
            metrics.low_confidence_lines = len(low)
            if total_chars:
                metrics.low_confidence_char_ratio = sum(c for _, c in low) / total_chars
        if words:
            metrics.handwriting_word_ratio = sum(1 for w in words if w["handwriting"]) / len(words)
        suspect = 0
        for table in self._tables:
            merged = [self._merged[i] for i in table["merged_ids"] if i in self._merged]
            if table["confidence"] < self.table_confidence_floor or (
                merged and min(m["confidence"] for m in merged) < self.table_confidence_floor
            ):
                suspect += 1
        metrics.low_confidence_tables = suspect
        return metrics


#: 再試行しても結果が変わらない S3 の失敗。これらは文書単位の失敗として記録し、
#: それ以外（SlowDown、InternalError など）は再送出して Step Functions に再試行させる。
#: HEAD は本文を持たないため、存在しないキーのコードは "NoSuchKey" ではなく "404" で返る
#: （S3ApHelper.get_object_bytes は先に HEAD する。moto で確認）。
PERMANENT_S3_ERROR_CODES = frozenset(
    {
        "AccessDenied",
        "NoSuchKey",
        "404",
        "NotFound",
        "NoSuchBucket",
        "ObjectTooLargeForInlineAnalysis",
        "InvalidObjectState",
    }
)


def is_permanent_s3_error(error: S3ApHelperError) -> bool:
    """S3 Access Point の失敗が、再試行しても直らない種類かを返す。

    Args:
        error: `S3ApHelper` が raise した例外。

    Returns:
        恒久的な失敗なら True。
    """
    return error.error_code in PERMANENT_S3_ERROR_CODES


def failure_record(error: Exception) -> dict[str, Any]:
    """文書単位の失敗を、Step Functions の状態に載せられる小さな記録にする。

    Args:
        error: 失敗の原因。`error_code` を持つ例外ならそれをエラー型にする。

    Returns:
        `status: failed` と、エラー型・200 文字までのメッセージを持つ記録。
    """
    code = getattr(error, "error_code", None) or type(error).__name__
    return {"status": "failed", "error": {"type": str(code), "message": str(error)[:200]}}


def review_settings_from_env() -> tuple[float, dict[str, float]]:
    """環境変数から Human Review の閾値を読む。

    Returns:
        (低信頼度の行とみなす信頼度 0〜100, `decide_review` に渡す閾値の辞書)。
    """
    thresholds = {
        "auto_approve": float(os.environ.get("REVIEW_AUTO_APPROVE", "0.95")),
        "reject": float(os.environ.get("REVIEW_REJECT", "0.30")),
        "low_confidence_char_ratio_limit": float(os.environ.get("LOW_CONFIDENCE_CHAR_RATIO", "0.05")),
        "handwriting_word_ratio_limit": float(os.environ.get("HANDWRITING_WORD_RATIO", "0.05")),
    }
    return float(os.environ.get("LOW_CONFIDENCE_LINE", "90")), thresholds


# ---------------------------------------------------------------------------
# ステージング（S3 Access Point → 通常の S3 バケット）
# ---------------------------------------------------------------------------

#: ストリーミングコピーのチャンクとパートの大きさ。S3 のマルチパートは最終パート以外 5 MiB 以上。
STAGING_CHUNK_BYTES = 8 * 1024 * 1024
STAGING_PART_BYTES = 16 * 1024 * 1024


def staged_key_for(execution_name: str, doc_id: str, original_key: str) -> str:
    """ステージングバケット上のキーを作る。

    原本のキーは日本語を含みうるので使わない。拡張子だけ引き継ぐ。

    Args:
        execution_name: Step Functions の実行名。
        doc_id: 文書 ID（キーのハッシュ）。
        original_key: 原本のオブジェクトキー。

    Returns:
        `staging/<実行名>/<文書 ID><拡張子>`。
    """
    return f"staging/{execution_name}/{doc_id}{PurePosixPath(original_key).suffix.lower()}"


def stage_document(
    source_alias: str,
    key: str,
    staging_bucket: str,
    staged_key: str,
    size: int | None = None,
) -> dict[str, Any]:
    """S3 Access Point 上の文書を、同一リージョンの通常 S3 バケットへストリーミングコピーする。

    Textract の非同期 API (`Start*`) は `DocumentLocation` に S3 バケット上のオブジェクトしか
    受け付けない。FSx for ONTAP の S3 Access Point は `S3Object` 参照で読めない
    (docs/agent/pitfalls-s3ap-ontap.md) ので、非同期で処理するにはいったん通常のバケットに置く。
    メモリに全体を載せず、チャンクで流す。

    Args:
        source_alias: コピー元の S3 Access Point Alias（または通常バケット名）。
        key: コピー元のキー。
        staging_bucket: コピー先の通常 S3 バケット。
        staged_key: コピー先のキー。
        size: コピー元のサイズ（バイト）。分かっていればマルチパートの判断に使う。

    Returns:
        `OutputWriter.put_stream` の戻り値（`bucket_or_ap`、`key`、`size` など）。

    Raises:
        S3ApHelperError: コピー元の読み取りに失敗した場合。
    """
    source = S3ApHelper(source_alias)
    return OutputWriter(STANDARD_S3, bucket=staging_bucket).put_stream(
        staged_key,
        source.streaming_download(key, chunk_size=STAGING_CHUNK_BYTES),
        part_size=STAGING_PART_BYTES,
        content_length_hint=size,
    )


def delete_staged_copy(staging_bucket: str, staged_key: str) -> None:
    """ステージング済みのコピーを削除する。失敗してもワークフローは止めない。

    Args:
        staging_bucket: ステージングバケット名。
        staged_key: 削除するキー。
    """
    try:
        S3ApHelper(staging_bucket).delete_object(staged_key)
    except S3ApHelperError as e:
        # バケットのライフサイクル（1 日）が最終的に消す。ここで失敗させて文書の結果を失うほうが損失が大きい。
        logger.warning("Could not delete staged copy %s: %s", staged_key, e)


def collection_fields(collections_json: str, collection: str) -> list[str]:
    """コレクション設定から、項目抽出の項目名を引く。

    検証は discovery が済ませている。ここでは読むだけで、設定が読めないときは空を返す
    （項目抽出を飛ばすだけで、OCR の結果は捨てない）。

    Args:
        collections_json: `COLLECTIONS_JSON` の文字列。
        collection: コレクション ID。

    Returns:
        項目名のリスト。無ければ空。
    """
    try:
        fields = json.loads(collections_json)[collection].get("fields", [])
    except (TypeError, ValueError, KeyError, AttributeError):
        return []
    return [f for f in fields if isinstance(f, str)] if isinstance(fields, list) else []


# ---------------------------------------------------------------------------
# Human Review の判定
# ---------------------------------------------------------------------------


def decide_review(
    quality: dict[str, Any],
    *,
    auto_approve: float = 0.95,
    reject: float = 0.30,
    low_confidence_char_ratio_limit: float = 0.05,
    handwriting_word_ratio_limit: float = 0.05,
    extra_reasons: Iterable[str] = (),
) -> HumanReviewDecision:
    """品質指標から Human Review の要否を判定する。

    平均信頼度だけでは足りない。実測では、誤読された行が信頼度 98 のまま返った。
    そのため、平均信頼度の判定（`evaluate_confidence`）に、次の引き上げを重ねる。
    いずれも「補助信号」であり、最終判断ではない。

    - 低信頼度の行が全文字の `low_confidence_char_ratio_limit` を超える
    - 手書きと判定された単語の割合が `handwriting_word_ratio_limit` を超える
      （手書き認識は英語のみのため、日本語の手書きは誤りやすい）
    - 構造が疑わしい表（結合セルの信頼度が低いなど）がある
    - テキストが 1 行も検出されなかった
    - 呼び出し側が渡した追加の理由（項目抽出の根拠なしなど）

    REJECT は引き上げで変えない。

    Args:
        quality: `BlockAccumulator.result()["quality"]`。
        auto_approve: 自動承認する平均信頼度（0〜1）の下限。
        reject: これ未満は REJECT（0〜1）。
        low_confidence_char_ratio_limit: 低信頼度の文字割合の上限。
        handwriting_word_ratio_limit: 手書き単語割合の上限。
        extra_reasons: 追加の引き上げ理由。1 つでもあれば HUMAN_REVIEW 以上にする。

    Returns:
        `HumanReviewDecision`。`confidence` は平均信頼度を 0〜1 にした値。
    """
    reasons: list[str] = []
    if int(quality.get("line_count", 0)) == 0:
        base = HumanReviewDecision(
            confidence=0.0, requires_review=True, action="HUMAN_REVIEW", reason="No text detected"
        )
        reasons.extend(extra_reasons)
        if reasons:
            base.reason = "; ".join([base.reason, *reasons])
        return base

    mean = float(quality.get("mean_confidence", 0.0)) / 100.0
    decision = evaluate_confidence(mean, threshold_auto_approve=auto_approve, threshold_reject=reject)
    if decision.action == "HUMAN_REVIEW":
        # evaluate_confidence の理由は小数 2 桁で、0.949 と 0.95 の差が同じ数字に見える。
        decision.reason = f"Mean confidence {mean:.3f} below auto-approve threshold {auto_approve:.3f}"
    if float(quality.get("low_confidence_char_ratio", 0.0)) > low_confidence_char_ratio_limit:
        reasons.append(f"{float(quality['low_confidence_char_ratio']):.0%} of characters are in low-confidence lines")
    if float(quality.get("handwriting_word_ratio", 0.0)) > handwriting_word_ratio_limit:
        reasons.append("handwriting detected (Textract handwriting recognition supports English only)")
    if int(quality.get("low_confidence_tables", 0)) > 0:
        reasons.append("table structure looks unreliable")
    reasons.extend(extra_reasons)

    if reasons and decision.action == "AUTO_APPROVE":
        decision = HumanReviewDecision(
            confidence=decision.confidence,
            requires_review=True,
            action="HUMAN_REVIEW",
            reason="; ".join(reasons),
        )
    elif reasons:
        decision.reason = "; ".join([decision.reason, *reasons])
    return decision


# ---------------------------------------------------------------------------
# 結果の確定
# ---------------------------------------------------------------------------

#: 実行結果に載せる理由の長さ。Step Functions の状態は 256 KiB までなので、小さく保つ。
MAX_REASON_CHARS = 160


def quality_pages(document: dict[str, Any]) -> int:
    """正規化結果のページ数を返す。

    Args:
        document: `BlockAccumulator.result()` の戻り値。

    Returns:
        品質指標のページ数。
    """
    return int(document["quality"]["pages"])


def result_text(document: dict[str, Any]) -> str:
    """正規化結果から、ページ順・行順のプレーンテキストを作る。

    ページの区切りは空行 1 つ。

    Args:
        document: `BlockAccumulator.result()` の戻り値。

    Returns:
        改行区切りのテキスト。
    """
    return "\n\n".join("\n".join(ln["text"] for ln in page["lines"]) for page in document["pages"])


def finalize_document(
    *,
    accumulator: BlockAccumulator,
    writer: Any,
    key_prefix: str,
    source: dict[str, Any],
    textract_meta: dict[str, Any],
    classification: str,
    thresholds: dict[str, float],
    extra_reasons: Iterable[str] = (),
) -> dict[str, Any]:
    """正規化 → 判定 → 結果の書き込み → 小さな記録、までをまとめる。

    ocr_sync と async_collect が共有する。本文は結果バケットに書き、返す記録には本文を
    含めない（Step Functions の状態に OCR 本文を載せないため）。

    Args:
        accumulator: 全ページ分を足し終えた `BlockAccumulator`。
        writer: `shared.output_writer.OutputWriter`（`put_json` / `put_text` / `build_s3_uri`）。
        key_prefix: 出力キーの接頭辞（末尾 `/` なし）。
        source: 原本の情報（`key`、`size`、`last_modified`、`etag` など）。
        textract_meta: 呼び出しの情報（`api`、`mode`、`features`、`job_id`、`model_version` など）。
        classification: 出力のデータ分類ラベル。
        thresholds: `decide_review` に渡す閾値（`auto_approve` など）。
        extra_reasons: Human Review に引き上げる追加の理由（`PARTIAL_SUCCESS` など）。

    Returns:
        `status`、`pages`、`api`、`mean_confidence`、`human_review`、出力先を持つ小さな記録。
    """
    document = accumulator.result()
    decision = decide_review(document["quality"], extra_reasons=extra_reasons, **thresholds)
    document.update(
        {
            "schema_version": "1",
            "source": source,
            "textract": textract_meta,
            "human_review": decision.to_dict(),
            "data_classification": classification,
        }
    )
    logger.info(
        "Document finalized: pages=%s lines=%s action=%s",
        quality_pages(document),
        document["quality"]["line_count"],
        decision.action,
    )
    result_key = f"{key_prefix}/result.json"
    text_key = f"{key_prefix}/text.txt"
    writer.put_json(result_key, document)
    writer.put_text(text_key, result_text(document))
    quality = document["quality"]
    return {
        "status": "completed",
        "pages": quality["pages"],
        "api": textract_meta.get("api"),
        "mean_confidence": round(float(quality["mean_confidence"]) / 100.0, 4),
        "human_review": {
            "action": decision.action,
            "requires_review": decision.requires_review,
            "reason": decision.reason[:MAX_REASON_CHARS],
        },
        "result": writer.build_s3_uri(result_key),
        "text": writer.build_s3_uri(text_key),
    }
