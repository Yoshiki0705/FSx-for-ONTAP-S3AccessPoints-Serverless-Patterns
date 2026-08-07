import os

import boto3
from botocore.config import Config

region = os.environ.get("AWS_REGION", "ap-northeast-1")
s3 = boto3.client(
    "s3", region_name=region, endpoint_url=f"https://s3.{region}.amazonaws.com", config=Config(signature_version="s3v4")
)
rekognition = boto3.client("rekognition", region_name=region)


def handler(event, context):
    """Detect objects/labels in an image file on FSx for ONTAP S3 AP using Rekognition.

    Downloads image via S3 AP, sends to Rekognition DetectLabels,
    returns labels with bounding boxes and confidence scores.
    """
    ap_alias = os.environ.get("S3_AP_ALIAS", "")
    key = event.get("key", "")
    max_labels = event.get("maxLabels", 10)
    min_confidence = event.get("minConfidence", 70.0)

    if not ap_alias or not key:
        return {"labels": [], "error": "Missing required parameters (key)"}

    try:
        # Get image from S3 AP
        obj = s3.get_object(Bucket=ap_alias, Key=key)
        image_bytes = obj["Body"].read()

        # Detect labels
        response = rekognition.detect_labels(
            Image={"Bytes": image_bytes},
            MaxLabels=max_labels,
            MinConfidence=min_confidence,
        )

        labels = []
        for label in response.get("Labels", []):
            label_data = {
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
        print(f"Error: {e}")
        return {"labels": [], "error": str(e)}
