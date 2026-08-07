import os

import boto3
from botocore.config import Config

region = os.environ.get("AWS_REGION", "ap-northeast-1")
s3 = boto3.client(
    "s3", region_name=region, endpoint_url=f"https://s3.{region}.amazonaws.com", config=Config(signature_version="s3v4")
)
textract = boto3.client("textract", region_name=region)


def handler(event, context):
    """Extract text from a document/image on FSx for ONTAP S3 AP using Textract."""
    ap_alias = os.environ.get("S3_AP_ALIAS", "")
    key = event.get("key", "")
    mode = event.get("mode", "text")  # "text" or "analyze"

    if not ap_alias or not key:
        return {"text": "", "blocks": [], "error": "Missing parameters"}

    try:
        obj = s3.get_object(Bucket=ap_alias, Key=key)
        doc_bytes = obj["Body"].read()

        if mode == "analyze":
            response = textract.analyze_document(
                Document={"Bytes": doc_bytes},
                FeatureTypes=["TABLES", "FORMS"],
            )
        else:
            response = textract.detect_document_text(Document={"Bytes": doc_bytes})

        # Extract text lines
        lines = []
        for block in response.get("Blocks", []):
            if block["BlockType"] == "LINE":
                lines.append(block["Text"])

        return {
            "text": "\n".join(lines),
            "blockCount": len(response.get("Blocks", [])),
            "pageCount": len([b for b in response.get("Blocks", []) if b["BlockType"] == "PAGE"]),
            "error": None,
        }

    except Exception as e:
        return {"text": "", "blockCount": 0, "pageCount": 0, "error": str(e)}
