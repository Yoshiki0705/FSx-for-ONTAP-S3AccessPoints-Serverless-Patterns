🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

# Event-Driven FPolicy — Demo Guide

## Overview

This demo demonstrates how a file creation operation via NFS is converted into a real-time event through the ONTAP FPolicy → ECS Fargate → SQS → EventBridge pipeline.

**Estimated Time**: 10–15 minutes (3–5 minutes with pre-deployed environment)

---

## Prerequisites

| Item | Requirement |
|------|-------------|
| FSx for NetApp ONTAP | ONTAP 9.17.1 or later, FPolicy capable |
| VPC | Private subnets in same VPC as FSxN |
| NFS Mount | Client with NFS mount to FSxN volume |
| AWS CLI | v2 or later with appropriate IAM permissions |
| Docker | For building container image |
| ECR | Repository created |

---

## Step 1: Deploy the Stack

### 1.1 Build Container Image

```bash
cd event-driven-fpolicy/

aws ecr get-login-password --region ap-northeast-1 | \
  docker login --username AWS --password-stdin \
  <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com

docker buildx build --platform linux/arm64 \
  -f server/Dockerfile \
  -t <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/fsxn-fpolicy-server:latest \
  --push .
```

### 1.2 Deploy CloudFormation

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-fpolicy-demo \
  --parameter-overrides \
    VpcId=vpc-xxxxxxxxx \
    SubnetIds=subnet-aaa,subnet-bbb \
    FsxnSvmSecurityGroupId=sg-xxxxxxxxx \
    ContainerImage=<ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/fsxn-fpolicy-server:latest \
    FsxnMgmtIp=10.0.3.72 \
    FsxnSvmUuid=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
    FsxnCredentialsSecret=fsxn-admin-credentials \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### 1.3 Get Fargate Task IP

```bash
CLUSTER="fsxn-fpolicy-fsxn-fpolicy-demo"
TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --desired-status RUNNING --query 'taskArns[0]' --output text)
TASK_IP=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)
echo "Fargate Task IP: $TASK_IP"
```

---

## Step 2: Configure ONTAP FPolicy

Connect to FSxN SVM via SSH and execute:

```bash
# 1. Create External Engine
vserver fpolicy policy external-engine create \
  -vserver FSxN_OnPre \
  -engine-name fpolicy_aws_engine \
  -primary-servers <TASK_IP> \
  -port 9898 \
  -extern-engine-type asynchronous

# 2. Create Event
vserver fpolicy policy event create \
  -vserver FSxN_OnPre \
  -event-name fpolicy_aws_event \
  -protocol cifs,nfsv3,nfsv4 \
  -file-operations create,write,delete,rename

# 3. Create Policy
vserver fpolicy policy create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -events fpolicy_aws_event \
  -engine fpolicy_aws_engine \
  -is-mandatory false

# 4. Create Scope
vserver fpolicy policy scope create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -volumes-to-include "*"

# 5. Enable Policy
vserver fpolicy enable \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -sequence-number 1

# 6. Verify Connection
vserver fpolicy show-engine -vserver FSxN_OnPre
```

---

## Step 3: Create Test File

```bash
# NFS mount (if not already done)
sudo mount -o vers=4.1 <SVM_DATA_LIF_IP>:/vol1 /mnt/fsxn

# Create test file
echo "FPolicy test $(date)" > /mnt/fsxn/test-fpolicy-event.txt
```

---

## Step 4: Verify SQS Message

```bash
QUEUE_URL=$(aws cloudformation describe-stacks \
  --stack-name fsxn-fpolicy-demo \
  --query 'Stacks[0].Outputs[?OutputKey==`IngestionQueueUrl`].OutputValue' \
  --output text)

aws sqs receive-message \
  --queue-url $QUEUE_URL \
  --max-number-of-messages 5 \
  --wait-time-seconds 10
```

---

## Step 5: Verify EventBridge Event in CloudWatch Logs

```bash
LOG_GROUP="/aws/events/fsxn-fpolicy-fsxn-fpolicy-demo"

STREAM=$(aws logs describe-log-streams \
  --log-group-name $LOG_GROUP \
  --order-by LastEventTime \
  --descending \
  --limit 1 \
  --query 'logStreams[0].logStreamName' \
  --output text)

aws logs get-log-events \
  --log-group-name $LOG_GROUP \
  --log-stream-name $STREAM \
  --limit 5
```

---

## Step 6: Cleanup

```bash
# 1. Disable ONTAP FPolicy
vserver fpolicy disable -vserver FSxN_OnPre -policy-name fpolicy_aws

# 2. Delete CloudFormation stack
aws cloudformation delete-stack \
  --stack-name fsxn-fpolicy-demo \
  --region ap-northeast-1

# 3. Remove test file
rm /mnt/fsxn/test-fpolicy-event.txt
```

---

## Troubleshooting

### Cannot connect to FPolicy Server

1. Verify Security Group allows TCP 9898
2. Confirm Fargate task is in RUNNING state
3. Check ONTAP external-engine IP is correct
4. Verify SQS VPC Endpoint exists

### No messages in SQS

1. Check FPolicy Server logs: `aws logs tail /ecs/fsxn-fpolicy-server-*`
2. Verify SQS VPC Endpoint exists
3. Confirm task role has `sqs:SendMessage` permission

### NFSv4.2 events not detected

NFSv4.2 is not supported by ONTAP FPolicy monitoring. Use `mount -o vers=4.1` explicitly.
