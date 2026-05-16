🌐 **Language / 言語**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

# Event-Driven FPolicy — Demo Guide

## Overview

This demo demonstrates how file creation operations via NFS are converted into real-time events through the ONTAP FPolicy → ECS Fargate → SQS → EventBridge path.

**Estimated Time**: 10–15 minutes (3–5 minutes with a pre-deployed environment)

---

## Prerequisites

| Item | Requirement |
|------|-------------|
| FSx for NetApp ONTAP | ONTAP 9.17.1 or later, FPolicy supported |
| VPC | Private subnet in the same VPC as FSxN |
| NFS Mount | NFS mounted from client to FSxN volume |
| AWS CLI | v2 or later, appropriate IAM permissions |
| Docker | For building container images |
| ECR | Repository created |

---

## Step 1: Deploy the Stack

### 1.1 Build the Container Image

```bash
cd event-driven-fpolicy/

# ECR Login
aws ecr get-login-password --region ap-northeast-1 | \
  docker login --username AWS --password-stdin \
  <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com

# Build & Push
docker buildx build --platform linux/arm64 \
  -f server/Dockerfile \
  -t <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/fsxn-fpolicy-server:latest \
  --push .
```

### 1.2 CloudFormation Deploy

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

### 1.3 Confirm Fargate Task IP

```bash
CLUSTER="fsxn-fpolicy-fsxn-fpolicy-demo"
TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --desired-status RUNNING --query 'taskArns[0]' --output text)
TASK_IP=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)
echo "Fargate Task IP: $TASK_IP"
```

---

## Step 2: ONTAP FPolicy Configuration

Connect to the FSxN SVM via SSH and execute the following commands.

### 2.1 Create External Engine

```bash
fpolicy policy external-engine create \
  -vserver FSxN_OnPre \
  -engine-name fpolicy_aws_engine \
  -primary-servers <TASK_IP> \
  -port 9898 \
  -extern-engine-type asynchronous
```

### 2.2 Create Event

```bash
fpolicy policy event create \
  -vserver FSxN_OnPre \
  -event-name fpolicy_aws_event \
  -protocol cifs,nfsv3,nfsv4 \
  -file-operations create,write,delete,rename
```

### 2.3 Create Policy

```bash
fpolicy policy create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -events fpolicy_aws_event \
  -engine fpolicy_aws_engine \
  -is-mandatory false
```

### 2.4 Configure Scope

```bash
fpolicy policy scope create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -volumes-to-include "*"
```

### 2.5 Enable Policy

```bash
fpolicy enable \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -sequence-number 1
```

### 2.6 Verify Connection

```bash
fpolicy show-engine -vserver FSxN_OnPre
# Confirm Status: connected
```

---

## Step 3: Create Test File

Create a file from the NFS-mounted client.

```bash
# NFS Mount (if not already done)
sudo mount -o vers=4.1 <SVM_DATA_LIF_IP>:/vol1 /mnt/fsxn

# Create test file
echo "FPolicy test $(date)" > /mnt/fsxn/test-fpolicy-event.txt
```

---

## Step 4: Verify SQS Messages

```bash
QUEUE_URL=$(aws cloudformation describe-stacks \
  --stack-name fsxn-fpolicy-demo \
  --query 'Stacks[0].Outputs[?OutputKey==`IngestionQueueUrl`].OutputValue' \
  --output text)

# Receive messages (for verification)
aws sqs receive-message \
  --queue-url $QUEUE_URL \
  --max-number-of-messages 5 \
  --wait-time-seconds 10
```

**Expected Output**:

```json
{
  "Messages": [
    {
      "Body": "{\"event_id\":\"...\",\"operation_type\":\"create\",\"file_path\":\"test-fpolicy-event.txt\",\"volume_name\":\"vol1\",\"svm_name\":\"FSxN_OnPre\",\"timestamp\":\"...\",\"file_size\":0}"
    }
  ]
}
```

---

## Step 5: Verify EventBridge Events

Verify events in CloudWatch Logs.

```bash
LOG_GROUP="/aws/events/fsxn-fpolicy-fsxn-fpolicy-demo"

# Get the latest log stream
STREAM=$(aws logs describe-log-streams \
  --log-group-name $LOG_GROUP \
  --order-by LastEventTime \
  --descending \
  --limit 1 \
  --query 'logStreams[0].logStreamName' \
  --output text)

# Get log events
aws logs get-log-events \
  --log-group-name $LOG_GROUP \
  --log-stream-name $STREAM \
  --limit 5
```

**Expected Output**:

```json
{
  "source": "fsxn.fpolicy",
  "detail-type": "FPolicy File Operation",
  "detail": {
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "operation_type": "create",
    "file_path": "test-fpolicy-event.txt",
    "volume_name": "vol1",
    "svm_name": "FSxN_OnPre",
    "timestamp": "2026-01-15T10:30:00+00:00",
    "file_size": 0
  }
}
```

---

## Step 6: Verify IP Auto-Update (Optional)

Force restart the Fargate task and verify the IP auto-update.

```bash
# Force stop task (new task will start automatically)
aws ecs update-service \
  --cluster fsxn-fpolicy-fsxn-fpolicy-demo \
  --service fsxn-fpolicy-server-fsxn-fpolicy-demo \
  --force-new-deployment

# Wait 30 seconds, then check new task IP
sleep 30
TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --desired-status RUNNING --query 'taskArns[0]' --output text)
NEW_IP=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)
echo "New Task IP: $NEW_IP"

# Verify that the ONTAP engine IP has been updated
# Connect to FSxN SVM via SSH
fpolicy show-engine -vserver FSxN_OnPre
```

---

## Step 7: Cleanup

```bash
# 1. Disable ONTAP FPolicy
# Connect to FSxN SVM via SSH
fpolicy disable -vserver FSxN_OnPre -policy-name fpolicy_aws
fpolicy policy scope delete -vserver FSxN_OnPre -policy-name fpolicy_aws
fpolicy policy delete -vserver FSxN_OnPre -policy-name fpolicy_aws
fpolicy policy event delete -vserver FSxN_OnPre -event-name fpolicy_aws_event
fpolicy policy external-engine delete -vserver FSxN_OnPre -engine-name fpolicy_aws_engine

# 2. Delete CloudFormation stack
aws cloudformation delete-stack \
  --stack-name fsxn-fpolicy-demo \
  --region ap-northeast-1

# 3. Delete test file
rm /mnt/fsxn/test-fpolicy-event.txt
```

---

## Troubleshooting

### Cannot Connect to FPolicy Server

1. Verify that TCP 9898 is allowed in the Security Group
2. Verify that the Fargate task is in RUNNING state
3. Verify that the ONTAP external-engine IP is correct
4. Verify that the SQS VPC Endpoint exists

### Messages Not Arriving in SQS

1. Check FPolicy Server logs: `aws logs tail /ecs/fsxn-fpolicy-server-*`
2. Verify that the SQS VPC Endpoint exists
3. Verify that the task role has `sqs:SendMessage` permission

### Events Not Arriving in EventBridge

1. Check Bridge Lambda logs
2. Verify that SQS Event Source Mapping is enabled
3. Verify that the EventBridge custom bus name is correct

### Events Not Detected with NFSv4.2

NFSv4.2 is not supported for ONTAP FPolicy monitoring. Explicitly specify `mount -o vers=4.1`.
