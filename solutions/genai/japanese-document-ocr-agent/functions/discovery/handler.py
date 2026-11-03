"""Discovery Lambda — 日本語文書 OCR × AgentCore Gateway パターン。

エージェントが渡した入力を検証し、サーバー側の許可リスト（コレクション設定）から
プレフィックス・プロファイル・データ分類を解決し、S3 Access Point 上の文書を一覧して
ルーティング（同期 / 非同期 / スキップ）を決める。ワークフローの最初の Task。

エージェントから受け取るのは `collection`（ASCII の ID）、`profile`、`max_files`、
`modified_after` だけ。S3 のパスやキーは受け取らない。日本語をツール入力に要求しないので、
Gateway 経由の入力で日本語が化ける問題（前回パターンで観測）に依存しない。

入力が不正なときは `InvalidInput`、コレクション設定が不正なときは `InvalidConfiguration` を
raise する。どちらも再試行しても直らないので、ステートマシンは再試行せず実行を FAILED で終える。

Environment Variables:
    S3_ACCESS_POINT_ALIAS: S3 Access Point Alias（DemoMode では通常バケット名）
    COLLECTIONS_JSON: コレクションの許可リスト（JSON）
    DEFAULT_PROFILE: コレクションが profile を持たないときの既定（text | structure）
    MAX_FILES: 1 実行あたりの最大文書数
    MAX_DOCUMENT_BYTES: 1 文書の最大バイト数
    MAP_CONCURRENCY: Map の同時実行数
    POLL_SECONDS: 非同期ジョブの最初の待機秒数
    ENABLE_FIELD_EXTRACTION: "true" で項目抽出を有効にする
    DATA_CLASSIFICATION: コレクションが分類を持たないときの既定
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

from shared.data_classification import DataClassification
from shared.exceptions import InvalidConfiguration, InvalidInput, lambda_error_handler
from shared.observability import EmfMetrics
from shared.s3ap_helper import S3ApHelper
from shared.textract_helper import FEATURE_PROFILES

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ALLOWED_INPUT_KEYS = frozenset({"collection", "profile", "max_files", "modified_after"})
COLLECTION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: 同期 API に bytes で渡せる上限。API リファレンスの `Bytes` の上限（5 MB）に合わせる。
SYNC_INLINE_LIMIT = 5 * 1024 * 1024
#: 画像を非同期 API に S3 参照で渡せる上限（Developer Guide の Set Quotas）。
ASYNC_IMAGE_LIMIT = 10 * 1024 * 1024

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg"})
DOCUMENT_EXTENSIONS = frozenset({".pdf", ".tif", ".tiff"})
DEFAULT_SUFFIXES = tuple(sorted(IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS))

#: 実行結果に載せる skipped の件数。全件は件数（skipped_count）で示す。
MAX_SKIPPED_LISTED = 50
MAX_FIELDS = 20
MAX_FIELD_NAME_CHARS = 40

#: Step Functions の状態は 1 つにつき 256 KiB (262,144 B) まで。Map が終わった時点の状態は、
#: discovery の出力（`objects` と `skipped`）と文書ごとの結果（`processed`）を同時に持ち、
#: キーはその両方に現れる。キーが長いと 100 件でも上限を超える（約 900 B のキー 100 件で約 320 KB、
#: 2026-11-03 に手元で計算）。対象にする文書数を、キーの長さを含めた見積りで制限する。
#: 上限の約 88 %。残りは見積りの誤差のための余白。
#: 見積りが実際の状態より小さくならないことは、tests/test_state_budget.py が実際のハンドラーの
#: 出力（最悪の値で埋めたもの）で確かめる。ハンドラーの出力が増えてそのテストが落ちたら、
#: 次の 2 つの定数を上げるか、記録を小さくする。
STATE_BUDGET_BYTES = 230_000
#: 文書によらない分（入力、discovery のスカラー、実行名など）。
BASE_STATE_BYTES = 2_000
#: 1 文書あたり、キー以外の分。内訳は `objects` の項目 171 B と、`processed` の記録 1,402 B
#: （`ocr` 1,057 B、`fields` 265 B など。理由の文字列は 3 バイト文字 160 字で埋めた最悪値）で
#: 合計 1,575 B。それに約 8 % の余白を足した値。
PER_DOCUMENT_BYTES = 1_700


def parse_collections(raw: str) -> dict[str, dict[str, Any]]:
    """許可リストの JSON を検証して返す。

    Args:
        raw: `COLLECTIONS_JSON` の文字列。

    Returns:
        コレクション ID から設定への辞書。`suffixes` は小文字・ドット始まりに揃える。

    Raises:
        InvalidConfiguration: JSON が不正、または規則に反する場合。
    """
    try:
        data = json.loads(raw)
    except (TypeError, ValueError) as e:
        raise InvalidConfiguration(f"COLLECTIONS_JSON is not valid JSON: {e}") from e
    if not isinstance(data, dict) or not data:
        raise InvalidConfiguration("COLLECTIONS_JSON must be a non-empty JSON object")
    valid_classifications = {c.name for c in DataClassification}
    collections: dict[str, dict[str, Any]] = {}
    for name, cfg in data.items():
        if not COLLECTION_ID.match(name):
            raise InvalidConfiguration(f"collection id {name!r} must match {COLLECTION_ID.pattern}")
        if not isinstance(cfg, dict):
            raise InvalidConfiguration(f"collection {name!r}: settings must be an object")
        unknown = set(cfg) - {"prefix", "suffixes", "profile", "classification", "fields"}
        if unknown:
            raise InvalidConfiguration(f"collection {name!r}: unknown setting(s) {sorted(unknown)}")
        prefix = cfg.get("prefix")
        if not isinstance(prefix, str) or not prefix or prefix.startswith("/"):
            raise InvalidConfiguration(f"collection {name!r}: prefix must be a non-empty string without a leading '/'")
        suffixes = cfg.get("suffixes", list(DEFAULT_SUFFIXES))
        if not isinstance(suffixes, list) or not suffixes or not all(isinstance(s, str) for s in suffixes):
            raise InvalidConfiguration(f"collection {name!r}: suffixes must be a non-empty list of strings")
        suffixes = [s.lower() if s.startswith(".") else f".{s.lower()}" for s in suffixes]
        profile = cfg.get("profile")
        if profile is not None and profile not in FEATURE_PROFILES:
            raise InvalidConfiguration(f"collection {name!r}: profile must be one of {sorted(FEATURE_PROFILES)}")
        classification = cfg.get("classification")
        if classification is not None and classification not in valid_classifications:
            raise InvalidConfiguration(
                f"collection {name!r}: classification must be one of {sorted(valid_classifications)}"
            )
        fields = cfg.get("fields", [])
        if (
            not isinstance(fields, list)
            or len(fields) > MAX_FIELDS
            or not all(isinstance(f, str) and 0 < len(f) <= MAX_FIELD_NAME_CHARS for f in fields)
        ):
            raise InvalidConfiguration(
                f"collection {name!r}: fields must be a list of at most {MAX_FIELDS} strings "
                f"of 1-{MAX_FIELD_NAME_CHARS} characters"
            )
        collections[name] = {
            "prefix": prefix,
            "suffixes": suffixes,
            "profile": profile,
            "classification": classification,
            "fields": fields,
        }
    return collections


def validate_request(request: Any, max_files_cap: int) -> dict[str, Any]:
    """エージェントの入力を検証する。

    Args:
        request: `StartExecution` の `input` を JSON として解析した値。
        max_files_cap: スタックが許す 1 実行あたりの最大文書数。

    Returns:
        検証済みの入力（`collection`、`profile`、`max_files`、`modified_after`。省略は None）。

    Raises:
        InvalidInput: 型・キー・値が規則に反する場合。メッセージはエージェントが読んで直せる形にする。
    """
    if not isinstance(request, dict):
        raise InvalidInput(f"input must be a JSON object, got {type(request).__name__}")
    unknown = sorted(set(request) - ALLOWED_INPUT_KEYS)
    if unknown:
        raise InvalidInput(f"unknown field(s): {', '.join(unknown)}; allowed: {', '.join(sorted(ALLOWED_INPUT_KEYS))}")
    collection = request.get("collection")
    if not isinstance(collection, str) or not COLLECTION_ID.match(collection):
        raise InvalidInput(f"collection is required and must match {COLLECTION_ID.pattern} (ASCII id, not a path)")
    profile = request.get("profile")
    if profile is not None and profile not in FEATURE_PROFILES:
        raise InvalidInput(f"profile must be one of: {', '.join(sorted(FEATURE_PROFILES))}")
    max_files = request.get("max_files")
    if max_files is not None and (
        isinstance(max_files, bool) or not isinstance(max_files, int) or not 1 <= max_files <= max_files_cap
    ):
        raise InvalidInput(f"max_files must be an integer from 1 to {max_files_cap}")
    modified_after = request.get("modified_after")
    if modified_after is not None:
        if not isinstance(modified_after, str) or not DATE_ONLY.match(modified_after):
            raise InvalidInput("modified_after must be a date string YYYY-MM-DD")
        try:
            datetime.strptime(modified_after, "%Y-%m-%d")
        except ValueError as e:
            raise InvalidInput(f"modified_after is not a real date: {modified_after}") from e
    return {
        "collection": collection,
        "profile": profile,
        "max_files": max_files,
        "modified_after": modified_after,
    }


def route_object(key: str, size: int, suffixes: list[str], max_document_bytes: int) -> tuple[str, str | None]:
    """1 つの文書の処理経路を決める。

    PDF のページ数は推定しない（失敗しうる推定より、常に非同期にするほうが確実）。
    同期 API は PDF / TIFF を 1 ページしか受け付けず、東京の同期は 1 TPS のため、
    PDF と TIFF は非同期にする。

    Args:
        key: オブジェクトキー。
        size: バイト数。
        suffixes: コレクションが許す拡張子（小文字・ドット始まり）。
        max_document_bytes: 1 文書の最大バイト数。

    Returns:
        (経路, スキップ理由)。経路は "sync" | "async" | "skip"。スキップ以外の理由は None。
    """
    extension = PurePosixPath(key).suffix.lower()
    if extension not in suffixes or extension not in IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS:
        return "skip", "unsupported_extension"
    if size <= 0:
        return "skip", "empty"
    if size > max_document_bytes:
        return "skip", "too_large"
    if extension in IMAGE_EXTENSIONS:
        if size <= SYNC_INLINE_LIMIT:
            return "sync", None
        if size <= ASYNC_IMAGE_LIMIT:
            return "async", None
        return "skip", "image_too_large"
    return "async", None


def doc_id_for(key: str) -> str:
    """出力キーに使う文書 ID（キーの sha256 先頭 16 文字）を返す。

    原本のキーは日本語を含みうる。出力のパスには使わず、ハッシュで置き換える。

    Args:
        key: 原本のオブジェクトキー。

    Returns:
        16 文字の 16 進文字列。
    """
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def document_state_cost(key: str) -> int:
    """1 文書が、Map 終了時点の状態に占めるバイト数の見積りを返す。

    キーは `objects` と `processed` の両方に載るので 2 回数える。

    Args:
        key: オブジェクトキー。

    Returns:
        見積りのバイト数（UTF-8）。
    """
    return 2 * len(key.encode("utf-8")) + PER_DOCUMENT_BYTES


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


def _parse_modified(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


@lambda_error_handler
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Discovery Lambda ハンドラー。

    Args:
        event: `{"request": <エージェントの input>, "execution_name": <実行名>}`。
        context: Lambda コンテキスト。

    Returns:
        `collection`、`profile`、`classification`、`output_prefix`、`objects`（Map の入力）、
        `skipped`、`map_concurrency` などを持つ辞書。`truncated` は、対象の文書のうち先頭（キー順）
        の一部だけを選んだとき真になる。理由は `max_files` か、状態の大きさの予算
        （`STATE_BUDGET_BYTES`）のどちらか。

    Raises:
        InvalidInput: 入力が不正な場合。
        InvalidConfiguration: コレクション設定が不正な場合。
        S3ApHelperError: S3 Access Point の一覧に失敗した場合（Step Functions が再試行する）。
    """
    max_files_cap = _env_int("MAX_FILES", 50)
    max_document_bytes = _env_int("MAX_DOCUMENT_BYTES", 50 * 1024 * 1024)
    request = validate_request(event.get("request"), max_files_cap)
    collections = parse_collections(os.environ.get("COLLECTIONS_JSON", ""))
    collection = request["collection"]
    if collection not in collections:
        raise InvalidInput(f"unknown collection {collection!r}; available: {', '.join(sorted(collections))}")
    settings = collections[collection]

    profile = request["profile"] or settings["profile"] or os.environ.get("DEFAULT_PROFILE", "text")
    if profile not in FEATURE_PROFILES:
        raise InvalidConfiguration(f"DEFAULT_PROFILE must be one of {sorted(FEATURE_PROFILES)}")
    classification = settings["classification"] or os.environ.get("DATA_CLASSIFICATION", "INTERNAL").upper()
    max_files = request["max_files"] or max_files_cap
    modified_after = (
        datetime.strptime(request["modified_after"], "%Y-%m-%d").replace(tzinfo=UTC)
        if request["modified_after"]
        else None
    )
    execution_name = str(event.get("execution_name") or "local")
    alias = os.environ.get("S3_ACCESS_POINT_ALIAS", "")

    logger.info(
        "Discovery: collection=%s profile=%s prefix=%s max_files=%d modified_after=%s",
        collection,
        profile,
        settings["prefix"],
        max_files,
        request["modified_after"],
    )
    listed = S3ApHelper(alias).list_objects(prefix=settings["prefix"])

    candidates = []
    for item in listed:
        key = item["Key"]
        if key.endswith("/"):  # フォルダを表すプレースホルダ
            continue
        modified = _parse_modified(item.get("LastModified"))
        if modified_after and (modified is None or modified < modified_after):
            continue
        candidates.append((key, int(item.get("Size", 0)), modified, item.get("ETag", "")))
    candidates.sort(key=lambda c: c[0])  # 打ち切っても再現できるよう、キー順に固定する

    eligible: list[tuple[str, int, datetime | None, str, str]] = []
    skipped: list[dict[str, str]] = []
    skipped_count = 0
    for key, size, modified, etag in candidates:
        route, reason = route_object(key, size, settings["suffixes"], max_document_bytes)
        if route == "skip":
            skipped_count += 1
            if len(skipped) < MAX_SKIPPED_LISTED:
                skipped.append({"key": key, "reason": reason or "skipped"})
            continue
        eligible.append((key, size, modified, etag, route))

    # skipped は状態に載るので、その分を差し引いた予算の中で、キー順の先頭から選ぶ。
    budget = (
        STATE_BUDGET_BYTES
        - BASE_STATE_BYTES
        - sum(len(json.dumps(s, ensure_ascii=False).encode("utf-8")) + 2 for s in skipped)
    )
    objects: list[dict[str, Any]] = []
    used = 0
    truncated = False
    for key, size, modified, etag, route in eligible:
        cost = document_state_cost(key)
        if len(objects) >= max_files or used + cost > budget:
            truncated = True
            if len(objects) < max_files:
                logger.warning(
                    "State budget reached: %d of %d eligible documents selected (max_files=%d)",
                    len(objects),
                    len(eligible),
                    max_files,
                )
            break
        used += cost
        objects.append(
            {
                "key": key,
                "size": size,
                "last_modified": modified.isoformat() if modified else "",
                "etag": etag,
                "route": route,
                "doc_id": doc_id_for(key),
            }
        )

    metrics = EmfMetrics(service="japanese-document-ocr-agent")
    metrics.set_dimension("Collection", collection)
    metrics.put_metric("FilesDiscovered", len(objects), "Count")
    metrics.put_metric("FilesSkipped", skipped_count, "Count")
    metrics.flush()
    logger.info("Discovery completed: %d to process, %d skipped, truncated=%s", len(objects), skipped_count, truncated)

    return {
        "status": "completed",
        "collection": collection,
        "profile": profile,
        "classification": classification,
        "execution_name": execution_name,
        "output_prefix": f"{collection}/{execution_name}",
        "extract_fields": os.environ.get("ENABLE_FIELD_EXTRACTION", "false").lower() == "true"
        and bool(settings["fields"]),
        "object_count": len(objects),
        "objects": objects,
        "truncated": truncated,
        "skipped_count": skipped_count,
        "skipped": skipped,
        "map_concurrency": _env_int("MAP_CONCURRENCY", 2),
        "poll_seconds": _env_int("POLL_SECONDS", 5),
    }
