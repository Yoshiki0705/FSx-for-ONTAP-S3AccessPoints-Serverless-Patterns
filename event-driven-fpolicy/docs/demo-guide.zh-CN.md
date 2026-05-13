🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

# 事件驱动 FPolicy — 演示指南

## 概述

本演示展示了通过 NFS 的文件创建操作如何通过 ONTAP FPolicy → ECS Fargate → SQS → EventBridge 路径实时转化为事件。

**预计时间**: 10~15 分钟（已部署环境的情况下 3~5 分钟）

---

## 前提条件

| 项目 | 要求 |
|------|------|
| FSx for NetApp ONTAP | ONTAP 9.17.1 以上，支持 FPolicy |
| VPC | 与 FSxN 相同 VPC 中的私有子网 |
| NFS 挂载 | 客户端已 NFS 挂载到 FSxN 卷 |
| AWS CLI | v2 以上，适当的 IAM 权限 |
| Docker | 用于构建容器镜像 |
| ECR | 已创建仓库 |

---

## Step 1: 部署堆栈

### 1.1 构建容器镜像

```bash
cd event-driven-fpolicy/

# ECR 登录
aws ecr get-login-password --region ap-northeast-1 | \
  docker login --username AWS --password-stdin \
  <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com

# 构建 & 推送
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

### 1.3 确认 Fargate 任务 IP

```bash
CLUSTER="fsxn-fpolicy-fsxn-fpolicy-demo"
TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --desired-status RUNNING --query 'taskArns[0]' --output text)
TASK_IP=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)
echo "Fargate Task IP: $TASK_IP"
```

---

## Step 2: ONTAP FPolicy 配置

通过 SSH 连接到 FSxN SVM，执行以下命令。

### 2.1 创建 External Engine

```bash
vserver fpolicy policy external-engine create \
  -vserver FSxN_OnPre \
  -engine-name fpolicy_aws_engine \
  -primary-servers <TASK_IP> \
  -port 9898 \
  -extern-engine-type asynchronous
```

### 2.2 创建 Event

```bash
vserver fpolicy policy event create \
  -vserver FSxN_OnPre \
  -event-name fpolicy_aws_event \
  -protocol cifs,nfsv3,nfsv4 \
  -file-operations create,write,delete,rename
```

### 2.3 创建 Policy

```bash
vserver fpolicy policy create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -events fpolicy_aws_event \
  -engine fpolicy_aws_engine \
  -is-mandatory false
```

### 2.4 配置 Scope

```bash
vserver fpolicy policy scope create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -volumes-to-include "*"
```

### 2.5 启用 Policy

```bash
vserver fpolicy enable \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -sequence-number 1
```

### 2.6 确认连接

```bash
vserver fpolicy show-engine -vserver FSxN_OnPre
# 确认 Status: connected
```

---

## Step 3: 创建测试文件

从已 NFS 挂载的客户端创建文件。

```bash
# NFS 挂载（如未执行）
sudo mount -o vers=4.1 <SVM_DATA_LIF_IP>:/vol1 /mnt/fsxn

# 创建测试文件
echo "FPolicy test $(date)" > /mnt/fsxn/test-fpolicy-event.txt
```

---

## Step 4: 确认 SQS 消息

```bash
QUEUE_URL=$(aws cloudformation describe-stacks \
  --stack-name fsxn-fpolicy-demo \
  --query 'Stacks[0].Outputs[?OutputKey==`IngestionQueueUrl`].OutputValue' \
  --output text)

# 接收消息（用于确认）
aws sqs receive-message \
  --queue-url $QUEUE_URL \
  --max-number-of-messages 5 \
  --wait-time-seconds 10
```

**预期输出**:

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

## Step 5: 确认 EventBridge 事件

在 CloudWatch Logs 中确认事件。

```bash
LOG_GROUP="/aws/events/fsxn-fpolicy-fsxn-fpolicy-demo"

# 获取最新的日志流
STREAM=$(aws logs describe-log-streams \
  --log-group-name $LOG_GROUP \
  --order-by LastEventTime \
  --descending \
  --limit 1 \
  --query 'logStreams[0].logStreamName' \
  --output text)

# 获取日志事件
aws logs get-log-events \
  --log-group-name $LOG_GROUP \
  --log-stream-name $STREAM \
  --limit 5
```

**预期输出**:

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

## Step 6: 确认 IP 自动更新（可选）

强制重启 Fargate 任务，确认 IP 自动更新。

```bash
# 强制停止任务（新任务将自动启动）
aws ecs update-service \
  --cluster fsxn-fpolicy-fsxn-fpolicy-demo \
  --service fsxn-fpolicy-server-fsxn-fpolicy-demo \
  --force-new-deployment

# 等待 30 秒后确认新任务 IP
sleep 30
TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --desired-status RUNNING --query 'taskArns[0]' --output text)
NEW_IP=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)
echo "New Task IP: $NEW_IP"

# 确认 ONTAP engine 的 IP 已更新
# 通过 SSH 连接到 FSxN SVM
vserver fpolicy show-engine -vserver FSxN_OnPre
```

---

## Step 7: 清理

```bash
# 1. 禁用 ONTAP FPolicy
# 通过 SSH 连接到 FSxN SVM
vserver fpolicy disable -vserver FSxN_OnPre -policy-name fpolicy_aws
vserver fpolicy policy scope delete -vserver FSxN_OnPre -policy-name fpolicy_aws
vserver fpolicy policy delete -vserver FSxN_OnPre -policy-name fpolicy_aws
vserver fpolicy policy event delete -vserver FSxN_OnPre -event-name fpolicy_aws_event
vserver fpolicy policy external-engine delete -vserver FSxN_OnPre -engine-name fpolicy_aws_engine

# 2. 删除 CloudFormation 堆栈
aws cloudformation delete-stack \
  --stack-name fsxn-fpolicy-demo \
  --region ap-northeast-1

# 3. 删除测试文件
rm /mnt/fsxn/test-fpolicy-event.txt
```

---

## 故障排除

### 无法连接到 FPolicy Server

1. 确认 Security Group 中是否允许 TCP 9898
2. 确认 Fargate 任务是否处于 RUNNING 状态
3. 确认 ONTAP external-engine 的 IP 是否正确
4. 确认 SQS VPC Endpoint 是否存在

### 消息未到达 SQS

1. 检查 FPolicy Server 日志: `aws logs tail /ecs/fsxn-fpolicy-server-*`
2. 确认 SQS VPC Endpoint 是否存在
3. 确认任务角色是否具有 `sqs:SendMessage` 权限

### 事件未到达 EventBridge

1. 检查 Bridge Lambda 日志
2. 确认 SQS Event Source Mapping 是否已启用
3. 确认 EventBridge 自定义总线名称是否正确

### NFSv4.2 下未检测到事件

NFSv4.2 不支持 ONTAP FPolicy monitoring。请明确指定 `mount -o vers=4.1`。
