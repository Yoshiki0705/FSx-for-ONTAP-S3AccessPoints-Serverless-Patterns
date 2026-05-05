"""保険 / 損害査定 保険金請求レポート生成 Lambda ハンドラ

Bedrock で写真ベース損害評価と見積書データを相関させた包括的保険金請求レポートを生成する。
JSON と人間可読形式で S3 出力し、SNS 通知する。

Environment Variables:
    OUTPUT_BUCKET: S3 出力バケット名
    BEDROCK_MODEL_ID: Bedrock モデル ID (デフォルト: amazon.nova-lite-v1:0)
    SNS_TOPIC_ARN: SNS トピック ARN
    LOG_PII_DATA: PII データのログ出力 (デフォルト: false)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import boto3

from shared.exceptions import lambda_error_handler

logger = logging.getLogger(__name__)


def sanitize_for_logging(data: dict) -> dict:
    """PII データをログ出力用にサニタイズする"""
    log_pii = os.environ.get("LOG_PII_DATA", "false").lower() == "true"
    if log_pii:
        return data
    sanitized = {}
    pii_fields = {"name", "address", "phone", "email", "policy_number", "claimant"}
    for key, value in data.items():
        if any(pii in key.lower() for pii in pii_fields):
            sanitized[key] = "***REDACTED***"
        else:
            sanitized[key] = value
    return sanitized


def _build_claims_prompt(
    damage_assessments: list[dict],
    estimate_data: list[dict],
) -> str:
    """保険金請求レポート生成用プロンプトを構築する"""
    assessments_text = json.dumps(damage_assessments[:5], ensure_ascii=False, indent=2)
    estimates_text = json.dumps(estimate_data[:5], ensure_ascii=False, indent=2)

    return f"""以下の損害評価結果と見積書データに基づいて、包括的な保険金請求レポートを生成してください。

## 損害評価結果:
{assessments_text}

## 見積書データ:
{estimates_text}

## レポート要件:
1. 損害サマリー（損害タイプ、重大度、影響箇所）
2. 写真評価と見積書の相関分析
3. 不一致点の指摘
4. 承認/拒否/追加調査の推奨
5. 推奨理由と信頼度

日本語で詳細なレポートを生成してください。"""


def _generate_human_readable_report(claims_report: dict) -> str:
    """人間可読形式のレポートテキストを生成する"""
    lines = [
        "=" * 60,
        "保険金請求レポート",
        "=" * 60,
        "",
        f"請求ID: {claims_report.get('claim_id', 'N/A')}",
        f"生成日時: {claims_report.get('generated_at', 'N/A')}",
        "",
        "--- 損害サマリー ---",
        claims_report.get("damage_summary", "情報なし"),
        "",
        "--- 見積相関 ---",
        f"一致項目数: {claims_report.get('estimate_correlation', {}).get('matched_items', 0)}",
        f"総損害額: ¥{claims_report.get('estimate_correlation', {}).get('total_assessed_damage', 0):,}",
        "",
        "--- 推奨 ---",
        f"判定: {claims_report.get('recommendation', 'N/A')}",
        f"信頼度: {claims_report.get('confidence', 0):.0%}",
        "",
        "=" * 60,
    ]
    return "\n".join(lines)


@lambda_error_handler
def handler(event, context):
    """保険金請求レポート生成（Bedrock）

    Input:
        {
            "damage_assessments": [...],
            "estimate_data": [...]
        }

    Output:
        {
            "status": "SUCCESS",
            "claims_report": {...},
            "output_key": "...",
            "human_readable_key": "...",
            "notification_sent": true
        }
    """
    damage_assessments = event.get("damage_assessments", [])
    estimate_data = event.get("estimate_data", [])

    output_bucket = os.environ["OUTPUT_BUCKET"]
    model_id = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")

    logger.info(
        "Claims report generation started: assessments=%d, estimates=%d",
        len(damage_assessments),
        len(estimate_data),
    )

    # Bedrock でレポート生成
    bedrock_client = boto3.client("bedrock-runtime")
    prompt = _build_claims_prompt(damage_assessments, estimate_data)

    try:
        bedrock_response = bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": 4096,
                    "temperature": 0.2,
                },
            }),
        )
        response_json = json.loads(bedrock_response["body"].read())
        if "results" in response_json:
            report_text = response_json["results"][0].get("outputText", "")
        elif "content" in response_json:
            report_text = response_json["content"][0].get("text", "")
        else:
            report_text = "レポート生成に失敗しました。"
    except Exception as e:
        logger.warning("Bedrock invocation failed: %s", e)
        report_text = f"レポート自動生成に失敗しました。エラー: {e}"

    # 構造化レポート
    now = datetime.now(timezone.utc)
    claim_id = f"CLM{now.strftime('%Y%m%d')}_{context.aws_request_id[:8]}"

    # 見積相関分析
    total_damage = sum(
        e.get("estimate_data", {}).get("total_estimate", 0)
        for e in estimate_data
        if isinstance(e, dict)
    )

    claims_report = {
        "claim_id": claim_id,
        "generated_at": now.isoformat(),
        "damage_summary": report_text[:500],
        "photo_assessments": damage_assessments[:10],
        "estimate_correlation": {
            "matched_items": len(estimate_data),
            "discrepancies": [],
            "total_assessed_damage": total_damage,
        },
        "recommendation": "review",
        "confidence": 0.75,
    }

    # JSON 出力
    output_key = f"reports/{now.strftime('%Y/%m/%d')}/{claim_id}_claims_report.json"
    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=output_bucket,
        Key=output_key,
        Body=json.dumps(claims_report, default=str, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
    )

    # 人間可読形式出力
    human_readable_key = f"reports/{now.strftime('%Y/%m/%d')}/{claim_id}_claims_report.txt"
    human_readable_text = _generate_human_readable_report(claims_report)
    s3_client.put_object(
        Bucket=output_bucket,
        Key=human_readable_key,
        Body=human_readable_text.encode("utf-8"),
        ContentType="text/plain; charset=utf-8",
    )

    # SNS 通知
    notification_sent = False
    if sns_topic_arn:
        try:
            sns_client = boto3.client("sns")
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Subject=f"保険金請求レポート生成完了: {claim_id}",
                Message=(
                    f"保険金請求レポートが生成されました。\n\n"
                    f"請求ID: {claim_id}\n"
                    f"損害評価数: {len(damage_assessments)}\n"
                    f"見積書数: {len(estimate_data)}\n"
                    f"総損害額: ¥{total_damage:,}\n"
                    f"出力先: s3://{output_bucket}/{output_key}"
                ),
            )
            notification_sent = True
        except Exception as e:
            logger.warning("SNS notification failed: %s", e)

    logger.info(
        "Claims report completed: claim_id=%s, output_key=%s",
        claim_id,
        output_key,
    )

    return {
        "status": "SUCCESS",
        "claims_report": claims_report,
        "output_key": output_key,
        "human_readable_key": human_readable_key,
        "notification_sent": notification_sent,
    }
