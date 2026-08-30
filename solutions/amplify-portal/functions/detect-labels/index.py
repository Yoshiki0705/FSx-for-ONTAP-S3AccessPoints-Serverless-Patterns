"""Image label detection on an FSx for ONTAP S3 Access Point object, via Rekognition.

Same shape as the other content-reading endpoints: an object key arrives from the
client. It read `S3_AP_ALIAS` alone and checked nothing, so labels for another team's
image were reachable by naming its key. Labels and bounding boxes describe the picture,
so an unchecked key here leaks the thing the boundary exists to protect.
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
rekognition = boto3.client("rekognition", region_name=region)

DEFAULT_AP_ALIAS = os.environ.get("S3_AP_ALIAS", "")
GROUP_AP_MAPPING = json.loads(os.environ.get("GROUP_AP_MAPPING", "{}"))
GROUP_PATH_PREFIXES = json.loads(os.environ.get("GROUP_PATH_PREFIXES", "{}"))
# Whether callers from outside the organisation may use this endpoint. Off unless
# set, because the call sends file content to a model and is billed per token.
EXTERNAL_AI_ENABLED = os.environ.get("EXTERNAL_AI_ENABLED", "") == "true"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Detect labels in an image with Rekognition.

    Args:
        event: `key`, optional `maxLabels` and `minConfidence`, plus `groups` injected
            by the resolver from the Cognito identity.
        context: Lambda context, unused.

    Returns:
        `labels` with bounding boxes and confidence, or `error`.
    """
    key = event.get("key", "")
    max_labels = event.get("maxLabels", 10)
    min_confidence = event.get("minConfidence", 70.0)
    groups = event.get("groups") if isinstance(event.get("groups"), list) else []

    # Before the key boundary. The scope answer does not depend on which key was asked
    # for, and refusing first keeps the denial from confirming the key exists.
    denied = ai_denial_reason(groups, ai_enabled=EXTERNAL_AI_ENABLED)
    if denied:
        logger.info("AI endpoint refused for an external caller: %s", denied)
        return {"labels": [], "error": denied}

    alias, refused = scope_for_caller(
        groups,
        group_ap_mapping=GROUP_AP_MAPPING,
        group_path_prefixes=GROUP_PATH_PREFIXES,
        default_alias=DEFAULT_AP_ALIAS,
        key=key,
    )
    if refused:
        return {"labels": [], **refused}

    try:
        image_bytes = S3ApHelper(alias).get_object_bytes(key)
    except S3ApHelperError as e:
        logger.exception("Read failed for key %s on %s", key, alias)
        return {"labels": [], "error": str(e)}

    try:
        response = rekognition.detect_labels(
            Image={"Bytes": image_bytes},
            MaxLabels=max_labels,
            MinConfidence=min_confidence,
        )

        labels = []
        for label in response.get("Labels", []):
            label_data: dict[str, Any] = {
                "name": label["Name"],
                "confidence": round(label["Confidence"], 1),
                "instances": [],
            }
            for instance in label.get("Instances", []):
                box = instance.get("BoundingBox", {})
                label_data["instances"].append(
                    {
                        "boundingBox": {
                            "width": round(box.get("Width", 0), 4),
                            "height": round(box.get("Height", 0), 4),
                            "left": round(box.get("Left", 0), 4),
                            "top": round(box.get("Top", 0), 4),
                        },
                        "confidence": round(instance.get("Confidence", 0), 1),
                    }
                )
            labels.append(label_data)

        return {"labels": labels, "imageWidth": None, "imageHeight": None, "error": None}
    except Exception as e:
        logger.exception("Rekognition failed for key %s", key)
        return {"labels": [], "error": str(e)}
