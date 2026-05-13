🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

# イベント駆動 FPolicy — デモガイド

## 概要

本デモでは、NFS 経由のファイル作成操作が ONTAP FPolicy → ECS Fargate → SQS → EventBridge の経路でリアルタイムにイベント化される様子を実演します。

**想定時間**: 10〜15 分（デプロイ済み環境の場合 3〜5 分）

---

## 前提条件

| 項目 | 要件 |
|------|------|
| FSx for NetApp ONTAP | ONTAP 9.17.1 以上、FPolicy 対応 |
| VPC | FSxN と同一 VPC にプライベートサブネット |
| NFS マウント | クライアントから FSxN ボリュームに NFS マウント済み |
| AWS CLI | v2 以上、適切な IAM 権限 |
| Docker | コンテナイメージビルド用 |
| ECR | リポジトリ作成済み |

---

## Step 1: スタックのデプロイ

### 1.1 コンテナイメージのビルド

```bash
cd event-driven-fpolicy/

# ECR ログイン
aws ecr get-login-password --region ap-northeast-1 | \
  docker login --username AWS --password-stdin \
  <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com

# ビルド & プッシュ
docker buildx build --platform linux/arm64 \
  -f server/Dockerfile \
  -t <ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/fsxn-fpolicy-server:latest \
  --push .
```

### 1.2 CloudFormation デプロイ

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

### 1.3 Fargate タスク IP の確認

```bash
CLUSTER="fsxn-fpolicy-fsxn-fpolicy-demo"
TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --desired-status RUNNING --query 'taskArns[0]' --output text)
TASK_IP=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)
echo "Fargate Task IP: $TASK_IP"
```

---

## Step 2: ONTAP FPolicy 設定

FSxN SVM に SSH 接続し、以下のコマンドを実行します。

### 2.1 External Engine 作成

```bash
vserver fpolicy policy external-engine create \
  -vserver FSxN_OnPre \
  -engine-name fpolicy_aws_engine \
  -primary-servers <TASK_IP> \
  -port 9898 \
  -extern-engine-type asynchronous
```

### 2.2 Event 作成

```bash
vserver fpolicy policy event create \
  -vserver FSxN_OnPre \
  -event-name fpolicy_aws_event \
  -protocol cifs,nfsv3,nfsv4 \
  -file-operations create,write,delete,rename
```

### 2.3 Policy 作成

```bash
vserver fpolicy policy create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -events fpolicy_aws_event \
  -engine fpolicy_aws_engine \
  -is-mandatory false
```

### 2.4 Scope 設定

```bash
vserver fpolicy policy scope create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -volumes-to-include "*"
```

### 2.5 Policy 有効化

```bash
vserver fpolicy enable \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -sequence-number 1
```

### 2.6 接続確認

```bash
vserver fpolicy show-engine -vserver FSxN_OnPre
# Status: connected であることを確認
```

---

## Step 3: テストファイル作成

NFS マウント済みのクライアントからファイルを作成します。

```bash
# NFS マウント（未実施の場合）
sudo mount -o vers=4.1 <SVM_DATA_LIF_IP>:/vol1 /mnt/fsxn

# テストファイル作成
echo "FPolicy test $(date)" > /mnt/fsxn/test-fpolicy-event.txt
```

---

## Step 4: SQS メッセージの確認

```bash
QUEUE_URL=$(aws cloudformation describe-stacks \
  --stack-name fsxn-fpolicy-demo \
  --query 'Stacks[0].Outputs[?OutputKey==`IngestionQueueUrl`].OutputValue' \
  --output text)

# メッセージ受信（確認用）
aws sqs receive-message \
  --queue-url $QUEUE_URL \
  --max-number-of-messages 5 \
  --wait-time-seconds 10
```

**期待される出力**:

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

## Step 5: EventBridge イベントの確認

CloudWatch Logs でイベントを確認します。

```bash
LOG_GROUP="/aws/events/fsxn-fpolicy-fsxn-fpolicy-demo"

# 最新のログストリームを取得
STREAM=$(aws logs describe-log-streams \
  --log-group-name $LOG_GROUP \
  --order-by LastEventTime \
  --descending \
  --limit 1 \
  --query 'logStreams[0].logStreamName' \
  --output text)

# ログイベント取得
aws logs get-log-events \
  --log-group-name $LOG_GROUP \
  --log-stream-name $STREAM \
  --limit 5
```

**期待される出力**:

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

## Step 6: IP 自動更新の確認（オプション）

Fargate タスクを強制再起動し、IP 自動更新を確認します。

```bash
# タスク強制停止（新タスクが自動起動される）
aws ecs update-service \
  --cluster fsxn-fpolicy-fsxn-fpolicy-demo \
  --service fsxn-fpolicy-server-fsxn-fpolicy-demo \
  --force-new-deployment

# 30秒待機後、新しいタスク IP を確認
sleep 30
TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --desired-status RUNNING --query 'taskArns[0]' --output text)
NEW_IP=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)
echo "New Task IP: $NEW_IP"

# ONTAP engine の IP が更新されていることを確認
# SSH で FSxN SVM に接続
vserver fpolicy show-engine -vserver FSxN_OnPre
```

---

## Step 7: クリーンアップ

```bash
# 1. ONTAP FPolicy 無効化
# SSH で FSxN SVM に接続
vserver fpolicy disable -vserver FSxN_OnPre -policy-name fpolicy_aws
vserver fpolicy policy scope delete -vserver FSxN_OnPre -policy-name fpolicy_aws
vserver fpolicy policy delete -vserver FSxN_OnPre -policy-name fpolicy_aws
vserver fpolicy policy event delete -vserver FSxN_OnPre -event-name fpolicy_aws_event
vserver fpolicy policy external-engine delete -vserver FSxN_OnPre -engine-name fpolicy_aws_engine

# 2. CloudFormation スタック削除
aws cloudformation delete-stack \
  --stack-name fsxn-fpolicy-demo \
  --region ap-northeast-1

# 3. テストファイル削除
rm /mnt/fsxn/test-fpolicy-event.txt
```

---

## トラブルシューティング

### FPolicy Server に接続できない

1. Security Group で TCP 9898 が許可されているか確認
2. Fargate タスクが RUNNING 状態か確認
3. ONTAP external-engine の IP が正しいか確認
4. SQS VPC Endpoint が存在するか確認

### SQS にメッセージが届かない

1. FPolicy Server のログを確認: `aws logs tail /ecs/fsxn-fpolicy-server-*`
2. SQS VPC Endpoint が存在するか確認
3. タスクロールに `sqs:SendMessage` 権限があるか確認

### EventBridge にイベントが届かない

1. Bridge Lambda のログを確認
2. SQS Event Source Mapping が有効か確認
3. EventBridge カスタムバス名が正しいか確認

### NFSv4.2 でイベントが検知されない

NFSv4.2 は ONTAP FPolicy monitoring に非対応です。`mount -o vers=4.1` を明示的に指定してください。
