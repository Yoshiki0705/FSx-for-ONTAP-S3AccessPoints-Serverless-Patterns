"""Text extraction from an FSx for ONTAP S3 Access Point object, via Textract.

This endpoint takes an object key from the client and returns the file's text. It
read `S3_AP_ALIAS` alone and checked nothing, so a caller could name a key belonging
to another team and receive the contents back in the answer -- without listing the
file, previewing it, or downloading it. The boundary that listing and writing enforce
did not reach here.
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
from shared.portal_regulated_path import regulated_path_denial_reason
from shared.s3ap_helper import S3ApHelper

logger = logging.getLogger()
logger.setLevel(logging.INFO)

region = os.environ.get("AWS_REGION", "ap-northeast-1")
textract = boto3.client("textract", region_name=region)

DEFAULT_AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")
GROUP_AP_MAPPING = json.loads(os.environ.get("GROUP_AP_MAPPING", "{}"))
GROUP_PATH_PREFIXES = json.loads(os.environ.get("GROUP_PATH_PREFIXES", "{}"))
# Whether callers from outside the organisation may use this endpoint. Off unless
# set, because the call sends file content to a model and is billed per token.
EXTERNAL_AI_ENABLED = os.environ.get("EXTERNAL_AI_ENABLED", "") == "true"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Extract text from a document or image using Textract.

    Args:
        event: `key`, optional `mode` (`text` or `analyze`), plus `groups` injected by
            the resolver from the Cognito identity.
        context: Lambda context, unused.

    Returns:
        `text`, `blockCount` and `pageCount`, or `error` naming why nothing was read.
    """
    key = event.get("key", "")
    mode = event.get("mode", "text")
    groups = event.get("groups") if isinstance(event.get("groups"), list) else []

    # Before the key boundary. The scope answer does not depend on which key was asked
    # for, and refusing first keeps the denial from confirming the key exists.
    denied = ai_denial_reason(groups, ai_enabled=EXTERNAL_AI_ENABLED)
    if denied:
        logger.info("AI endpoint refused for an external caller: %s", denied)
        return {"text": "", "blockCount": 0, "pageCount": 0, "error": denied}

    alias, refused = scope_for_caller(
        groups,
        group_ap_mapping=GROUP_AP_MAPPING,
        group_path_prefixes=GROUP_PATH_PREFIXES,
        default_alias=DEFAULT_AP_ALIAS,
        key=key,
    )
    if refused:
        return {"text": "", "blockCount": 0, "pageCount": 0, **refused}

    # After the scope answer, so a key the caller cannot reach is refused for that reason
    # rather than told which folders are regulated. Extraction returns the document's text,
    # so this endpoint sends regulated data to Textract exactly as a read would. The browser
    # hides the buttons for these paths; without this, calling AppSync directly did not.
    denied = regulated_path_denial_reason(key)
    if denied:
        logger.info("AI endpoint refused for a regulated path: %s", key)
        return {"text": "", "blockCount": 0, "pageCount": 0, "error": denied, "blocked": True}

    try:
        doc_bytes = S3ApHelper(alias).get_object_bytes(key)
    except S3ApHelperError as e:
        logger.exception("Read failed for key %s on %s", key, alias)
        return {"text": "", "blockCount": 0, "pageCount": 0, "error": str(e)}

    try:
        if mode == "analyze":
            response = textract.analyze_document(
                Document={"Bytes": doc_bytes},
                FeatureTypes=["TABLES", "FORMS"],
            )
        else:
            response = textract.detect_document_text(Document={"Bytes": doc_bytes})

        blocks = response.get("Blocks", [])
        lines = [b["Text"] for b in blocks if b["BlockType"] == "LINE"]
        return {
            "text": "\n".join(lines),
            "blockCount": len(blocks),
            "pageCount": len([b for b in blocks if b["BlockType"] == "PAGE"]),
            "error": None,
        }
    except Exception as e:
        logger.exception("Textract failed for key %s", key)
        return {"text": "", "blockCount": 0, "pageCount": 0, "error": str(e)}
