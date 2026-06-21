#!/usr/bin/env python3
"""Rebuild the UC29 Self-Service Knowledge Base end-to-end (idempotent).

Recreates everything teardown removes for the KB side, in dependency order:
  AOSS encryption + network policies -> IAM role -> AOSS data-access policy ->
  AOSS collection -> vector index -> Bedrock KB -> S3 data source -> ingestion.

Lessons learned encoded here:
  * Amazon S3 Vectors store is NOT creatable via CLI/boto3 (console quick-create
    only) -> we use OPENSEARCH_SERVERLESS.
  * The KB data source 'bucket' is the FSx for ONTAP S3 Access Point ALIAS
    (arn:aws:s3:::<alias>), supplied via env (never hardcoded in the repo).
  * Titan embed v2 here uses 256 dimensions -> the knn index dim MUST match.
  * AOSS data-access policy must include BOTH the KB role AND the caller
    (the caller creates the index with its own SigV4 creds).
  * Role/policy propagation + collection ACTIVE are eventually consistent ->
    we poll/retry.

Config (env, with safe non-sensitive defaults; secrets have NO default):
  AWS_REGION, KB_DATA_BUCKET (required), KB_INCLUSION_PREFIX, KB_EMBED_MODEL,
  KB_EMBED_DIMENSIONS, KB_VECTOR_INDEX, AOSS_COLLECTION, KB_NAME, KB_ROLE

Usage:
  source scripts/uc29-kb-manifest.local.env   # provides KB_DATA_BUCKET etc.
  .venv/bin/python scripts/rebuild-uc29-kb.py
"""
from __future__ import annotations

import json
import os
import sys
import time

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
DATA_BUCKET = os.environ.get("KB_DATA_BUCKET", "")  # S3 AP alias — required
PREFIX = os.environ.get("KB_INCLUSION_PREFIX", "ai-knowledge/")
EMBED_MODEL = os.environ.get("KB_EMBED_MODEL", "amazon.titan-embed-text-v2:0")
EMBED_DIMS = int(os.environ.get("KB_EMBED_DIMENSIONS", "256"))
INDEX_NAME = os.environ.get("KB_VECTOR_INDEX", "bedrock-kb-index")
COLLECTION = os.environ.get("AOSS_COLLECTION", "uc29-kb-vectors")
KB_NAME = os.environ.get("KB_NAME", "uc29-selfservice-kb")
ROLE_NAME = os.environ.get("KB_ROLE", "fsxn-s3ap-bedrock-kb-role")

ENC_POLICY = "uc29-kb-encryption"
NET_POLICY = "uc29-kb-network"
ACCESS_POLICY = "uc29-kb-access"

sts = boto3.client("sts", region_name=REGION)
aoss = boto3.client("opensearchserverless", region_name=REGION)
iam = boto3.client("iam", region_name=REGION)
agent = boto3.client("bedrock-agent", region_name=REGION)
ACCOUNT = sts.get_caller_identity()["Account"]


def log(msg: str) -> None:
    print(f"==> {msg}", flush=True)


def role_arn_of_caller() -> str:
    """Normalize an assumed-role session ARN to its base role ARN for AOSS."""
    arn = sts.get_caller_identity()["Arn"]
    if ":assumed-role/" in arn:
        name = arn.split("/")[1]
        return f"arn:aws:iam::{ACCOUNT}:role/{name}"
    return arn


def ensure_encryption_policy() -> None:
    policy = {"Rules": [{"ResourceType": "collection", "Resource": [f"collection/{COLLECTION}"]}],
              "AWSOwnedKey": True}
    try:
        aoss.create_security_policy(name=ENC_POLICY, type="encryption", policy=json.dumps(policy))
        log(f"created encryption policy {ENC_POLICY}")
    except aoss.exceptions.ConflictException:
        log(f"encryption policy exists: {ENC_POLICY}")


def ensure_network_policy() -> None:
    policy = [{"Rules": [{"ResourceType": "collection", "Resource": [f"collection/{COLLECTION}"]},
                         {"ResourceType": "dashboard", "Resource": [f"collection/{COLLECTION}"]}],
               "AllowFromPublic": True}]
    try:
        aoss.create_security_policy(name=NET_POLICY, type="network", policy=json.dumps(policy))
        log(f"created network policy {NET_POLICY}")
    except aoss.exceptions.ConflictException:
        log(f"network policy exists: {NET_POLICY}")


