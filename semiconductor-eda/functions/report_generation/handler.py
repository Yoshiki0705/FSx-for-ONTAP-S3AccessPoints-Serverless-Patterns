"""半導体 / EDA レポート生成 Lambda ハンドラ

DRC 集計結果を受け取り、Amazon Bedrock を使用して自然言語の
設計レビューサマリーを生成する。レポートを S3 に書き出し、
SNS 通知を発行する。

生成内容:
    - 設計ファイル全体の品質サマリー
    - cell_count 分布の分析
    - bounding_box 外れ値の詳細
    - 命名規則違反の一覧と推奨修正
    - 無効ファイルの対応推奨

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

DEFAULT_BEDROCK_MODEL_ID = "amazon.nova-lite-v1:0"


def _build_prompt(statistics: dict) -> str:
    """DRC 集計結果から設計レビュープロンプトを構築する

    Args:
        statistics: DRC 集計統計

    Returns:
        str: Bedrock に送信するプロンプト
    """
    cell_dist = statistics.get("cell_count_distribution", {})
    outliers = statistics.get("bounding_box_outliers", [])
    violations = statistics.get("naming_violations", [])
    invalid = statistics.get("invalid_files", 0)
    total = statistics.get("total_designs", 0)

    return (
        "You are a semiconductor design review engineer. Based on the "
        "following DRC (Design Rule Check) aggregation results from "
        "GDS/OASIS design files, generate a comprehensive design review "
        "summary in Japanese.\n\n"
        "## DRC 集計結果\n\n"
        f"### 設計ファイル総数: {total}\n\n"
        f"### セル数分布\n"
        f"- 最小: {cell_dist.get('min', 0)}\n"
        f"- 最大: {cell_dist.get('max', 0)}\n"
        f"- 平均: {cell_dist.get('avg', 0)}\n"
        f"- P95: {cell_dist.get('p95', 0)}\n\n"
        f"### バウンディングボックス外れ値 ({len(outliers)} 件)\n"
        f"{json.dumps(outliers, indent=2)}\n\n"
        f"### 命名規則違反 ({len(violations)} 件)\n"
        f"{json.dumps(violations, indent=2)}\n\n"
        f"### 無効ファイル数: {invalid}\n\n"
        "## レポート要件\n"
        "1. エグゼクティブサマリー（設計品質の全体評価）\n"
        "2. セル数分布の分析と異常値の指摘\n"
        "3. バウンディングボックス外れ値の詳細分析と推奨対応\n"
        "4. 命名規則違反の一覧と修正推奨\n"
        "5. 無効ファイルの対応推奨\n"
        "6. リスク評価（High/Medium/Low）\n\n"
        "日本語でレポートを生成してください。"
    )


def _invoke_bedrock(bedrock_client, model_id: str, prompt: str) -> str:
    """Bedrock InvokeModel で設計レビューサマリーを生成する

    Args:
        bedrock_client: boto3 Bedrock Runtime クライアント
        model_id: Bedrock モデル ID
        prompt: プロンプト文字列

    Returns:
        str: 生成されたレポートテキスト
    """
    body = json.dumps({
        "messages": [
            {"role": "user", "content": [{"text": prompt}]},
        ],
        "inferenceConfig": {
            "maxTokens": 4096,
            "temperature": 0.3,
        },
    })

    response = bedrock_client.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=body,
    )

    response_body = json.loads(response["body"].read())
    output = response_body.get("output", {})
    message = output.get("message", {})
    content_blocks = message.get("content", [])

    report_text = ""
    for block in content_blocks:
        if "text" in block:
            report_text += block["text"]

    return report_text


@lambda_error_handler
def handler(event, context):
    """半導体 / EDA レポート生成 Lambda

    DRC 集計結果を受け取り、Bedrock で設計レビューサマリーを生成。
    レポートを S3 に書き出し、SNS 通知を発行する。

    Args:
        event: DRC 集計 Lambda の出力
            {
                "status": "SUCCESS",
                "statistics": {...},
                "query_execution_id": "abc-123"
            }

    Returns:
        dict: report_key, sns_message_id, total_designs
    """
    output_bucket = os.environ["OUTPUT_BUCKET"]
    sns_topic_arn = os.environ["SNS_TOPIC_ARN"]
    model_id = os.environ.get("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID)

    statistics = event.get("statistics", {})
    query_execution_id = event.get(
        "query_execution_id", context.aws_request_id
    )

    logger.info(
        "Report Generation started: model=%s, query_execution_id=%s",
        model_id,
        query_execution_id,
    )

    # Bedrock で設計レビューサマリー生成
    prompt = _build_prompt(statistics)
    bedrock_client = boto3.client("bedrock-runtime")
    report_text = _invoke_bedrock(bedrock_client, model_id, prompt)

    # レポートを S3 に書き出し
    now = datetime.now(timezone.utc)
    report_key = (
        f"reports/{now.strftime('%Y/%m/%d')}"
        f"/eda-design-review-{context.aws_request_id}.md"
    )

    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=output_bucket,
        Key=report_key,
        Body=report_text.encode("utf-8"),
        ContentType="text/markdown; charset=utf-8",
    )

    logger.info("Report written to S3: s3://%s/%s", output_bucket, report_key)

    # SNS 通知発行
    total_designs = statistics.get("total_designs", 0)
    invalid_files = statistics.get("invalid_files", 0)
    outlier_count = len(statistics.get("bounding_box_outliers", []))
    violation_count = len(statistics.get("naming_violations", []))

    sns_message = (
        f"EDA 設計レビューレポートが生成されました。\n\n"
        f"実行 ID: {context.aws_request_id}\n"
        f"設計ファイル総数: {total_designs}\n"
        f"無効ファイル数: {invalid_files}\n"
        f"バウンディングボックス外れ値: {outlier_count} 件\n"
        f"命名規則違反: {violation_count} 件\n"
        f"レポート: s3://{output_bucket}/{report_key}\n"
        f"生成日時: {now.isoformat()}"
    )

    sns_client = boto3.client("sns")
    sns_response = sns_client.publish(
        TopicArn=sns_topic_arn,
        Subject="[EDA Design Review] レポート生成完了",
        Message=sns_message,
    )

    logger.info(
        "Report Generation completed: report=%s, total_designs=%d, "
        "invalid=%d, outliers=%d, violations=%d",
        report_key,
        total_designs,
        invalid_files,
        outlier_count,
        violation_count,
    )

    return {
        "report_key": report_key,
        "sns_message_id": sns_response["MessageId"],
        "total_designs": total_designs,
    }
