🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

# 事件驅動 FPolicy — 演示指南

## 概述

本演示展示了透過 NFS 的檔案建立操作如何透過 ONTAP FPolicy → ECS Fargate → SQS → EventBridge 路徑即時轉化為事件。

**預計時間**: 10~15 分鐘（已部署環境的情況下 3~5 分鐘）

---

## 前提條件

| 項目 | 要求 |
|------|------|
| FSx for NetApp ONTAP | ONTAP 9.17.1 以上，支援 FPolicy |
| VPC | 與 FSxN 相同 VPC 中的私有子網路 |
| NFS 掛載 | 用戶端已 NFS 掛載到 FSxN 磁碟區 |
| AWS CLI | v2 以上，適當的 IAM 權限 |
| Docker | 用於建置容器映像 |
| ECR | 已建立儲存庫 |

---

## Step 1: 部署堆疊

### 1.1 建置容器映像

```bash
cd event-driven-fpolicy/

# ECR 登入
aws ecr get-login-password --region ap-northeast-1 | \
  docker login --username AWS --password-stdin \
  <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com

# 建置 & 推送
docker buildx build --platform linux/arm64 \
  -f server/Dockerfile \
  -t <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/fsxn-fpolicy-server:latest \
  --push .
```

### 1.2 CloudFormation 部署

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

### 1.3 確認 Fargate 任務 IP

```bash
CLUSTER="fsxn-fpolicy-fsxn-fpolicy-demo"
TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --desired-status RUNNING --query 'taskArns[0]' --output text)
TASK_IP=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)
echo "Fargate Task IP: $TASK_IP"
```

---

## Step 2: ONTAP FPolicy 設定

透過 SSH 連線到 FSxN SVM，執行以下命令。

### 2.1 建立 External Engine

```bash
fpolicy policy external-engine create \
  -vserver FSxN_OnPre \
  -engine-name fpolicy_aws_engine \
  -primary-servers <TASK_IP> \
  -port 9898 \
  -extern-engine-type asynchronous
```

### 2.2 建立 Event

```bash
fpolicy policy event create \
  -vserver FSxN_OnPre \
  -event-name fpolicy_aws_event \
  -protocol cifs,nfsv3,nfsv4 \
  -file-operations create,write,delete,rename
```

### 2.3 建立 Policy

```bash
fpolicy policy create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -events fpolicy_aws_event \
  -engine fpolicy_aws_engine \
  -is-mandatory false
```

### 2.4 設定 Scope

```bash
fpolicy policy scope create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -volumes-to-include "*"
```

### 2.5 啟用 Policy

```bash
fpolicy enable \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -sequence-number 1
```

### 2.6 確認連線

```bash
fpolicy show-engine -vserver FSxN_OnPre
# 確認 Status: connected
```

---

## Step 3: 建立測試檔案

從已 NFS 掛載的用戶端建立檔案。

```bash
# NFS 掛載（如未執行）
sudo mount -o vers=4.1 <SVM_DATA_LIF_IP>:/vol1 /mnt/fsxn

# 建立測試檔案
echo "FPolicy test $(date)" > /mnt/fsxn/test-fpolicy-event.txt
```

---

## Step 4: 確認 SQS 訊息

```bash
QUEUE_URL=$(aws cloudformation describe-stacks \
  --stack-name fsxn-fpolicy-demo \
  --query 'Stacks[0].Outputs[?OutputKey==`IngestionQueueUrl`].OutputValue' \
  --output text)

# 接收訊息（用於確認）
aws sqs receive-message \
  --queue-url $QUEUE_URL \
  --max-number-of-messages 5 \
  --wait-time-seconds 10
```

**預期輸出**:

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

## Step 5: 確認 EventBridge 事件

在 CloudWatch Logs 中確認事件。

```bash
LOG_GROUP="/aws/events/fsxn-fpolicy-fsxn-fpolicy-demo"

# 取得最新的日誌串流
STREAM=$(aws logs describe-log-streams \
  --log-group-name $LOG_GROUP \
  --order-by LastEventTime \
  --descending \
  --limit 1 \
  --query 'logStreams[0].logStreamName' \
  --output text)

# 取得日誌事件
aws logs get-log-events \
  --log-group-name $LOG_GROUP \
  --log-stream-name $STREAM \
  --limit 5
```

**預期輸出**:

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

## Step 6: 確認 IP 自動更新（選用）

強制重新啟動 Fargate 任務，確認 IP 自動更新。

```bash
# 強制停止任務（新任務將自動啟動）
aws ecs update-service \
  --cluster fsxn-fpolicy-fsxn-fpolicy-demo \
  --service fsxn-fpolicy-server-fsxn-fpolicy-demo \
  --force-new-deployment

# 等待 30 秒後確認新任務 IP
sleep 30
TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --desired-status RUNNING --query 'taskArns[0]' --output text)
NEW_IP=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)
echo "New Task IP: $NEW_IP"

# 確認 ONTAP engine 的 IP 已更新
# 透過 SSH 連線到 FSxN SVM
fpolicy show-engine -vserver FSxN_OnPre
```

---

## Step 7: 清理

```bash
# 1. 停用 ONTAP FPolicy
# 透過 SSH 連線到 FSxN SVM
fpolicy disable -vserver FSxN_OnPre -policy-name fpolicy_aws
fpolicy policy scope delete -vserver FSxN_OnPre -policy-name fpolicy_aws
fpolicy policy delete -vserver FSxN_OnPre -policy-name fpolicy_aws
fpolicy policy event delete -vserver FSxN_OnPre -event-name fpolicy_aws_event
fpolicy policy external-engine delete -vserver FSxN_OnPre -engine-name fpolicy_aws_engine

# 2. 刪除 CloudFormation 堆疊
aws cloudformation delete-stack \
  --stack-name fsxn-fpolicy-demo \
  --region ap-northeast-1

# 3. 刪除測試檔案
rm /mnt/fsxn/test-fpolicy-event.txt
```

---

## 疑難排解

### 無法連線到 FPolicy Server

1. 確認 Security Group 中是否允許 TCP 9898
2. 確認 Fargate 任務是否處於 RUNNING 狀態
3. 確認 ONTAP external-engine 的 IP 是否正確
4. 確認 SQS VPC Endpoint 是否存在

### 訊息未到達 SQS

1. 檢查 FPolicy Server 日誌: `aws logs tail /ecs/fsxn-fpolicy-server-*`
2. 確認 SQS VPC Endpoint 是否存在
3. 確認任務角色是否具有 `sqs:SendMessage` 權限

### 事件未到達 EventBridge

1. 檢查 Bridge Lambda 日誌
2. 確認 SQS Event Source Mapping 是否已啟用
3. 確認 EventBridge 自訂匯流排名稱是否正確

### NFSv4.2 下未偵測到事件

NFSv4.2 不支援 ONTAP FPolicy monitoring。請明確指定 `mount -o vers=4.1`。
