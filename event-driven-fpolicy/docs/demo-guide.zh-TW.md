🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

# 事件驅動 FPolicy — 示範指南

## 概述

本示範展示透過 NFS 建立檔案時，如何透過 ONTAP FPolicy → ECS Fargate → SQS → EventBridge 管線即時產生事件。

**預計時間**: 10~15 分鐘（已部署環境下 3~5 分鐘）

---

## 前提條件

| 項目 | 要求 |
|------|------|
| FSx for NetApp ONTAP | ONTAP 9.17.1 以上，支援 FPolicy |
| VPC | 與 FSxN 相同 VPC 中的私有子網路 |
| NFS 掛載 | 用戶端已掛載 FSxN 磁碟區 |
| AWS CLI | v2 以上，具有適當 IAM 權限 |

---

## Step 1: 部署堆疊

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

---

## Step 2: 設定 ONTAP FPolicy

SSH 連線到 FSxN SVM 後執行：

```bash
vserver fpolicy policy external-engine create \
  -vserver FSxN_OnPre \
  -engine-name fpolicy_aws_engine \
  -primary-servers <TASK_IP> \
  -port 9898 \
  -extern-engine-type asynchronous

vserver fpolicy policy event create \
  -vserver FSxN_OnPre \
  -event-name fpolicy_aws_event \
  -protocol cifs,nfsv3,nfsv4 \
  -file-operations create,write,delete,rename

vserver fpolicy policy create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -events fpolicy_aws_event \
  -engine fpolicy_aws_engine \
  -is-mandatory false

vserver fpolicy enable \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -sequence-number 1
```

---

## Step 3: 建立測試檔案

```bash
sudo mount -o vers=4.1 <SVM_DATA_LIF_IP>:/vol1 /mnt/fsxn
echo "FPolicy test $(date)" > /mnt/fsxn/test-fpolicy-event.txt
```

---

## Step 4: 驗證 SQS 訊息

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

## Step 5: 驗證 EventBridge 事件

```bash
LOG_GROUP="/aws/events/fsxn-fpolicy-fsxn-fpolicy-demo"
aws logs tail $LOG_GROUP --since 5m
```

---

## Step 6: 清理

```bash
vserver fpolicy disable -vserver FSxN_OnPre -policy-name fpolicy_aws

aws cloudformation delete-stack \
  --stack-name fsxn-fpolicy-demo \
  --region ap-northeast-1
```

---

## 疑難排解

- **無法連線 FPolicy Server**: 確認 Security Group 允許 TCP 9898，確認 Fargate 任務為 RUNNING 狀態
- **SQS 無訊息**: 確認 SQS VPC Endpoint 存在，確認任務角色權限
- **NFSv4.2 事件未偵測**: 明確指定 `mount -o vers=4.1`
