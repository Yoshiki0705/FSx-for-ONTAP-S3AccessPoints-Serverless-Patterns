🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

# 事件驱动 FPolicy — 演示指南

## 概述

本演示展示通过 NFS 创建文件时，如何通过 ONTAP FPolicy → ECS Fargate → SQS → EventBridge 管道实时生成事件。

**预计时间**: 10~15 分钟（已部署环境下 3~5 分钟）

---

## 前提条件

| 项目 | 要求 |
|------|------|
| FSx for NetApp ONTAP | ONTAP 9.17.1 以上，支持 FPolicy |
| VPC | 与 FSxN 相同 VPC 中的私有子网 |
| NFS 挂载 | 客户端已挂载 FSxN 卷 |
| AWS CLI | v2 以上，具有适当 IAM 权限 |

---

## Step 1: 部署堆栈

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

## Step 2: 配置 ONTAP FPolicy

SSH 连接到 FSxN SVM 后执行：

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

## Step 3: 创建测试文件

```bash
sudo mount -o vers=4.1 <SVM_DATA_LIF_IP>:/vol1 /mnt/fsxn
echo "FPolicy test $(date)" > /mnt/fsxn/test-fpolicy-event.txt
```

---

## Step 4: 验证 SQS 消息

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

## Step 5: 验证 EventBridge 事件

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

## 故障排除

- **无法连接 FPolicy Server**: 确认 Security Group 允许 TCP 9898，确认 Fargate 任务为 RUNNING 状态
- **SQS 无消息**: 确认 SQS VPC Endpoint 存在，确认任务角色权限
- **NFSv4.2 事件未检测**: 明确指定 `mount -o vers=4.1`
