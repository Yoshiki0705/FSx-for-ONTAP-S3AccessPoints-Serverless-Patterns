"""Entity, sentiment and key-phrase analysis of an object's text, via Comprehend.

Like the other endpoints that read file content, this one takes an object key from the
client. It read `S3_AP_ALIAS` alone and checked nothing, so the analysis of another
team's file was reachable by naming its key. Detected entities are a summary of the
contents, which is what makes an unchecked key here equivalent to a read.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3

from shared.exceptions import S3ApHelperError
from shared.portal_external_policy import ai_denial_reason
from shared.portal_path_scope import scope_for_caller
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger()
logger.setLevel(logging.INFO)

region = os.environ.get("AWS_REGION", "ap-northeast-1")
comprehend = boto3.client("comprehend", region_name=region)

DEFAULT_AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")
GROUP_AP_MAPPING = json.loads(os.environ.get("GROUP_AP_MAPPING", "{}"))
GROUP_PATH_PREFIXES = json.loads(os.environ.get("GROUP_PATH_PREFIXES", "{}"))
# Whether callers from outside the organisation may use this endpoint. Off unless
# set, because the call sends file content to a model and is billed per token.
EXTERNAL_AI_ENABLED = os.environ.get("EXTERNAL_AI_ENABLED", "") == "true"

MAX_TEXT_SIZE = 5000  # Comprehend limit per request


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Analyse an object's text with Comprehend.

    Args:
        event: `key`, optional `analysisType` (`entities`, `sentiment`, `keyPhrases`),
            plus `groups` injected by the resolver from the Cognito identity.
        context: Lambda context, unused.

    Returns:
        `results`, or `error` naming why nothing was analysed.
    """
    key = event.get("key", "")
    analysis_type = event.get("analysisType", "entities")
    groups = event.get("groups") if isinstance(event.get("groups"), list) else []

    # Before the key boundary. The scope answer does not depend on which key was asked
    # for, and refusing first keeps the denial from confirming the key exists.
    denied = ai_denial_reason(groups, ai_enabled=EXTERNAL_AI_ENABLED)
    if denied:
        logger.info("AI endpoint refused for an external caller: %s", denied)
        return {"results": [], "error": denied}

    alias, refused = scope_for_caller(
        groups,
        group_ap_mapping=GROUP_AP_MAPPING,
        group_path_prefixes=GROUP_PATH_PREFIXES,
        default_alias=DEFAULT_AP_ALIAS,
        key=key,
    )
    if refused:
        return {"results": [], **refused}

    try:
        text = S3ApHelper(alias).get_object_bytes(key, max_bytes=MAX_TEXT_SIZE).decode("utf-8", errors="replace")
    except S3ApHelperError as e:
        logger.exception("Read failed for key %s on %s", key, alias)
        return {"results": [], "error": str(e)}

    try:
        if analysis_type == "sentiment":
            response = comprehend.detect_sentiment(Text=text, LanguageCode="en")
            return {
                "results": {
                    "sentiment": response["Sentiment"],
                    "scores": response["SentimentScore"],
                },
                "error": None,
            }
        if analysis_type == "keyPhrases":
            response = comprehend.detect_key_phrases(Text=text, LanguageCode="en")
            phrases = [{"text": p["Text"], "score": round(p["Score"], 3)} for p in response["KeyPhrases"][:20]]
            return {"results": phrases, "error": None}
        response = comprehend.detect_entities(Text=text, LanguageCode="en")
        entities = [
            {"text": e["Text"], "type": e["Type"], "score": round(e["Score"], 3)} for e in response["Entities"][:30]
        ]
        return {"results": entities, "error": None}
    except Exception as e:
        logger.exception("Comprehend failed for key %s", key)
        return {"results": [], "error": str(e)}
