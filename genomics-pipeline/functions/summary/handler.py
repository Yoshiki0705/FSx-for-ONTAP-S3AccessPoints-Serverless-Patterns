"""ゲノミクス / バイオインフォマティクス サマリー生成 Lambda ハンドラ

QC 結果、バリアント統計、Athena 分析結果を統合し、Amazon Bedrock で
研究サマリーを生成する。Cross_Region_Client で Comprehend Medical
DetectEntitiesV2 を実行し、バイオメディカルエンティティ（遺伝子名、
疾患、薬剤）を抽出する。

構造化出力を JSON で S3 に書き出し、SNS 通知を発行する。

セキュリティ:
    - PHI（保護対象医療情報）はログに出力しない
    - sanitize_for_logging パターンで機密データをマスクする

Environment Variables:
    OUTPUT_BUCKET: S3 出力バケット名
    BEDROCK_MODEL_ID: Bedrock モデル ID (デフォルト: amazon.nova-lite-v1:0)
    SNS_TOPIC_ARN: SNS トピック ARN
    CROSS_REGION: クロスリージョンターゲット (デフォルト: us-east-1)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import boto3

from shared.cross_region_client import CrossRegionClient, CrossRegionConfig
from shared.exceptions import lambda_error_handler

logger = logging.getLogger(__name__)

DEFAULT_BEDROCK_MODEL_ID = "amazon.nova-lite-v1:0"
DEFAULT_CROSS_REGION = "us-east-1"


def sanitize_for_logging(data: dict) -> dict:
    """ログ出力用にデータをサニタイズする

    PHI（保護対象医療情報）を含む可能性のあるフィールドをマスクする。

    Args:
        data: サニタイズ対象のデータ

    Returns:
        dict: サニタイズ済みデータ
    """
    sensitive_keys = {
        "research_summary",
        "biomedical_entities",
        "genes",
        "diseases",
        "medications",
        "patient_id",
        "sample_id",
    }
    sanitized = {}
    for key, value in data.items():
        if key in sensitive_keys:
            if isinstance(value, str):
                sanitized[key] = f"[REDACTED: {len(value)} chars]"
            elif isinstance(value, (list, dict)):
                sanitized[key] = f"[REDACTED: {type(value).__name__}]"
            else:
                sanitized[key] = "[REDACTED]"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_for_logging(value)
        else:
            sanitized[key] = value
    return sanitized


def _build_research_prompt(
    qc_results: list[dict],
    variant_stats: list[dict],
    athena_results: dict,
) -> str:
    """研究サマリー生成プロンプトを構築する

    Args:
        qc_results: QC 結果リスト
        variant_stats: バリアント統計リスト
        athena_results: Athena 分析結果

    Returns:
        str: Bedrock に送信するプロンプト
    """
    quality_summary = athena_results.get("quality_summary", {})
    below_threshold = athena_results.get("below_threshold_sample_names", [])

    # QC サマリー構築
    qc_summary_lines = []
    for qc in qc_results[:10]:  # 最大 10 サンプル
        metrics = qc.get("quality_metrics", {})
        qc_summary_lines.append(
            f"- {qc.get('file_key', 'unknown')}: "
            f"reads={metrics.get('total_reads', 0)}, "
            f"quality={metrics.get('average_quality_score', 0)}, "
            f"GC={metrics.get('gc_content_percentage', 0)}%"
        )

    # バリアント統計サマリー構築
    variant_summary_lines = []
    for vs in variant_stats[:10]:  # 最大 10 サンプル
        stats = vs.get("variant_statistics", {})
        variant_summary_lines.append(
            f"- {vs.get('file_key', 'unknown')}: "
            f"variants={stats.get('total_variants', 0)}, "
            f"SNP={stats.get('snp_count', 0)}, "
            f"indel={stats.get('indel_count', 0)}, "
            f"Ti/Tv={stats.get('ti_tv_ratio', 0)}"
        )

    return (
        "You are a bioinformatics research scientist. Based on the following "
        "genomics data analysis results, generate a comprehensive research "
        "summary in Japanese.\n\n"
        "## 品質チェック結果\n\n"
        f"### 全体統計\n"
        f"- サンプル総数: {quality_summary.get('total_samples', 0)}\n"
        f"- 平均品質スコア: {quality_summary.get('average_quality_score', 0)}\n"
        f"- 最小品質スコア: {quality_summary.get('min_quality_score', 0)}\n"
        f"- 最大品質スコア: {quality_summary.get('max_quality_score', 0)}\n"
        f"- 平均 GC 含有率: {quality_summary.get('average_gc_content', 0)}%\n\n"
        f"### サンプル別 QC\n"
        + "\n".join(qc_summary_lines)
        + "\n\n"
        f"### 品質閾値未満サンプル ({len(below_threshold)} 件)\n"
        + (", ".join(below_threshold) if below_threshold else "なし")
        + "\n\n"
        "## バリアント統計\n\n"
        + "\n".join(variant_summary_lines)
        + "\n\n"
        "## レポート要件\n"
        "1. エグゼクティブサマリー（データ品質の全体評価）\n"
        "2. シーケンシング品質の分析と問題サンプルの指摘\n"
        "3. バリアントコール統計の分析（SNP/Indel 比率、Ti/Tv 比率の評価）\n"
        "4. GC 含有率の分布分析\n"
        "5. 品質閾値未満サンプルの対応推奨\n"
        "6. 次のステップの提案\n\n"
        "日本語でレポートを生成してください。"
    )


def _invoke_bedrock(bedrock_client, model_id: str, prompt: str) -> str:
    """Bedrock InvokeModel で研究サマリーを生成する

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


