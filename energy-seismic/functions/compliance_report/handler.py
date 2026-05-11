"""エネルギー / 石油・ガス コンプライアンスレポート生成 Lambda ハンドラ

Amazon Bedrock で調査メタデータ、検出異常、規制推奨事項を含む
コンプライアンスレポートを生成する。Amazon Rekognition で坑井ログ
可視化画像（存在する場合）のパターン認識を実行する。

構造化出力を JSON で OutputWriter 経由で出力先に書き出し、SNS 通知を発行する。

Environment Variables:
    OUTPUT_DESTINATION: STANDARD_S3 or FSXN_S3AP (デフォルト: STANDARD_S3)
    OUTPUT_BUCKET: STANDARD_S3 モード時の出力バケット名
    OUTPUT_S3AP_ALIAS: FSXN_S3AP モード時の S3AP Alias
    OUTPUT_S3AP_PREFIX: FSXN_S3AP モード時のプレフィックス (デフォルト: ai-outputs/)
    BEDROCK_MODEL_ID: Bedrock モデル ID (デフォルト: amazon.nova-lite-v1:0)
    SNS_TOPIC_ARN: SNS トピック ARN
    S3_ACCESS_POINT: S3 AP Alias or ARN (画像読み取り用)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler
from shared.output_writer import OutputWriter

logger = logging.getLogger(__name__)

DEFAULT_BEDROCK_MODEL_ID = "amazon.nova-lite-v1:0"


def _build_compliance_prompt(
    metadata_results: list[dict],
    anomaly_results: list[dict],
    athena_results: dict,
) -> str:
    """コンプライアンスレポート生成プロンプトを構築する

    Args:
        metadata_results: SEG-Y メタデータ抽出結果リスト
        anomaly_results: 異常検知結果リスト
        athena_results: Athena 分析結果

    Returns:
        str: Bedrock に送信するプロンプト
    """
    anomaly_summary = athena_results.get("anomaly_summary", {})
    anomaly_by_well = athena_results.get("anomaly_by_well", [])
    anomaly_by_sensor = athena_results.get("anomaly_by_sensor", [])

    # メタデータサマリー構築
    metadata_lines = []
    for md in metadata_results[:10]:
        meta = md.get("metadata", {})
        metadata_lines.append(
            f"- {md.get('file_key', 'unknown')}: "
            f"survey={meta.get('survey_name', 'N/A')}, "
            f"coord={meta.get('coordinate_system', 'N/A')}, "
            f"interval={meta.get('sample_interval', 0)}μs, "
            f"traces={meta.get('trace_count', 0)}, "
            f"format={meta.get('data_format_code', 0)}"
        )

    # 異常サマリー構築
    anomaly_lines = []
    for ar in anomaly_results[:10]:
        anomaly_lines.append(
            f"- {ar.get('file_key', 'unknown')}: "
            f"anomalies={ar.get('total_anomalies', 0)}"
        )

    # 坑井別異常
    well_anomaly_lines = []
    for wa in anomaly_by_well[:10]:
        well_anomaly_lines.append(
            f"- {wa.get('file_key', 'unknown')}: "
            f"anomalies={wa.get('total_anomalies', 0)}, "
            f"primary_sensor={wa.get('primary_sensor', 'N/A')}"
        )

    # センサー別異常
    sensor_anomaly_lines = []
    for sa in anomaly_by_sensor[:10]:
        sensor_anomaly_lines.append(
            f"- {sa.get('sensor', 'unknown')}: "
            f"count={sa.get('occurrence_count', 0)}, "
            f"avg_std={sa.get('avg_std_deviations', 0)}, "
            f"max_std={sa.get('max_std_deviations', 0)}"
        )

    return (
        "You are a petroleum engineering compliance specialist. Based on the "
        "following seismic survey and well log analysis results, generate a "
        "comprehensive compliance report in Japanese.\n\n"
        "## 調査メタデータ\n\n"
        + "\n".join(metadata_lines)
        + "\n\n"
        "## 異常検知サマリー\n\n"
        f"- 総坑井数: {anomaly_summary.get('total_wells', 0)}\n"
        f"- 異常検出坑井数: {anomaly_summary.get('wells_with_anomalies', 0)}\n"
        f"- 総異常数: {anomaly_summary.get('total_anomalies_all', 0)}\n"
        f"- 坑井あたり平均異常数: {anomaly_summary.get('avg_anomalies_per_well', 0)}\n"
        f"- 坑井あたり最大異常数: {anomaly_summary.get('max_anomalies_per_well', 0)}\n\n"
        "## 坑井別異常\n\n"
        + "\n".join(well_anomaly_lines)
        + "\n\n"
        "## センサー別異常\n\n"
        + "\n".join(sensor_anomaly_lines)
        + "\n\n"
        "## レポート要件\n"
        "1. エグゼクティブサマリー（調査データの全体評価）\n"
        "2. 地震探査データの品質評価と問題点の指摘\n"
        "3. 坑井ログ異常の分析と潜在的リスクの評価\n"
        "4. センサー別異常パターンの分析\n"
        "5. 規制コンプライアンスの観点からの推奨事項\n"
        "6. 是正措置の提案と優先順位付け\n\n"
        "日本語でコンプライアンスレポートを生成してください。"
    )


def _invoke_bedrock(bedrock_client, model_id: str, prompt: str) -> str:
    """Bedrock InvokeModel でコンプライアンスレポートを生成する

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

    with xray_subsegment(


        name="bedrock_invokemodel",


        annotations={"service_name": "bedrock", "operation": "InvokeModel", "use_case": "energy-seismic"},


    ):


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


