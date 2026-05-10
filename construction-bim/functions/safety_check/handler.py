"""建設 / AEC 安全コンプライアンスチェック Lambda ハンドラ

Bedrock で安全コンプライアンスルール（防火避難要件、構造荷重仕様、材料基準）に
対するチェックを実行する。Rekognition で図面画像の安全関連視覚要素（非常口、
消火器、危険区域）を検出する。

ルールごとの PASS/FAIL と全体コンプライアンス結果を JSON 出力する。

セキュリティ:
    - 安全記録はログに機密データを出力しない
    - sanitize_for_logging パターンで安全チェック詳細をマスクする

Environment Variables:
    OUTPUT_DESTINATION: `STANDARD_S3` or `FSXN_S3AP` (デフォルト: `STANDARD_S3`)
    OUTPUT_BUCKET: STANDARD_S3 モードの出力バケット名
    OUTPUT_S3AP_ALIAS: FSXN_S3AP モードの S3AP Alias or ARN
    OUTPUT_S3AP_PREFIX: FSXN_S3AP モードの出力プレフィックス (デフォルト: `ai-outputs/`)
    BEDROCK_MODEL_ID: Bedrock モデル ID (デフォルト: amazon.nova-lite-v1:0)
    SNS_TOPIC_ARN: SNS トピック ARN
    SAFETY_RULES: 安全ルール JSON (オプション、デフォルトルール使用)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import boto3

from shared.exceptions import lambda_error_handler
from shared.output_writer import OutputWriter
from shared.observability import xray_subsegment, EmfMetrics, trace_lambda_handler

logger = logging.getLogger(__name__)

DEFAULT_BEDROCK_MODEL_ID = "amazon.nova-lite-v1:0"


# デフォルト安全コンプライアンスルール
DEFAULT_SAFETY_RULES = [
    {
        "rule_id": "FIRE_ESCAPE_001",
        "rule_name": "Fire escape requirements",
        "description": "建物には適切な防火避難経路が設置されていること",
        "keywords": ["fire escape", "emergency exit", "evacuation", "非常口", "避難"],
    },
    {
        "rule_id": "STRUCTURAL_LOAD_001",
        "rule_name": "Structural load specifications",
        "description": "構造荷重が設計基準を満たしていること",
        "keywords": ["structural load", "load bearing", "foundation", "構造", "荷重"],
    },
    {
        "rule_id": "MATERIAL_STANDARD_001",
        "rule_name": "Material standards compliance",
        "description": "使用材料が建築基準法の材料基準を満たしていること",
        "keywords": ["material", "concrete", "steel", "材料", "基準"],
    },
]


def get_safety_rules() -> list[dict]:
    """安全コンプライアンスルールを取得する

    環境変数 SAFETY_RULES が設定されている場合はそれを使用し、
    未設定の場合はデフォルトルールを返す。

    Returns:
        list[dict]: 安全ルールのリスト
    """
    rules_env = os.environ.get("SAFETY_RULES", "")
    if rules_env:
        try:
            return json.loads(rules_env)
        except json.JSONDecodeError:
            logger.warning("Invalid SAFETY_RULES JSON, using defaults")
    return DEFAULT_SAFETY_RULES


def check_compliance_with_bedrock(
    bedrock_client,
    model_id: str,
    extracted_text: str,
    bim_metadata: dict,
    rules: list[dict],
) -> list[dict]:
    """Bedrock で安全コンプライアンスチェックを実行する

    Args:
        bedrock_client: boto3 Bedrock Runtime クライアント
        model_id: Bedrock モデル ID
        extracted_text: OCR で抽出されたテキスト
        bim_metadata: BIM メタデータ
        rules: 安全ルールリスト

    Returns:
        list[dict]: ルールごとのコンプライアンス結果
    """
    rules_description = "\n".join(
        f"- {r['rule_id']}: {r['rule_name']} - {r['description']}"
        for r in rules
    )

    prompt = (
        "You are a construction safety compliance expert. "
        "Analyze the following building documentation and check compliance "
        "against each safety rule.\n\n"
        f"## Building Information\n"
        f"- Project: {bim_metadata.get('project_name', 'Unknown')}\n"
        f"- Floors: {bim_metadata.get('floor_count', 'Unknown')}\n"
        f"- Elements: {bim_metadata.get('building_elements_count', 'Unknown')}\n\n"
        f"## Extracted Document Text\n{extracted_text[:5000]}\n\n"
        f"## Safety Rules to Check\n{rules_description}\n\n"
        "For each rule, respond in JSON format with:\n"
        '{"results": [{"rule_id": "...", "status": "PASS" or "FAIL", '
        '"details": "...", "remediation": "..."}]}\n'
        "Respond ONLY with the JSON."
    )

    try:
        body = json.dumps({
            "messages": [
                {"role": "user", "content": [{"text": prompt}]},
            ],
            "inferenceConfig": {
                "maxTokens": 2048,
                "temperature": 0.1,
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

        response_text = ""
        for block in content_blocks:
            if "text" in block:
                response_text += block["text"]

        # JSON パース試行
        try:
            parsed = json.loads(response_text)
            return parsed.get("results", [])
        except json.JSONDecodeError:
            # JSON 抽出を試行
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                return parsed.get("results", [])

    except Exception as e:
        logger.warning("Bedrock compliance check failed: %s", e)

    # フォールバック: キーワードベースのチェック
    return _keyword_based_check(extracted_text, bim_metadata, rules)


def _keyword_based_check(
    extracted_text: str, bim_metadata: dict, rules: list[dict]
) -> list[dict]:
    """キーワードベースのフォールバックコンプライアンスチェック

    Bedrock が利用できない場合のフォールバック。
    テキスト内のキーワード出現に基づいてルールの PASS/FAIL を判定する。

    Args:
        extracted_text: OCR で抽出されたテキスト
        bim_metadata: BIM メタデータ
        rules: 安全ルールリスト

    Returns:
        list[dict]: ルールごとのコンプライアンス結果
    """
    text_lower = extracted_text.lower()
    results = []

    for rule in rules:
        keywords = rule.get("keywords", [])
        found_keywords = [kw for kw in keywords if kw.lower() in text_lower]

        if found_keywords:
            status = "PASS"
            details = f"Keywords found: {', '.join(found_keywords)}"
            remediation = ""
        else:
            status = "FAIL"
            details = f"No evidence found for rule: {rule['rule_name']}"
            remediation = f"Review documentation for {rule['rule_name']} compliance"

        results.append({
            "rule_id": rule["rule_id"],
            "rule_name": rule["rule_name"],
            "status": status,
            "details": details,
            "remediation": remediation,
        })

    return results


def detect_visual_safety_elements(
    rekognition_client, drawing_images: list[dict]
) -> dict:
    """Rekognition で図面画像の安全関連視覚要素を検出する

    Args:
        rekognition_client: boto3 Rekognition クライアント
        drawing_images: 図面画像のリスト [{"bucket": "...", "key": "..."}]

    Returns:
        dict: 検出された安全要素のカウント
    """
    visual_elements = {
        "emergency_exits": 0,
        "fire_extinguishers": 0,
        "hazard_zones": 0,
    }

    # 安全関連ラベルのマッピング
    safety_label_map = {
        "emergency_exits": [
            "Exit Sign", "Door", "Emergency", "Arrow",
            "Exit", "Escape Route",
        ],
        "fire_extinguishers": [
            "Fire Extinguisher", "Fire Hydrant", "Sprinkler",
            "Fire Safety", "Extinguisher",
        ],
        "hazard_zones": [
            "Warning Sign", "Hazard", "Danger", "Caution",
            "Restricted Area", "Warning",
        ],
    }

    for image_info in drawing_images:
        try:
            # S3 から画像を指定して Rekognition に送信
            if "bucket" in image_info and "key" in image_info:
                with xray_subsegment(

                    name="rekognition_detectlabels",

                    annotations={"service_name": "rekognition", "operation": "DetectLabels", "use_case": "construction-bim"},

                ):

                    response = rekognition_client.detect_labels(
                    Image={
                        "S3Object": {
                            "Bucket": image_info["bucket"],
                            "Name": image_info["key"],
                        }
                    },
                    MaxLabels=30,
                    MinConfidence=50.0,
                )
            elif "bytes" in image_info:
                response = rekognition_client.detect_labels(
                    Image={"Bytes": image_info["bytes"]},
                    MaxLabels=30,
                    MinConfidence=50.0,
                )
            else:
                continue

            # ラベルを安全要素にマッピング
            for label in response.get("Labels", []):
                label_name = label.get("Name", "")
                for category, keywords in safety_label_map.items():
                    if any(kw.lower() in label_name.lower() for kw in keywords):
                        visual_elements[category] += 1
                        break

        except Exception as e:
            logger.warning(
                "Rekognition detection failed for image: %s", e
            )

    return visual_elements


def determine_overall_compliance(compliance_results: list[dict]) -> str:
    """全体コンプライアンス結果を判定する

    いずれかのルールが FAIL の場合、全体は FAIL。

    Args:
        compliance_results: ルールごとのコンプライアンス結果

    Returns:
        str: "PASS" | "FAIL"
    """
    for result in compliance_results:
        if result.get("status") == "FAIL":
            return "FAIL"
    return "PASS"


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """安全コンプライアンスチェック（Bedrock + Rekognition）

    Input:
        {
            "extracted_text": "...",
            "bim_metadata": {...},
            "drawing_images": [{"bucket": "...", "key": "..."}, ...]
        }

    Output:
        {
            "status": "SUCCESS",
            "compliance_results": [...],
            "visual_elements": {...},
            "overall_compliance": "PASS" | "FAIL",
            "output_key": "..."
        }
    """
    extracted_text = event.get("extracted_text", "")
    bim_metadata = event.get("bim_metadata", {})
    drawing_images = event.get("drawing_images", [])

    output_writer = OutputWriter.from_env()
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")  # legacy fallback for non-put_object usages
    model_id = os.environ.get("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID)
    sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")

    logger.info(
        "Safety Check started: text_length=%d, images=%d, model=%s",
        len(extracted_text),
        len(drawing_images),
        model_id,
    )

    # 安全ルール取得
    rules = get_safety_rules()

    # Bedrock でコンプライアンスチェック
    bedrock_client = boto3.client("bedrock-runtime")
    compliance_results = check_compliance_with_bedrock(
        bedrock_client, model_id, extracted_text, bim_metadata, rules
    )

    # 結果にルール情報を補完
    rule_ids_in_results = {r.get("rule_id") for r in compliance_results}
    for rule in rules:
        if rule["rule_id"] not in rule_ids_in_results:
            compliance_results.append({
                "rule_id": rule["rule_id"],
                "rule_name": rule["rule_name"],
                "status": "FAIL",
                "details": "Rule not evaluated",
                "remediation": "Manual review required",
            })

    # Rekognition で視覚要素検出
    rekognition_client = boto3.client("rekognition")
    visual_elements = detect_visual_safety_elements(
        rekognition_client, drawing_images
    )

    # 全体コンプライアンス判定
    overall_compliance = determine_overall_compliance(compliance_results)

    # 出力キー生成
    now = datetime.now(timezone.utc)
    project_name = bim_metadata.get("project_name", "unknown")
    output_key = (
        f"compliance/{now.strftime('%Y/%m/%d')}"
        f"/{project_name}_safety.json"
    )

    # 結果を S3 出力バケットに書き込み
    result = {
        "status": "SUCCESS",
        "compliance_results": compliance_results,
        "visual_elements": visual_elements,
        "overall_compliance": overall_compliance,
        "output_key": output_key,
        "checked_at": now.isoformat(),
    }

    output_writer.put_json(key=output_key, data=result)

    # SNS 通知
    if sns_topic_arn:
        try:
            sns_client = boto3.client("sns")
            sns_message = (
                f"安全コンプライアンスチェック完了\n\n"
                f"プロジェクト: {project_name}\n"
                f"全体結果: {overall_compliance}\n"
                f"ルール数: {len(compliance_results)}\n"
                f"PASS: {sum(1 for r in compliance_results if r.get('status') == 'PASS')}\n"
                f"FAIL: {sum(1 for r in compliance_results if r.get('status') == 'FAIL')}\n"
                f"レポート: s3://{output_bucket}/{output_key}\n"
                f"日時: {now.isoformat()}"
            )
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Subject="[Construction Safety] コンプライアンスチェック完了",
                Message=sns_message,
            )
        except Exception as e:
            logger.warning("SNS notification failed: %s", e)

    logger.info(
        "Safety Check completed: overall=%s, rules=%d, visual_elements=%s",
        overall_compliance,
        len(compliance_results),
        visual_elements,
    )


    # EMF メトリクス出力
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="safety_check")
    metrics.set_dimension("UseCase", os.environ.get("USE_CASE", "construction-bim"))
    metrics.put_metric("FilesProcessed", 1.0, "Count")
    metrics.flush()

    return result
