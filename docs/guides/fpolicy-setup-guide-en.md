# FPolicy Setup Guide

**Phase 10 — ONTAP FPolicy Event-Driven Integration**

## Overview

This guide explains how to configure ONTAP FPolicy to forward file operation events to AWS services (SQS → EventBridge → Step Functions).

> ⚠️ **IMPORTANT: Mount with NFSv3. NFSv4 blocks NFS operations with FPolicy external server mode.**

> ⚠️ **IMPORTANT: ONTAP FPolicy protocol does NOT work via NLB TCP passthrough. Use Fargate task direct Private IP.**

## AWS Prerequisites

- `shared/cfn/fpolicy-server-fargate.yaml` stack deployed
- `shared/cfn/fpolicy-ingestion.yaml` stack deployed
- SQS VPC Endpoint available
- ECR/STS/S3/Logs VPC Endpoints available

## ONTAP Prerequisites

- FSx for NetApp ONTAP file system running
- SVM configured with NFS enabled
- Admin access to ONTAP REST API or CLI

## Architecture

```
NFS Client (NFSv3 mount)
  → FSx ONTAP Volume (file create/write/delete/rename)
    → ONTAP FPolicy (async, external engine)
      → ECS Fargate TCP Server (port 9898, direct IP)
        → SQS Ingestion Queue
          → EventBridge Custom Bus
            → Step Functions (per-UC)
```

## Quick Setup

```bash
# 1. Deploy FPolicy Server
./scripts/deploy_fpolicy_server.sh <VPC_ID> <SUBNET_IDS> <FSxN_SVM_SG_ID> <SQS_QUEUE_URL>

# 2. Deploy E2E Demo (bastion + SQS VPC Endpoint)
aws cloudformation deploy \
  --template-file shared/cfn/fpolicy-e2e-demo.yaml \
  --stack-name fsxn-fpolicy-e2e-demo \
  --parameter-overrides VpcId=<VPC> SubnetId=<PUBLIC_SUBNET> \
    PrivateSubnetIds=<PRIV_1>,<PRIV_2> \
    VpcEndpointSecurityGroupId=<SG> KeyPairName=<KEY> \
  --capabilities CAPABILITY_NAMED_IAM

# 3. Get Fargate Task IP
TASK_IP=$(aws ecs describe-tasks --cluster <CLUSTER> \
  --tasks $(aws ecs list-tasks --cluster <CLUSTER> --desired-status RUNNING \
  --query 'taskArns[0]' --output text) \
  --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)

# 4. Configure ONTAP FPolicy (via REST API from bastion)
# Engine
curl -sk -u fsxadmin:<PASS> -X POST 'https://<MGMT_IP>/api/protocols/fpolicy/<SVM_UUID>/engines' \
  -H 'Content-Type: application/json' \
  -d '{"name":"fpolicy_aws_engine","type":"asynchronous","primary_servers":["'$TASK_IP'"],"port":9898}'

# Event (NFSv3 only!)
curl -sk -u fsxadmin:<PASS> -X POST 'https://<MGMT_IP>/api/protocols/fpolicy/<SVM_UUID>/events' \
  -H 'Content-Type: application/json' \
  -d '{"name":"nfsv3_file_events","protocol":"nfsv3","file_operations":{"create":true,"write":true,"delete":true,"rename":true}}'

# Policy + Scope + Enable
curl -sk -u fsxadmin:<PASS> -X POST 'https://<MGMT_IP>/api/protocols/fpolicy/<SVM_UUID>/policies' \
  -H 'Content-Type: application/json' \
  -d '{"name":"fpolicy_aws","mandatory":false,"engine":{"name":"fpolicy_aws_engine"},"events":[{"name":"nfsv3_file_events"}],"scope":{"include_volumes":["<VOLUME>"]},"priority":1}'

# 5. Test (from bastion, NFSv3 mount)
mount -t nfs -o vers=3 <SVM_IP>:/<VOL_PATH> /mnt/fsxn
echo "test" | sudo tee /mnt/fsxn/fpolicy-test.txt

# 6. Verify SQS
aws sqs receive-message --queue-url <QUEUE_URL> --max-number-of-messages 5
```

## Related Documentation

- [Event-Driven README (Quickstart)](../event-driven/README.md)
- [FPolicy Configuration Reference](../event-driven/fpolicy-configuration-reference.md)
- [FPolicy E2E Verification Report](../event-driven/fpolicy-e2e-verification-report.md)
- [FPolicy Server Deployment Architecture](../event-driven/fpolicy-server-deployment-architecture.md)
- [NetApp ONTAP FPolicy Docs](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html)