def _analyze_well_log_images(
    rekognition_client,
    s3ap,
    image_keys: list[str],
) -> list[dict]:
    """Rekognition で坑井ログ可視化画像のパターン認識を実行する

    Args:
        rekognition_client: boto3 Rekognition クライアント
        s3ap: S3ApHelper インスタンス
        image_keys: 画像ファイルキーのリスト

    Returns:
        list[dict]: 画像分析結果のリスト
    """
    results = []

    for image_key in image_keys:
        try:
            # S3 AP から画像を取得
            response = s3ap.get_object(image_key)
            image_bytes = response["Body"].read()

            # Rekognition でラベル検出
            rekog_response = rekognition_client.detect_labels(
                Image={"Bytes": image_bytes},
                MaxLabels=20,
                MinConfidence=70.0,
            )

            labels = [
                {
                    "name": label["Name"],
                    "confidence": round(label["Confidence"], 1),
                }
                for label in rekog_response.get("Labels", [])
            ]

            results.append({
                "image_key": image_key,
                "labels": labels,
                "label_count": len(labels),
            })

        except Exception as e:
            logger.warning(
                "Failed to analyze image %s: %s", image_key, str(e)
            )
            results.append({
                "image_key": image_key,
                "error": str(e),
                "labels": [],
                "label_count": 0,
            })

    return results


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """エネルギー / 石油・ガス コンプライアンスレポート生成 Lambda

    Bedrock でコンプライアンスレポートを生成し、Rekognition で
    坑井ログ可視化画像のパターン認識を実行する。
    構造化出力を JSON で S3 に書き出し、SNS 通知を発行する。

    Args:
        event: 統合入力
            {
                "metadata_results": [...],
                "anomaly_results": [...],
                "athena_results": {...},
                "image_keys": [...]  (optional)
            }

    Returns:
        dict: status, report, image_analysis, output_key, sns_message_id
    """
    sns_topic_arn = os.environ["SNS_TOPIC_ARN"]
    model_id = os.environ.get("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID)
    s3_access_point = os.environ.get("S3_ACCESS_POINT", "")

    metadata_results = event.get("metadata_results", [])
    anomaly_results = event.get("anomaly_results", [])
    athena_results = event.get("athena_results", {})
    image_keys = event.get("image_keys", [])

    logger.info(
        "Compliance Report generation started: model=%s, "
        "metadata_count=%d, anomaly_count=%d, image_count=%d",
        model_id,
        len(metadata_results),
        len(anomaly_results),
        len(image_keys),
    )

    # Bedrock でコンプライアンスレポート生成
    prompt = _build_compliance_prompt(
        metadata_results, anomaly_results, athena_results
    )
    bedrock_client = boto3.client("bedrock-runtime")
    compliance_report = _invoke_bedrock(bedrock_client, model_id, prompt)

    # Rekognition で坑井ログ可視化画像のパターン認識（画像がある場合）
    image_analysis: list[dict] = []
    if image_keys and s3_access_point:
        from shared.s3ap_helper import S3ApHelper

        s3ap = S3ApHelper(s3_access_point)
        rekognition_client = boto3.client("rekognition")
        image_analysis = _analyze_well_log_images(
            rekognition_client, s3ap, image_keys
        )

    # 構造化出力の構築
    report = {
        "compliance_report": compliance_report,
        "metadata_summary": {
            "total_surveys": len(metadata_results),
            "surveys": [
                {
                    "file_key": md.get("file_key", ""),
                    "survey_name": md.get("metadata", {}).get("survey_name", ""),
                }
                for md in metadata_results
            ],
        },
        "anomaly_summary": athena_results.get("anomaly_summary", {}),
        "image_analysis": image_analysis,
    }

    # 日付パーティション付き出力キー生成
    now = datetime.now(timezone.utc)
    output_key = (
        f"reports/{now.strftime('%Y/%m/%d')}"
        f"/compliance_report_{context.aws_request_id}.json"
    )

    # 構造化出力を OutputWriter 経由で出力先に書き出し
    output_data = {
        "execution_id": context.aws_request_id,
        "report": report,
        "generated_at": now.isoformat(),
    }

    writer = OutputWriter.from_env()
    writer.put_json(
        key=output_key,
        data=output_data,
    )

    output_uri = writer.build_s3_uri(output_key)
    logger.info("Output written: %s", output_uri)

    # SNS 通知発行
    anomaly_summary = athena_results.get("anomaly_summary", {})
    sns_message = (
        f"エネルギー / 石油・ガス コンプライアンスレポートが生成されました。\n\n"
        f"実行 ID: {context.aws_request_id}\n"
        f"調査データ数: {len(metadata_results)}\n"
        f"坑井ログ数: {len(anomaly_results)}\n"
        f"異常検出坑井数: {anomaly_summary.get('wells_with_anomalies', 0)}\n"
        f"総異常数: {anomaly_summary.get('total_anomalies_all', 0)}\n"
        f"画像分析数: {len(image_analysis)}\n"
        f"レポート: {output_uri}\n"
        f"出力先: {writer.target_description}\n"
        f"生成日時: {now.isoformat()}"
    )

    sns_client = boto3.client("sns")
    sns_response = sns_client.publish(
        TopicArn=sns_topic_arn,
        Subject="[Energy Seismic] コンプライアンスレポート生成完了",
        Message=sns_message,
    )

    logger.info(
        "Compliance Report generation completed: output_key=%s, "
        "metadata_count=%d, anomaly_count=%d, image_count=%d",
        output_key,
        len(metadata_results),
        len(anomaly_results),
        len(image_analysis),
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="compliance_report")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "energy-seismic"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return {
        "status": "SUCCESS",
        "report": report,
        "image_analysis": image_analysis,
        "output_key": output_key,
        "sns_message_id": sns_response["MessageId"],
    }
