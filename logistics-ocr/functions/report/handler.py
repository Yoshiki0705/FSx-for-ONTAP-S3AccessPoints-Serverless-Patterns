"""物流 / サプライチェーン レポート生成 Lambda ハンドラ

Bedrock で配送ルート最適化レポートを生成し、S3 出力、SNS 通知する。

Environment Variables:
    OUTPUT_BUCKET: S3 出力バケット名
    BEDROCK_MODEL_ID: Bedrock モデル ID (デフォルト: amazon.nova-lite-v1:0)
    SNS_TOPIC_ARN: SNS トピック ARN
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import boto3

from shared.exceptions import lambda_error_handler

logger = logging.getLogger(__name__)


def _build_report_prompt(
    structured_records: list[dict],
    inventory_analyses: list[dict],
) -> str:
    """レポート生成用プロンプトを構築する

    Args:
        structured_records: 構造化配送レコードのリスト
        inventory_analyses: 在庫分析結果のリスト

    Returns:
        str: Bedrock プロンプト
    """
    records_summary = json.dumps(structured_records[:10], ensure_ascii=False, indent=2)
    inventory_summary = json.dumps(inventory_analyses[:5], ensure_ascii=False, indent=2)

    return f"""以下の配送データと倉庫在庫分析結果に基づいて、配送ルート最適化レポートを生成してください。

## 配送レコード（最大10件）:
{records_summary}

## 倉庫在庫分析:
{inventory_summary}

## レポート要件:
1. 配送パターンの分析（頻度、地域分布）
2. 在庫状況サマリー（棚占有率、アイテム分布）
3. ルート最適化の提案
4. コスト削減の機会
5. 改善アクションアイテム

日本語で詳細なレポートを生成してください。"""


@lambda_error_handler
def handler(event, context):
    """配送ルート最適化レポート生成（Bedrock）

    Input:
        {
            "structured_records": [...],
            "inventory_analyses": [...]
        }

    Output:
        {
            "status": "SUCCESS",
            "report_summary": "...",
            "output_key": "...",
            "notification_sent": true
        }
    """
    structured_records = event.get("structured_records", [])
    inventory_analyses = event.get("inventory_analyses", [])

    output_bucket = os.environ["OUTPUT_BUCKET"]
    model_id = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")

    logger.info(
        "Report generation started: records=%d, inventories=%d",
        len(structured_records),
        len(inventory_analyses),
    )

    # Bedrock でレポート生成
    bedrock_client = boto3.client("bedrock-runtime")
    prompt = _build_report_prompt(structured_records, inventory_analyses)

    try:
        bedrock_response = bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": 4096,
                    "temperature": 0.3,
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

    # 出力キー生成
    now = datetime.now(timezone.utc)
    output_key = f"reports/{now.strftime('%Y/%m/%d')}/logistics_report_{now.strftime('%H%M%S')}.json"

    # レポートデータ
    report_data = {
        "report_type": "logistics_route_optimization",
        "generated_at": now.isoformat(),
        "total_records_analyzed": len(structured_records),
        "total_inventories_analyzed": len(inventory_analyses),
        "report_text": report_text,
        "structured_records_summary": structured_records[:5],
        "inventory_summary": inventory_analyses[:3],
    }

    # S3 出力
    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=output_bucket,
        Key=output_key,
        Body=json.dumps(report_data, default=str, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
    )

    # SNS 通知
    notification_sent = False
    if sns_topic_arn:
        try:
            sns_client = boto3.client("sns")
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Subject="物流レポート生成完了",
                Message=(
                    f"配送ルート最適化レポートが生成されました。\n\n"
                    f"分析対象: 配送レコード {len(structured_records)} 件、"
                    f"在庫分析 {len(inventory_analyses)} 件\n"
                    f"出力先: s3://{output_bucket}/{output_key}"
                ),
            )
            notification_sent = True
        except Exception as e:
            logger.warning("SNS notification failed: %s", e)

    logger.info(
        "Report generation completed: output_key=%s, notification=%s",
        output_key,
        notification_sent,
    )

    return {
        "status": "SUCCESS",
        "report_summary": report_text[:500],
        "output_key": output_key,
        "notification_sent": notification_sent,
    }
