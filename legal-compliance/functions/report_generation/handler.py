"""法務・コンプライアンス Report Generation Lambda ハンドラ

Athena 分析結果を受け取り、Amazon Bedrock を使用して
自然言語のコンプライアンスレポートを生成する。
レポートを S3 AP に書き出し、SNS 通知を発行する。

Environment Variables:
    S3_ACCESS_POINT_OUTPUT: S3 AP Alias or ARN (出力書き込み用)
    SNS_TOPIC_ARN: SNS トピック ARN
    BEDROCK_MODEL_ID: Bedrock モデル ID (デフォルト: amazon.nova-lite-v1:0)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import boto3

from shared.exceptions import lambda_error_handler
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger(__name__)

DEFAULT_BEDROCK_MODEL_ID = "amazon.nova-lite-v1:0"


def _build_prompt(query_results: dict) -> str:
    """Athena 分析結果からレポート生成プロンプトを構築する

    Args:
        query_results: Athena クエリ結果の辞書

    Returns:
        str: Bedrock に送信するプロンプト
    """
    findings_summary = []

    for query_name, result in query_results.items():
        rows = result.get("rows", [])
        status = result.get("status", "UNKNOWN")
        findings_summary.append(
            f"- {query_name}: {len(rows)} findings (status: {status})"
        )

    findings_text = "\n".join(findings_summary)

    return (
        "You are a compliance analyst. Based on the following file server audit "
        "findings from an FSx for NetApp ONTAP environment, generate a concise "
        "compliance report in Japanese.\n\n"
        "## Audit Findings Summary\n\n"
        f"{findings_text}\n\n"
        "## Detailed Findings\n\n"
        f"{json.dumps(query_results, indent=2, default=str)}\n\n"
        "## Report Requirements\n"
        "1. Executive summary of compliance posture\n"
        "2. Critical findings requiring immediate action\n"
        "3. Recommendations for remediation\n"
        "4. Risk assessment (High/Medium/Low)\n\n"
        "Generate the report in Japanese."
    )


def _invoke_bedrock(bedrock_client, model_id: str, prompt: str) -> str:
    """Bedrock InvokeModel でレポートを生成する

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
    # Extract text from Bedrock response
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
    """Report Generation Lambda

    Athena 分析結果を受け取り、Bedrock でコンプライアンスレポートを生成。
    レポートを S3 に書き出し、SNS 通知を発行する。

    Args:
        event: Athena Analysis Lambda の出力
            {"query_results": dict, "execution_id": str}

    Returns:
        dict: report_bucket, report_key, sns_message_id
    """
    output_ap = os.environ["S3_ACCESS_POINT_OUTPUT"]
    s3ap_output = S3ApHelper(output_ap)
    sns_topic_arn = os.environ["SNS_TOPIC_ARN"]
    model_id = os.environ.get("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID)

    query_results = event.get("query_results", {})
    execution_id = event.get("execution_id", context.aws_request_id)

    logger.info(
        "Report Generation started: model=%s, execution_id=%s",
        model_id,
        execution_id,
    )

    # Bedrock でレポート生成
    prompt = _build_prompt(query_results)
    bedrock_client = boto3.client("bedrock-runtime")
    report_text = _invoke_bedrock(bedrock_client, model_id, prompt)

    # レポートを S3 に書き出し
    now = datetime.now(timezone.utc)
    report_key = (
        f"reports/{now.strftime('%Y/%m/%d')}"
        f"/compliance-report-{execution_id}.md"
    )

    s3ap_output.put_object(
        key=report_key,
        body=report_text.encode("utf-8"),
        content_type="text/markdown; charset=utf-8",
    )

    logger.info("Report written to S3 AP: %s", report_key)

    # SNS 通知発行
    total_findings = sum(
        len(r.get("rows", [])) for r in query_results.values()
    )
    sns_message = (
        f"コンプライアンスレポートが生成されました。\n\n"
        f"実行 ID: {execution_id}\n"
        f"検出件数: {total_findings}\n"
        f"レポート: {report_key}\n"
        f"生成日時: {now.isoformat()}"
    )

    sns_client = boto3.client("sns")
    sns_response = sns_client.publish(
        TopicArn=sns_topic_arn,
        Subject="[FSxN Compliance] レポート生成完了",
        Message=sns_message,
    )

    logger.info(
        "Report Generation completed: report=%s, findings=%d",
        report_key,
        total_findings,
    )

    return {
        "report_key": report_key,
        "sns_message_id": sns_response["MessageId"],
        "total_findings": total_findings,
    }
