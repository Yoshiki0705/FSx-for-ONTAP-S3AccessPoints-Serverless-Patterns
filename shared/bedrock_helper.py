"""Bedrock Converse 共通ヘルパー

Amazon Bedrock のテキスト生成呼び出しをモデル非依存の Converse API に統一する
ラッパー。Nova / Claude / Titan など、モデルごとに異なる InvokeModel の
リクエスト/レスポンス形式の差異を吸収する。

なぜ Converse API か:
- モデル非依存の共通リクエスト/レスポンス形式（messages / inferenceConfig /
  output.message.content）を提供する。
- クロスリージョン推論プロファイル ID（例: apac./us./eu. 接頭辞）をそのまま
  ``model_id`` に渡せる。Amazon Nova や新しい Claude はオンデマンドでは
  ベアなモデル ID を呼び出せず、推論プロファイル ID が必須。
- 任意で Bedrock Guardrails を適用できる。

前提:
- 呼び出しリージョン（およびクロスリージョン推論プロファイルがルーティングする
  各リージョン）で、対象モデルの **モデルアクセスが有効化** されていること。
- 推論プロファイルの詳細・データレジデンシーの注意点は
  docs/bedrock-inference-profiles.md を参照。

Usage:
    from shared.bedrock_helper import converse_text, extract_json

    text = converse_text(
        model_id=os.environ["BEDROCK_MODEL_ID"],  # 例: apac.amazon.nova-lite-v1:0
        prompt="配送データを要約してください。",
        max_tokens=2048,
        temperature=0.3,
    )

    # JSON 出力を期待するプロンプトの場合
    record = extract_json(text)
"""

from __future__ import annotations

import json
import logging
from typing import Any

import boto3

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 2048
DEFAULT_TEMPERATURE = 0.3


def converse_text(
    model_id: str,
    prompt: str | None = None,
    *,
    messages: list[dict] | None = None,
    system: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    guardrail_id: str | None = None,
    guardrail_version: str = "DRAFT",
    client: Any | None = None,
) -> str:
    """Bedrock Converse API を呼び出し、生成テキストを返す（モデル非依存）。

    Args:
        model_id: モデル ID または推論プロファイル ID。Nova / 新しい Claude は
            オンデマンドではクロスリージョン推論プロファイル ID（apac./us./eu.
            接頭辞）が必須。
        prompt: 単一ユーザープロンプト。``messages`` を指定しない場合に使用。
        messages: Converse 形式の messages（``prompt`` より優先）。
            例: [{"role": "user", "content": [{"text": "..."}]}]
        system: システムプロンプト（任意）。
        max_tokens: 最大生成トークン数。
        temperature: サンプリング温度。
        guardrail_id: Bedrock Guardrail 識別子（任意。指定時のみ適用）。
        guardrail_version: Guardrail バージョン（デフォルト: "DRAFT"）。
        client: テスト用に注入する bedrock-runtime クライアント（任意）。

    Returns:
        str: 生成されたテキスト（content 内の text ブロックを連結）。
            出力が空の場合は空文字列を返す。

    Raises:
        ValueError: ``prompt`` と ``messages`` の両方が未指定の場合。
        botocore.exceptions.ClientError: Bedrock API 呼び出しが失敗した場合
            （呼び出し側で捕捉し、フォールバックすること）。
    """
    if messages is None:
        if prompt is None:
            raise ValueError("converse_text requires either 'prompt' or 'messages'")
        messages = [{"role": "user", "content": [{"text": prompt}]}]

    bedrock = client or boto3.client("bedrock-runtime")

    kwargs: dict[str, Any] = {
        "modelId": model_id,
        "messages": messages,
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
    }
    if system:
        kwargs["system"] = [{"text": system}]
    if guardrail_id:
        kwargs["guardrailConfig"] = {
            "guardrailIdentifier": guardrail_id,
            "guardrailVersion": guardrail_version,
        }

    response = bedrock.converse(**kwargs)
    return _extract_text(response)


def _extract_text(response: dict) -> str:
    """Converse レスポンスから text ブロックを連結して返す。

    output.message.content は複数ブロック（text / toolUse など）を含みうるため、
    text ブロックのみを抽出して連結する。空の場合は空文字列を返す。
    """
    content = (
        response.get("output", {})
        .get("message", {})
        .get("content", [])
    )
    texts = [block["text"] for block in content if isinstance(block, dict) and "text" in block]
    return "\n".join(texts).strip()


def extract_json(text: str) -> dict:
    """モデル出力テキストから JSON を抽出・解析する。

    自然言語やコードフェンス（```json ... ```）が混在するモデル出力から
    JSON 部分のみを取り出して解析する。解析に失敗した場合は空 dict を返す。

    Args:
        text: モデルが生成したテキスト。

    Returns:
        dict: 解析された JSON（失敗時は空 dict）。
    """
    try:
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            json_str = text.split("```")[1].split("```")[0].strip()
        else:
            json_str = text.strip()
        result = json.loads(json_str)
        return result if isinstance(result, dict) else {}
    except (json.JSONDecodeError, IndexError):
        return {}


def is_inference_profile_id(model_id: str) -> bool:
    """model_id がクロスリージョン推論プロファイル ID（geo 接頭辞付き）かを判定する。

    ARN 形式（arn:aws:bedrock:...:inference-profile/...）または geo 接頭辞
    （apac./us./eu./us-gov.）付き ID を推論プロファイルとみなす。
    """
    if model_id.startswith("arn:") and "inference-profile/" in model_id:
        return True
    return model_id.split(".", 1)[0] in {"apac", "us", "eu", "us-gov"}
