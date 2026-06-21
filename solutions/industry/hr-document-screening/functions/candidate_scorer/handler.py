"""HR (UC27) Candidate Scorer Lambda ハンドラ

候補者プロファイルを職務要件と照合し、適合度スコアを生成する。

Requirement 11.3:
    - Bedrock で適合度スコアリング
    - 保護特性をプロンプトで明示的に除外

Requirement 11.6:
    - 保護特性（年齢、性別、国籍）はスコアリングから除外
    - コンプライアンスノートを記録

AI/ML サービス:
    - Amazon Bedrock: 適合度スコアリング

Note: Output bucket enforces SSE-KMS encryption via bucket default encryption policy
(configured in template.yaml OutputBucket resource)

Environment Variables:
    BEDROCK_MODEL_ID: Bedrock モデル ID
    PII_MODE: PII 保護モード (default: strict)
    JOB_REQUIREMENTS_S3_KEY: 職務要件 JSON ファイルキー
"""

from __future__ import annotations

import json
import logging
import os
import time

import boto3

from shared.exceptions import lambda_error_handler
from shared.observability import EmfMetrics, trace_lambda_handler
from shared.pii_filter import PiiFilter, is_strict_mode
from shared.retry_handler import RetryConfig, categorize_error, retry_with_backoff

logger = logging.getLogger(__name__)


def score_candidate_bedrock(
    candidate_data: dict,
    job_requirements: dict,
    pii_filter: PiiFilter,
    bedrock_client=None,
    model_id: str | None = None,
) -> dict:
    """Bedrock で候補者の適合度をスコアリングする。

    Args:
        candidate_data: 候補者データ (skills, experience, education, certs)
        job_requirements: 職務要件
        pii_filter: PiiFilter インスタンス
        bedrock_client: Bedrock Runtime クライアント (テスト用)
        model_id: Bedrock モデル ID

    Returns:
        dict: score (0-100), reasons, matched_skills, gaps
    """
    if bedrock_client is None:
        bedrock_client = boto3.client("bedrock-runtime")

    if model_id is None:
        model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-haiku-4-5-20251001-v1:0")

    # 保護特性除外プロンプト (Requirement 11.6)
    exclusion_prompt = pii_filter.create_scoring_exclusion_prompt()

    candidate_summary = json.dumps(candidate_data, ensure_ascii=False)
    requirements_summary = json.dumps(job_requirements, ensure_ascii=False)

    prompt = (
        f"{exclusion_prompt}\n\n"
        f"以下の候補者データと職務要件を照合し、適合度スコアを算出してください。\n\n"
        f"候補者データ:\n{candidate_summary}\n\n"
        f"職務要件:\n{requirements_summary}\n\n"
        f"以下の JSON 形式で回答してください:\n"
        f'{{"score": 0-100の整数, "matched_skills": [マッチしたスキル], '
        f'"skill_gaps": [不足スキル], "recommendation": "推薦文"}}'
    )

    @retry_with_backoff(config=RetryConfig(max_attempts=3))
    def _call_bedrock():
        return bedrock_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                }
            ),
        )

    try:
        response = _call_bedrock()
        response_body = json.loads(response["body"].read())
        content_text = response_body.get("content", [{}])[0].get("text", "")

        # JSON 部分を抽出
        result = _parse_scoring_response(content_text)
        return result

    except Exception as e:
        logger.warning("Bedrock scoring failed: %s", str(e))
        return {
            "score": 0,
            "matched_skills": [],
            "skill_gaps": [],
            "recommendation": "",
            "scoring_error": str(e),
        }


def _parse_scoring_response(text: str) -> dict:
    """Bedrock レスポンスからスコアリング結果を抽出する。"""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            # スコアを 0-100 にクランプ
            score = data.get("score", 0)
            if isinstance(score, (int, float)):
                data["score"] = max(0, min(100, int(score)))
            else:
                data["score"] = 0
            return data
        except json.JSONDecodeError:
            pass
    return {"score": 0, "matched_skills": [], "skill_gaps": [], "recommendation": ""}


@trace_lambda_handler
@lambda_error_handler
def handler(event, context):
    """Candidate Scorer Lambda

    Input event:
        - results: Resume Extractor 出力
        - job_requirements: 職務要件 (optional, from config)

    Returns:
        dict: scored_results, success_count, error_count
    """
    start_time = time.time()

    pii_filter = PiiFilter()

    # SECURITY: Output bucket enforces SSE-KMS via default encryption policy (template.yaml).
    # For defense-in-depth, consider adding explicit ServerSideEncryption to put_object calls
    # when S3ApHelper supports it. See: shared/s3ap_helper.py

    results = event.get("results", [])
    job_requirements = event.get(
        "job_requirements",
        {
            "required_skills": [],
            "min_experience_years": 0,
            "preferred_certifications": [],
        },
    )

    if is_strict_mode():
        logger.info("Candidate scoring started: %d candidates (strict PII mode)", len(results))
    else:
        logger.info("Candidate scoring started: %d candidates", len(results))

    scored_results: list[dict] = []
    success_count = 0
    error_count = 0

    for result in results:
        if result.get("status") != "success":
            scored_results.append(result)
            error_count += 1
            continue

        key = result.get("key", "")
        candidate_data = result.get("candidate_data", {})

        try:
            # 保護特性を再確認して除去
            candidate_data = pii_filter.remove_protected_characteristics(candidate_data)

            scoring = score_candidate_bedrock(candidate_data, job_requirements, pii_filter)

            scored_results.append(
                {
                    "key": key,
                    "position_type": result.get("position_type", "general"),
                    "status": "success",
                    "candidate_data": candidate_data,
                    "scoring": scoring,
                    "compliance_note": result.get("compliance_note"),
                }
            )
            success_count += 1

        except Exception as e:
            error_category = categorize_error(e)
            logger.warning("Candidate scoring failed: %s [%s]", str(e), error_category.value)
            scored_results.append(
                {
                    "key": key,
                    "position_type": result.get("position_type", "general"),
                    "status": "error",
                    "error_type": error_category.value,
                    "error_message": str(e),
                }
            )
            error_count += 1

    processing_duration_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "Candidate scoring completed: success=%d, errors=%d",
        success_count,
        error_count,
    )

    # EMF メトリクス
    metrics = EmfMetrics(namespace="FSxN-S3AP-Patterns", service="processing")
    metrics.set_dimension("UseCase", "hr-document-screening")
    metrics.set_dimension("Stage", "candidate-scoring")
    metrics.put_metric("ProcessingDuration", float(processing_duration_ms), "Milliseconds")
    metrics.put_metric("SuccessCount", float(success_count), "Count")
    metrics.put_metric("ErrorCount", float(error_count), "Count")
    metrics.flush()

    return {
        "scored_results": scored_results,
        "success_count": success_count,
        "error_count": error_count,
        "processing_duration_ms": processing_duration_ms,
        "audit_trail": pii_filter.get_audit_trail(),
    }
