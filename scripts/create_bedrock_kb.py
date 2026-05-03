#!/usr/bin/env python3
"""Bedrock Knowledge Base を作成するスクリプト"""
import json
import time
import boto3

REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1")
ACCOUNT_ID = os.environ.get("AWS_ACCOUNT_ID", boto3.client("sts").get_caller_identity()["Account"])
COLLECTION_ARN = os.environ.get("AOSS_COLLECTION_ARN", "")
KB_ROLE_ARN = os.environ.get("KB_ROLE_ARN", f"arn:aws:iam::{ACCOUNT_ID}:role/fsxn-s3ap-bedrock-kb-role")
S3AP = os.environ.get("S3_ACCESS_POINT", "")

client = boto3.client("bedrock-agent", region_name=REGION)

# KB 作成
print("Creating Knowledge Base...")
try:
    resp = client.create_knowledge_base(
        name="fsxn-s3ap-test-kb",
        description="FSx for ONTAP S3 AP test Knowledge Base",
        roleArn=KB_ROLE_ARN,
        knowledgeBaseConfiguration={
            "type": "VECTOR",
            "vectorKnowledgeBaseConfiguration": {
                "embeddingModelArn": f"arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0",
                "embeddingModelConfiguration": {
                    "bedrockEmbeddingModelConfiguration": {
                        "dimensions": 256,
                    }
                },
            },
        },
        storageConfiguration={
            "type": "OPENSEARCH_SERVERLESS",
            "opensearchServerlessConfiguration": {
                "collectionArn": COLLECTION_ARN,
                "vectorIndexName": "bedrock-kb-index",
                "fieldMapping": {
                    "vectorField": "embedding",
                    "textField": "AMAZON_BEDROCK_TEXT_CHUNK",
                    "metadataField": "AMAZON_BEDROCK_METADATA",
                },
            },
        },
    )
    kb_id = resp["knowledgeBase"]["knowledgeBaseId"]
    print(f"KB created: {kb_id}")
    print(f"Status: {resp['knowledgeBase']['status']}")
except Exception as e:
    print(f"Error: {e}")
    raise

# KB が ACTIVE になるまで待機
print("Waiting for KB to become ACTIVE...")
for i in range(30):
    kb = client.get_knowledge_base(knowledgeBaseId=kb_id)
    status = kb["knowledgeBase"]["status"]
    print(f"  Attempt {i+1}: {status}")
    if status == "ACTIVE":
        break
    time.sleep(10)

# データソース追加（S3 AP）
print(f"\nAdding S3 AP data source: {S3AP}")
try:
    ds_resp = client.create_data_source(
        knowledgeBaseId=kb_id,
        name="fsxn-s3ap-source",
        description="FSx ONTAP S3 Access Point data source",
        dataSourceConfiguration={
            "type": "S3",
            "s3Configuration": {
                "bucketArn": f"arn:aws:s3:::{S3AP}",
            },
        },
    )
    ds_id = ds_resp["dataSource"]["dataSourceId"]
    print(f"Data source created: {ds_id}")
except Exception as e:
    print(f"Data source error: {e}")
    raise

# データ同期
print("\nStarting data sync...")
try:
    sync_resp = client.start_ingestion_job(
        knowledgeBaseId=kb_id,
        dataSourceId=ds_id,
    )
    job_id = sync_resp["ingestionJob"]["ingestionJobId"]
    print(f"Sync job started: {job_id}")
    
    # 同期完了を待機
    for i in range(30):
        job = client.get_ingestion_job(
            knowledgeBaseId=kb_id,
            dataSourceId=ds_id,
            ingestionJobId=job_id,
        )
        status = job["ingestionJob"]["status"]
        print(f"  Attempt {i+1}: {status}")
        if status in ("COMPLETE", "FAILED"):
            if status == "COMPLETE":
                stats = job["ingestionJob"].get("statistics", {})
                print(f"  Documents scanned: {stats.get('numberOfDocumentsScanned', 'N/A')}")
                print(f"  Documents indexed: {stats.get('numberOfNewDocumentsIndexed', 'N/A')}")
            break
        time.sleep(10)
except Exception as e:
    print(f"Sync error: {e}")

print(f"\nKB ID: {kb_id}")
print(f"Data Source ID: {ds_id}")