def ensure_role() -> str:
    trust = {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"Service": "bedrock.amazonaws.com"},
        "Action": "sts:AssumeRole",
        "Condition": {"StringEquals": {"aws:SourceAccount": ACCOUNT}}}]}
    try:
        iam.create_role(RoleName=ROLE_NAME, AssumeRolePolicyDocument=json.dumps(trust),
                        Description="UC29 Bedrock KB execution role")
        log(f"created IAM role {ROLE_NAME}")
    except iam.exceptions.EntityAlreadyExistsException:
        log(f"IAM role exists: {ROLE_NAME}")
    inline = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["aoss:APIAccessAll"],
         "Resource": [f"arn:aws:aoss:{REGION}:{ACCOUNT}:collection/*"]},
        {"Effect": "Allow", "Action": ["bedrock:InvokeModel"],
         "Resource": [f"arn:aws:bedrock:{REGION}::foundation-model/{EMBED_MODEL}"]},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:ListBucket"],
         "Resource": [f"arn:aws:s3:::{DATA_BUCKET}", f"arn:aws:s3:::{DATA_BUCKET}/*"]}]}
    iam.put_role_policy(RoleName=ROLE_NAME, PolicyName="kb-access", PolicyDocument=json.dumps(inline))
    log("attached inline policy kb-access")
    return f"arn:aws:iam::{ACCOUNT}:role/{ROLE_NAME}"


def ensure_access_policy(role_arn: str) -> None:
    principals = sorted({role_arn, role_arn_of_caller()})
    policy = [{"Rules": [
        {"ResourceType": "index", "Resource": [f"index/{COLLECTION}/*"], "Permission": ["aoss:*"]},
        {"ResourceType": "collection", "Resource": [f"collection/{COLLECTION}"], "Permission": ["aoss:*"]}],
        "Principal": principals}]
    try:
        aoss.create_access_policy(name=ACCESS_POLICY, type="data", policy=json.dumps(policy))
        log(f"created data-access policy {ACCESS_POLICY}")
    except aoss.exceptions.ConflictException:
        ver = aoss.list_access_policies(type="data")["accessPolicySummaries"]
        for p in ver:
            if p["name"] == ACCESS_POLICY:
                cur = aoss.get_access_policy(name=ACCESS_POLICY, type="data")["accessPolicyDetail"]
                aoss.update_access_policy(name=ACCESS_POLICY, type="data",
                                          policyVersion=cur["policyVersion"], policy=json.dumps(policy))
                log(f"updated data-access policy {ACCESS_POLICY}")


def ensure_collection() -> tuple[str, str]:
    try:
        aoss.create_collection(name=COLLECTION, type="VECTORSEARCH",
                               description="UC29 KB vector store")
        log(f"creating collection {COLLECTION} ...")
    except aoss.exceptions.ConflictException:
        log(f"collection exists: {COLLECTION}")
    for _ in range(60):
        det = aoss.batch_get_collection(names=[COLLECTION])["collectionDetails"]
        if det and det[0]["status"] == "ACTIVE":
            d = det[0]
            host = d["collectionEndpoint"].replace("https://", "")
            log(f"collection ACTIVE: {d['id']}")
            return d["arn"], host
        time.sleep(10)
    sys.exit("collection did not become ACTIVE in time")


