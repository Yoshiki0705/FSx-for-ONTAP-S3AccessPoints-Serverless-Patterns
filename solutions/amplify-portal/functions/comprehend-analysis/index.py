import os

import boto3
from botocore.config import Config

region = os.environ.get("AWS_REGION", "ap-northeast-1")
s3 = boto3.client(
    "s3", region_name=region, endpoint_url=f"https://s3.{region}.amazonaws.com", config=Config(signature_version="s3v4")
)
comprehend = boto3.client("comprehend", region_name=region)

MAX_TEXT_SIZE = 5000  # Comprehend limit per request


def handler(event, context):
    """Analyze text file from FSx for ONTAP S3 AP using Comprehend."""
    ap_alias = os.environ.get("S3_AP_ALIAS", "")
    key = event.get("key", "")
    analysis_type = event.get("analysisType", "entities")  # entities, sentiment, keyPhrases

    if not ap_alias or not key:
        return {"results": [], "error": "Missing parameters"}

    try:
        obj = s3.get_object(Bucket=ap_alias, Key=key)
        text = obj["Body"].read(MAX_TEXT_SIZE).decode("utf-8", errors="replace")

        if analysis_type == "sentiment":
            response = comprehend.detect_sentiment(Text=text, LanguageCode="en")
            return {
                "results": {
                    "sentiment": response["Sentiment"],
                    "scores": response["SentimentScore"],
                },
                "error": None,
            }
        elif analysis_type == "keyPhrases":
            response = comprehend.detect_key_phrases(Text=text, LanguageCode="en")
            phrases = [{"text": p["Text"], "score": round(p["Score"], 3)} for p in response["KeyPhrases"][:20]]
            return {"results": phrases, "error": None}
        else:  # entities
            response = comprehend.detect_entities(Text=text, LanguageCode="en")
            entities = [
                {"text": e["Text"], "type": e["Type"], "score": round(e["Score"], 3)} for e in response["Entities"][:30]
            ]
            return {"results": entities, "error": None}

    except Exception as e:
        return {"results": [], "error": str(e)}
