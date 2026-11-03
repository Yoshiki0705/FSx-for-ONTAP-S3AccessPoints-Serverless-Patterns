"""Extract fields Lambda — 日本語文書 OCR × AgentCore Gateway パターン（任意）。

日本語の文書では Textract の Forms が使えない（Forms は英・西・伊・葡・仏・独のみ）ため、
請求書の合計金額のような key-value は Textract 単体では取れない。この関数は、OCR テキストから
コレクションが定めた項目を Bedrock の Converse API で取り出す。`EnableFieldExtraction=true` の
ときだけ、ステートマシンがこの関数を呼ぶ。

モデルの出力は補助信号であり、最終判断ではない。幻覚を抑えるため、モデルに「値」と一緒に
「OCR テキストからそのまま引用した根拠」を返させ、その根拠が OCR テキストに実在するか
（`normalize_for_match` で NFKC 正規化と空白除去のうえで部分一致）を機械的に確かめる。
実在しない項目は `grounded: false` とし、1 つでもあれば文書を Human Review に引き上げる。

`temperature` は既定では送らない。モデルによっては非推奨で `ValidationException` になる。
必要なら環境変数 `BEDROCK_TEMPERATURE` で明示する。

Environment Variables:
    BEDROCK_MODEL_ID: モデル ID または推論プロファイル ID（docs/bedrock-inference-profiles.md）
    BEDROCK_TEMPERATURE: 任意。設定されたときだけ送る
    COLLECTIONS_JSON: 項目リストの出どころ（discovery と同じ許可リスト）
    OUTPUT_BUCKET / OUTPUT_DESTINATION: 結果の読み書き先（shared.output_writer が読む）
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.exceptions import BedrockThrottled, InvalidConfiguration, lambda_error_handler
from shared.observability import EmfMetrics
from shared.output_writer import OutputWriter
from shared.textract_helper import collection_fields, normalize_for_match

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_bedrock = boto3.client("bedrock-runtime")

#: 待てば成功しうる Bedrock のエラー。これらは Step Functions に再試行させる。
THROTTLED_CODES = frozenset(
    {"ThrottlingException", "ServiceUnavailableException", "ModelTimeoutException", "InternalServerException"}
)

#: モデルに渡す OCR テキストの長さ。長い文書は先頭のみ（請求書・契約書の要点は先頭にある想定）。
MAX_TEXT_CHARS = 12_000
MAX_VALUE_CHARS = 200
MAX_FIELDS = 20

SYSTEM_PROMPT = (
    "あなたは文書から指定された項目を抜き出す抽出器です。OCR で読み取った文書のテキストに"
    "書かれていることだけを使い、推測や補完はしません。OCR の誤りは直さず、見えたとおりに返します。"
)


def build_prompt(fields: list[str], text: str) -> str:
    """モデルに渡す指示を作る。

    Args:
        fields: 取り出す項目名。
        text: OCR テキスト（`MAX_TEXT_CHARS` までに切る）。

    Returns:
        指示全体。出力は JSON のみと指定する。
    """
    listing = "\n".join(f"- {name}" for name in fields)
    return (
        "次の OCR テキストから、下の項目の値を取り出してください。\n\n"
        f"項目:\n{listing}\n\n"
        "出力は JSON オブジェクト 1 つだけにしてください（説明やコードフェンスは不要）。"
        'キーは項目名、値は {"value": 値の文字列または null, "evidence": 根拠の文字列または null} です。\n'
        "- evidence には、値が書かれている部分を OCR テキストからそのまま引用してください（言い換えない）。\n"
        "- 書かれていない項目は value も evidence も null にしてください。\n\n"
        f"OCR テキスト:\n---\n{text[:MAX_TEXT_CHARS]}\n---"
    )


def parse_model_json(raw: str) -> dict[str, Any]:
    """モデルの応答から JSON オブジェクトを取り出す。

    コードフェンスで囲まれていても、前後に説明が付いていても、最初の `{` から最後の `}` までを読む。

    Args:
        raw: モデルの応答テキスト。

    Returns:
        解析した辞書。

    Raises:
        ValueError: JSON オブジェクトが見つからない、または解析できない場合。
    """
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in the model response")
    parsed = json.loads(raw[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("the model response is not a JSON object")
    return parsed


def ground_fields(fields: list[str], extracted: dict[str, Any], text: str) -> dict[str, dict[str, Any]]:
    """各項目の値と根拠を、OCR テキストと照合する。

    `grounded` が真になるのは、値が null でなく、根拠が OCR テキストに（NFKC 正規化と空白除去のうえで）
    部分一致する場合だけ。モデルが根拠を捏造した、または言い換えた場合は偽になる。

    Args:
        fields: 要求した項目名。
        extracted: モデルが返した辞書（項目名 → `{value, evidence}`）。
        text: OCR テキスト。

    Returns:
        要求した項目すべてについて `value`、`evidence`、`grounded` を持つ辞書。
        値と根拠は `MAX_VALUE_CHARS` で切り詰める。
    """
    haystack = normalize_for_match(text)
    result: dict[str, dict[str, Any]] = {}
    for name in fields[:MAX_FIELDS]:
        entry = extracted.get(name)
        entry = entry if isinstance(entry, dict) else {}
        value = entry.get("value")
        evidence = entry.get("evidence")
        value = str(value) if value not in (None, "") else None
        evidence = str(evidence) if evidence not in (None, "") else None
        grounded = bool(value and evidence and normalize_for_match(evidence) in haystack)
        result[name] = {
            "value": value[:MAX_VALUE_CHARS] if value else None,
            "evidence": evidence[:MAX_VALUE_CHARS] if evidence else None,
            "grounded": grounded,
        }
    return result


def read_text(writer: OutputWriter, text_uri_key: str) -> str:
    """結果バケットから `text.txt` を読む。

    Args:
        writer: 結果バケットの `OutputWriter`。
        text_uri_key: `text.txt` のキー。

    Returns:
        テキスト全体。
    """
    return writer.get_text(text_uri_key)


@lambda_error_handler
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Extract fields Lambda ハンドラー。

    Args:
        event: Map の項目。`doc`、`collection`、`output_prefix` を持つ。
        context: Lambda コンテキスト。

    Returns:
        `status: completed`、要求した項目数 `requested`、根拠なしの項目数 `ungrounded_count`、
        `fields.json` の S3 URI `result`。項目ごとの値と根拠は返さず `fields.json` に書く
        （Map の集計が 256 KiB を超えないよう、状態遷移が運ぶのは文書あたり一定の小ささにする。
        Report が `fields.json` を読み直す）。Bedrock の失敗や解析の失敗は `status: failed` で返す
        （OCR の結果は捨てない）。

    Raises:
        InvalidConfiguration: コレクションに `fields` が無い場合（呼び出し側の誤り）。
        BedrockThrottled: Bedrock がスロットリングした（Step Functions が再試行する）。
    """
    fields = collection_fields(os.environ.get("COLLECTIONS_JSON", ""), event["collection"])
    if not fields:
        raise InvalidConfiguration(f"collection {event['collection']!r} has no fields to extract")
    doc = event["doc"]
    writer = OutputWriter.from_env()
    prefix = f"{event['output_prefix']}/{doc['doc_id']}"
    text = read_text(writer, f"{prefix}/text.txt")
    model_id = os.environ.get("BEDROCK_MODEL_ID", "apac.amazon.nova-pro-v1:0")

    request: dict[str, Any] = {
        "modelId": model_id,
        "system": [{"text": SYSTEM_PROMPT}],
        "messages": [{"role": "user", "content": [{"text": build_prompt(fields, text)}]}],
        "inferenceConfig": {"maxTokens": 1024},
    }
    temperature = os.environ.get("BEDROCK_TEMPERATURE")
    if temperature:
        request["inferenceConfig"]["temperature"] = float(temperature)

    try:
        response = _bedrock.converse(**request)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "Unknown")
        if code in THROTTLED_CODES:
            raise BedrockThrottled(f"{code}: {e}") from e
        logger.warning("Field extraction rejected for %s: %s", doc["doc_id"], code)
        return {"status": "failed", "error": code}
    try:
        blocks = response["output"]["message"]["content"]
        raw = "".join(b["text"] for b in blocks if "text" in b)
        grounded = ground_fields(fields, parse_model_json(raw), text)
    except (KeyError, TypeError, ValueError) as e:
        # モデルの出力が JSON として読めない。OCR の結果は捨てず、項目だけ未取得にする。
        logger.warning("Field extraction output unreadable for %s: %s", doc["doc_id"], type(e).__name__)
        return {"status": "failed", "error": "UnreadableModelOutput"}

    ungrounded = [name for name, entry in grounded.items() if not entry["grounded"]]
    writer.put_json(f"{prefix}/fields.json", {"model_id": model_id, "fields": grounded, "ungrounded": ungrounded})

    metrics = EmfMetrics(service="japanese-document-ocr-agent")
    metrics.set_dimension("Collection", str(event["collection"]))
    metrics.put_metric("FieldsExtracted", len(grounded) - len(ungrounded), "Count")
    metrics.put_metric("FieldsUngrounded", len(ungrounded), "Count")
    metrics.flush()
    return {
        "status": "completed",
        "requested": len(grounded),
        "ungrounded_count": len(ungrounded),
        "result": writer.build_s3_uri(f"{prefix}/fields.json"),
    }