def _extract_biomedical_entities(
    cross_region_client: CrossRegionClient,
    text: str,
) -> dict:
    """Comprehend Medical でバイオメディカルエンティティを抽出する

    研究サマリーテキストから遺伝子名、疾患、薬剤を抽出する。

    Args:
        cross_region_client: CrossRegionClient インスタンス
        text: 解析対象テキスト

    Returns:
        dict: バイオメディカルエンティティ（genes, diseases, medications）
    """
    entities = {
        "genes": [],
        "diseases": [],
        "medications": [],
    }

    try:
        # Comprehend Medical のテキスト長制限（20,000 文字）
        truncated_text = text[:20000] if len(text) > 20000 else text

        response = cross_region_client.detect_entities_v2(truncated_text)

        for entity in response.get("Entities", []):
            category = entity.get("Category", "")
            entity_type = entity.get("Type", "")
            entity_text = entity.get("Text", "")
            score = entity.get("Score", 0.0)

            # 信頼度 0.7 以上のエンティティのみ抽出
            if score < 0.7:
                continue

            if category == "TEST_TREATMENT_PROCEDURE" and entity_type == "PROCEDURE_NAME":
                # 遺伝子名は PROCEDURE_NAME として検出されることがある
                if not any(g == entity_text for g in entities["genes"]):
                    entities["genes"].append(entity_text)
            elif category == "MEDICAL_CONDITION":
                if not any(d == entity_text for d in entities["diseases"]):
                    entities["diseases"].append(entity_text)
            elif category == "MEDICATION":
                if not any(m == entity_text for m in entities["medications"]):
                    entities["medications"].append(entity_text)
            elif category == "ANATOMY" and "gene" in entity_text.lower():
                if not any(g == entity_text for g in entities["genes"]):
                    entities["genes"].append(entity_text)
            elif category == "TEST_TREATMENT_PROCEDURE" and entity_type == "TEST_NAME":
                # 遺伝子検査名も遺伝子として扱う
                if not any(g == entity_text for g in entities["genes"]):
                    entities["genes"].append(entity_text)

    except Exception as e:
        logger.warning(
            "Comprehend Medical entity extraction failed: %s", str(e)
        )
        # エンティティ抽出失敗はワークフローを停止しない

    return entities