def ensure_index(host: str) -> None:
    creds = boto3.Session().get_credentials()
    auth = AWS4Auth(creds.access_key, creds.secret_key, REGION, "aoss",
                    session_token=creds.token)
    client = OpenSearch(hosts=[{"host": host, "port": 443}], http_auth=auth,
                        use_ssl=True, verify_certs=True, connection_class=RequestsHttpConnection,
                        pool_maxsize=20)
    body = {
        "settings": {"index": {"knn": True}},
        "mappings": {"properties": {
            "embedding": {"type": "knn_vector", "dimension": EMBED_DIMS,
                          "method": {"name": "hnsw", "engine": "faiss",
                                     "space_type": "l2", "parameters": {}}},
            "AMAZON_BEDROCK_TEXT_CHUNK": {"type": "text"},
            "AMAZON_BEDROCK_METADATA": {"type": "text", "index": False}}}}
    for attempt in range(10):
        try:
            if client.indices.exists(INDEX_NAME):
                log(f"index exists: {INDEX_NAME}")
                return
            client.indices.create(INDEX_NAME, body=body)
            log(f"created vector index {INDEX_NAME} (dim={EMBED_DIMS})")
            time.sleep(30)  # let the index settle before KB validation
            return
        except Exception as e:  # noqa: BLE001 — AOSS data-plane auth is eventually consistent
            log(f"index create retry {attempt + 1}/10: {e}")
            time.sleep(15)
    sys.exit("failed to create vector index")


def ensure_kb(role_arn: str, coll_arn: str) -> str:
    existing = [k for k in agent.list_knowledge_bases()["knowledgeBaseSummaries"]
                if k["name"] == KB_NAME]
    if existing:
        log(f"KB exists: {existing[0]['knowledgeBaseId']}")
        return existing[0]["knowledgeBaseId"]
    resp = agent.create_knowledge_base(
        name=KB_NAME, description="UC29 Self-Service KB Curation - FSx for ONTAP S3 AP data source",
        roleArn=role_arn,
        knowledgeBaseConfiguration={"type": "VECTOR", "vectorKnowledgeBaseConfiguration": {
            "embeddingModelArn": f"arn:aws:bedrock:{REGION}::foundation-model/{EMBED_MODEL}",
            "embeddingModelConfiguration": {"bedrockEmbeddingModelConfiguration": {"dimensions": EMBED_DIMS}}}},
        storageConfiguration={"type": "OPENSEARCH_SERVERLESS", "opensearchServerlessConfiguration": {
            "collectionArn": coll_arn, "vectorIndexName": INDEX_NAME,
            "fieldMapping": {"vectorField": "embedding",
                             "textField": "AMAZON_BEDROCK_TEXT_CHUNK",
                             "metadataField": "AMAZON_BEDROCK_METADATA"}}})
    kb_id = resp["knowledgeBase"]["knowledgeBaseId"]
    log(f"created KB {kb_id}")
    return kb_id


def ensure_data_source(kb_id: str) -> str:
    existing = [d for d in agent.list_data_sources(knowledgeBaseId=kb_id)["dataSourceSummaries"]]
    if existing:
        log(f"data source exists: {existing[0]['dataSourceId']}")
        return existing[0]["dataSourceId"]
    resp = agent.create_data_source(
        knowledgeBaseId=kb_id, name="fsxn-s3ap-ai-knowledge",
        description="FSx for ONTAP S3 AP - ai-knowledge/ prefix",
        dataDeletionPolicy="DELETE",
        dataSourceConfiguration={"type": "S3", "s3Configuration": {
            "bucketArn": f"arn:aws:s3:::{DATA_BUCKET}", "inclusionPrefixes": [PREFIX]}})
    ds_id = resp["dataSource"]["dataSourceId"]
    log(f"created data source {ds_id}")
    return ds_id


def main() -> None:
    if not DATA_BUCKET:
        sys.exit("KB_DATA_BUCKET is required (source scripts/uc29-kb-manifest.local.env).")
    log(f"Region={REGION} Account={ACCOUNT} Collection={COLLECTION} Bucket={DATA_BUCKET}")
    ensure_encryption_policy()
    ensure_network_policy()
    role_arn = ensure_role()
    ensure_access_policy(role_arn)
    time.sleep(10)  # IAM/AOSS policy propagation
    coll_arn, host = ensure_collection()
    ensure_index(host)
    kb_id = ensure_kb(role_arn, coll_arn)
    ds_id = ensure_data_source(kb_id)
    job = agent.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)
    log(f"started ingestion job {job['ingestionJob']['ingestionJobId']}")
    print(json.dumps({"knowledgeBaseId": kb_id, "dataSourceId": ds_id,
                      "collection": COLLECTION, "index": INDEX_NAME}, indent=2))
    log("Rebuild complete. Update UC29 stack params KbId/DataSourceId if redeploying the stack.")


if __name__ == "__main__":
    main()
