#!/usr/bin/env python3
"""OpenSearch Serverless にベクトルインデックスを作成するスクリプト"""
import json
import sys
import urllib.request

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

ENDPOINT = sys.argv[1] if len(sys.argv) > 1 else ""
INDEX_NAME = "bedrock-kb-index"
REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1")

index_body = {
    "settings": {
        "index.knn": True,
        "number_of_shards": 2,
        "number_of_replicas": 0,
    },
    "mappings": {
        "properties": {
            "embedding": {
                "type": "knn_vector",
                "dimension": 256,
                "method": {"engine": "faiss", "name": "hnsw", "parameters": {}},
            },
            "text": {"type": "text"},
            "metadata": {"type": "text"},
            "AMAZON_BEDROCK_TEXT_CHUNK": {"type": "text"},
            "AMAZON_BEDROCK_METADATA": {"type": "text"},
        }
    },
}

url = ENDPOINT + "/" + INDEX_NAME
data = json.dumps(index_body).encode()

session = boto3.Session()
creds = session.get_credentials().get_frozen_credentials()
request = AWSRequest(method="PUT", url=url, data=data, headers={"Content-Type": "application/json"})
SigV4Auth(creds, "aoss", REGION).add_auth(request)

req = urllib.request.Request(url, data=data, method="PUT")
for k, v in dict(request.headers).items():
    req.add_header(k, v)

try:
    resp = urllib.request.urlopen(req)
    print(f"Index created: {resp.status}")
    print(resp.read().decode())
except urllib.error.HTTPError as e:
    print(f"Error: {e.code}")
    print(e.read().decode())