@lambda_error_handler
def handler(event, context):
    """ゲノミクス / バイオインフォマティクス サマリー生成 Lambda

    QC 結果、バリアント統計、Athena 分析結果を統合し、
    Bedrock で研究サマリーを生成する。Comprehend Medical で
    バイオメディカルエンティティを抽出し、構造化出力を JSON で
    S3 に書き出す。

    Args:
        event: 統合入力
            {
                "qc_results": [...],
                "variant_stats": [...],
                "athena_results": {...}
            }

    Returns:
        dict: status, summary, output_key
    """
    output_bucket = os.environ["OUTPUT_BUCKET"]
    sns_topic_arn = os.environ["SNS_TOPIC_ARN"]
    model_id = os.environ.get("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID)
    cross_region = os.environ.get("CROSS_REGION", DEFAULT_CROSS_REGION)

    qc_results = event.get("qc_results", [])
    variant_stats = event.get("variant_stats", [])
    athena_results = event.get("athena_results", {})

    logger.info(
        "Summary Generation started: model=%s, cross_region=%s, "
        "qc_count=%d, variant_count=%d",
        model_id,
        cross_region,
        len(qc_results),
        len(variant_stats),
    )

    # Bedrock で研究サマリー生成
    prompt = _build_research_prompt(qc_results, variant_stats, athena_results)
    bedrock_client = boto3.client("bedrock-runtime")
    research_summary = _invoke_bedrock(bedrock_client, model_id, prompt)

    # Cross-Region Comprehend Medical でバイオメディカルエンティティ抽出
    cross_region_config = CrossRegionConfig(
        target_region=cross_region,
        services=["comprehendmedical"],
    )
    cross_region_client = CrossRegionClient(cross_region_config)
    biomedical_entities = _extract_biomedical_entities(
        cross_region_client, research_summary
    )

    # 閾値未満サンプル名の取得
    below_threshold_samples = athena_results.get(
        "below_threshold_sample_names", []
    )

    # 構造化出力の構築
    summary = {
        "quality_metrics": [
            {
                "file_key": qc.get("file_key", ""),
                "metrics": qc.get("quality_metrics", {}),
            }
            for qc in qc_results
        ],
        "variant_statistics": [
            {
                "file_key": vs.get("file_key", ""),
                "statistics": vs.get("variant_statistics", {}),
            }
            for vs in variant_stats
        ],
        "biomedical_entities": biomedical_entities,
        "research_summary": research_summary,
        "below_threshold_samples": below_threshold_samples,
    }

    # 日付パーティション付き出力キー生成
    now = datetime.now(timezone.utc)
    output_key = (
        f"summaries/{now.strftime('%Y/%m/%d')}"
        f"/research_summary_{context.aws_request_id}.json"
    )

    # 構造化出力を S3 に書き出し
    output_data = {
        "execution_id": context.aws_request_id,
        "summary": summary,
        "generated_at": now.isoformat(),
    }

    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=output_bucket,
        Key=output_key,
        Body=json.dumps(output_data, default=str, ensure_ascii=False).encode(
            "utf-8"
        ),
        ContentType="application/json; charset=utf-8",
    )

    # PHI をマスクしてログ出力
    sanitized = sanitize_for_logging(summary)
    logger.info(
        "Summary output (sanitized): %s",
        json.dumps(sanitized, default=str, ensure_ascii=False)[:500],
    )

    # SNS 通知発行
    sns_message = (
        f"ゲノミクス研究サマリーが生成されました。\n\n"
        f"実行 ID: {context.aws_request_id}\n"
        f"QC サンプル数: {len(qc_results)}\n"
        f"バリアント統計数: {len(variant_stats)}\n"
        f"品質閾値未満サンプル: {len(below_threshold_samples)} 件\n"
        f"検出エンティティ: 遺伝子 {len(biomedical_entities['genes'])} 件, "
        f"疾患 {len(biomedical_entities['diseases'])} 件, "
        f"薬剤 {len(biomedical_entities['medications'])} 件\n"
        f"レポート: s3://{output_bucket}/{output_key}\n"
        f"生成日時: {now.isoformat()}"
    )

    sns_client = boto3.client("sns")
    sns_response = sns_client.publish(
        TopicArn=sns_topic_arn,
        Subject="[Genomics Research] サマリー生成完了",
        Message=sns_message,
    )

    logger.info(
        "Summary Generation completed: output_key=%s, "
        "qc_count=%d, variant_count=%d, "
        "below_threshold=%d, entities=%d",
        output_key,
        len(qc_results),
        len(variant_stats),
        len(below_threshold_samples),
        sum(len(v) for v in biomedical_entities.values()),
    )

    return {
        "status": "SUCCESS",
        "summary": summary,
        "output_key": output_key,
        "sns_message_id": sns_response["MessageId"],
    }
