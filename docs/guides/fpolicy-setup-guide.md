# FPolicy セットアップガイド

**Phase 10 — ONTAP FPolicy イベント駆動統合**

## 概要

本ガイドでは、FSx for NetApp ONTAP の FPolicy 機能を使用して、
ファイル操作イベントを AWS サービス（SQS → EventBridge → Step Functions）に
転送するための設定手順を説明する。

## 前提条件

### AWS 側
- `shared/cfn/fpolicy-ingestion.yaml` スタックがデプロイ済み
- `shared/cfn/fpolicy-routing.yaml` スタックがデプロイ済み
- SQS Ingestion Queue URL が取得済み
- FPolicy Engine Lambda ARN が取得済み

### ONTAP 側
- FSx for NetApp ONTAP ファイルシステムが作成済み
- SVM（Storage Virtual Machine）が設定済み
- 管理者権限でのアクセスが可能

## アーキテクチャ

```
ONTAP SVM (ファイル操作)
  → FPolicy Engine (外部サーバー / Lambda)
    → SQS Ingestion Queue
      → SQS → EventBridge Bridge Lambda
        → EventBridge Custom Bus
          → UC 別 EventBridge Rule
            → Step Functions
```

## ONTAP FPolicy 設定手順

### Step 1: FPolicy 外部エンジンの登録

```bash
# ONTAP CLI で外部エンジンを登録
# FPolicy Engine Lambda の Function URL または ALB エンドポイントを指定

vserver fpolicy policy external-engine create \
  -vserver <svm_name> \
  -engine-name fpolicy-aws-engine \
  -primary-servers <fpolicy_engine_endpoint_ip> \
  -port 9898 \
  -extern-engine-type asynchronous \
  -ssl-option no-auth
```

**パラメータ説明:**
- `-vserver`: SVM 名
- `-engine-name`: エンジン識別名（任意）
- `-primary-servers`: FPolicy Engine のエンドポイント IP
- `-port`: FPolicy Engine のリスニングポート
- `-extern-engine-type`: `asynchronous`（非同期モード = 通知のみ、ブロックなし）
- `-ssl-option`: SSL 設定（本番環境では `server-auth` 推奨）

### Step 2: FPolicy イベントの定義

```bash
# 監視対象のファイル操作を定義
vserver fpolicy policy event create \
  -vserver <svm_name> \
  -event-name fpolicy-file-events \
  -protocol cifs \
  -file-operations create,write,delete,rename \
  -filters first-write
```

**パラメータ説明:**
- `-event-name`: イベント定義名
- `-protocol`: 監視プロトコル（`cifs` = SMB, `nfsv3`, `nfsv4`）
- `-file-operations`: 監視対象操作
- `-filters`: `first-write` = 最初の書き込みのみ通知（重複削減）

### Step 3: FPolicy ポリシーの作成

```bash
# FPolicy ポリシーを作成
vserver fpolicy policy create \
  -vserver <svm_name> \
  -policy-name fpolicy-aws-notify \
  -events fpolicy-file-events \
  -engine fpolicy-aws-engine \
  -is-mandatory false
```

**パラメータ説明:**
- `-policy-name`: ポリシー名
- `-events`: Step 2 で作成したイベント定義
- `-engine`: Step 1 で作成した外部エンジン
- `-is-mandatory`: `false` = エンジン接続失敗時もファイル操作を許可

### Step 4: FPolicy ポリシーの有効化

```bash
# ポリシーを有効化（優先度 1 = 最高優先度）
vserver fpolicy enable \
  -vserver <svm_name> \
  -policy-name fpolicy-aws-notify \
  -sequence-number 1
```

### Step 5: スコープの設定（オプション）

```bash
# 特定のボリューム/ディレクトリのみ監視する場合
vserver fpolicy policy scope create \
  -vserver <svm_name> \
  -policy-name fpolicy-aws-notify \
  -volumes-to-include vol1,vol2 \
  -export-policies-to-include default
```

## 動作確認

### FPolicy 接続状態の確認

```bash
# FPolicy エンジンの接続状態を確認
vserver fpolicy show-engine \
  -vserver <svm_name> \
  -engine-name fpolicy-aws-engine

# FPolicy ポリシーの状態を確認
vserver fpolicy show \
  -vserver <svm_name>
```

### テストファイルの作成

```bash
# SMB/NFS 経由でテストファイルを作成
echo "test" > /mnt/fsxn/vol1/products/test-fpolicy.txt

# SQS キューにメッセージが到着したか確認
aws sqs get-queue-attributes \
  --queue-url <ingestion_queue_url> \
  --attribute-names ApproximateNumberOfMessages
```

### EventBridge イベントの確認

```bash
# CloudWatch Logs で Bridge Lambda のログを確認
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-fpolicy-bridge-<stack_name> \
  --start-time $(date -d '5 minutes ago' +%s000)
```

## トラブルシューティング

### 問題 1: FPolicy エンジンが接続されない

**症状**: `vserver fpolicy show-engine` で `disconnected` 状態

**原因と対処:**
1. Security Group でポート 9898 のインバウンドが許可されているか確認
2. FPolicy Engine のエンドポイント IP が正しいか確認
3. FPolicy Engine Lambda/ECS タスクが起動しているか確認

### 問題 2: イベントが SQS に到着しない

**症状**: ファイル操作後も SQS キューが空

**原因と対処:**
1. FPolicy ポリシーが有効化されているか確認（`vserver fpolicy show`）
2. スコープ設定で対象ボリュームが含まれているか確認
3. FPolicy Engine Lambda の CloudWatch Logs でエラーを確認
4. `-is-mandatory false` が設定されているか確認（true の場合、接続失敗でファイル操作がブロックされる）

### 問題 3: スキーマバリデーション失敗

**症状**: DLQ にメッセージが蓄積

**原因と対処:**
1. DLQ メッセージの `validation_errors` フィールドを確認
2. FPolicy Engine のイベント変換ロジックを確認
3. JSON Schema (`shared/schemas/fpolicy-event-schema.json`) との整合性を確認

### 問題 4: EventBridge ルールが一致しない

**症状**: SQS → EventBridge は成功するが Step Functions が起動しない

**原因と対処:**
1. EventBridge ルールのパターンを確認（ファイルパスプレフィックス、拡張子）
2. CloudTrail で EventBridge イベントの配信状態を確認
3. Step Functions の実行ロールに `states:StartExecution` 権限があるか確認

## セキュリティ考慮事項

### 本番環境での推奨設定

1. **SSL/TLS**: `-ssl-option server-auth` で暗号化通信を有効化
2. **ネットワーク分離**: FPolicy Engine を Private Subnet に配置
3. **IAM 最小権限**: FPolicy Engine Lambda に SQS 送信のみ許可
4. **DLQ 監視**: DLQ メッセージ数のアラームを設定
5. **ログ保持**: CloudWatch Logs の保持期間を設定（30 日推奨）

### Lambda パッケージング注意事項（Phase 10 デプロイ知見）

1. **jsonschema バージョン**: `4.17.x` を使用すること。`4.18+` は `rpds-py` に依存し、ARM64 Lambda 環境でネイティブバイナリの互換性問題が発生する
2. **スキーマファイル配置**: `fpolicy-event-schema.json` は `handler.py` と同一ディレクトリに配置
3. **SCHEMA_PATH 環境変数**: Lambda 環境変数で `fpolicy-event-schema.json`（相対パス）を指定
4. **パッケージングスクリプト**: `scripts/package_fpolicy_lambdas.sh` を使用して再現可能なビルドを実行
5. **Guard Hook**: `Resource: "*"` は Guard ルール違反。`arn:aws:cloudwatch:${Region}:${AccountId}:*` 形式を使用

### EventBridge Archive の制限事項

EventBridge Archive リソースは CloudFormation の PropertyValidation で失敗する場合がある。
Archive が必要な場合は、メインスタックとは別に手動作成するか、スタック更新で追加する。

### FPolicy Server (ECS Fargate) デプロイ知見

#### NLB 非互換（重要）

**ONTAP FPolicy プロトコルは NLB TCP パススルー経由では動作しない。**

- ONTAP FPolicy はバイナリフレーミング（`"` + 4バイト長 + `"` + payload）を使用
- NLB がこのフレーミングを正しく中継できない（接続確立後にデータが届かない）
- ONTAP external-engine には **Fargate タスクの直接 Private IP** を指定すること
- NLB はヘルスチェック + サービスディスカバリ用途のみ

#### タイムアウト設定

- サーバーの `conn.settimeout` は **300 秒以上** に設定すること
- ONTAP の `keep_alive_interval` デフォルトは 2 分（120 秒）
- タイムアウトが keep_alive_interval 以下だと、KEEP_ALIVE 受信前に切断される

#### VPC Endpoints 要件

ECS Fargate (Private Subnet) には以下の VPC Endpoints が必須:

| Endpoint | Type | 用途 |
|----------|------|------|
| `com.amazonaws.<region>.ecr.dkr` | Interface | コンテナイメージプル |
| `com.amazonaws.<region>.ecr.api` | Interface | ECR 認証トークン取得 |
| `com.amazonaws.<region>.s3` | Gateway | ECR イメージレイヤー（S3 経由） |
| `com.amazonaws.<region>.logs` | Interface | CloudWatch Logs 出力 |
| `com.amazonaws.<region>.sts` | Interface | IAM ロール認証 |
| `com.amazonaws.<region>.sqs` | Interface | SQS メッセージ送信（realtime モード） |

#### Security Group 設定

```
FPolicy Server SG:
  Inbound: TCP 9898 from 10.0.0.0/8 (VPC CIDR — NLB health check + ONTAP data LIF)
  Outbound: TCP 443 to 0.0.0.0/0 (VPC Endpoints 経由)

VPC Endpoint SG (default SG):
  Inbound: TCP 443 from 10.0.0.0/16 (VPC CIDR 全体)
```

#### NFSv3 イベント設定

FPolicy イベントはプロトコル別に作成する必要がある:

```bash
# CIFS (SMB) 用
vserver fpolicy policy event create \
  -vserver SVM_NAME -event-name fpolicy_cifs_events \
  -protocol cifs -file-operations create,write,delete,rename

# NFSv3 用（別イベントとして作成）
vserver fpolicy policy event create \
  -vserver SVM_NAME -event-name fpolicy_nfs_events \
  -protocol nfsv3 -file-operations create,write,delete,rename

# ポリシーに両方のイベントを紐付け
# REST API: {"events": [{"name": "fpolicy_cifs_events"}, {"name": "fpolicy_nfs_events"}]}
```

## SMB (CIFS) テスト手順（Active Directory 必須）

### 前提条件（SMB 追加）

- AWS Managed Microsoft AD（または Self-Managed AD）
- FSxN SVM が AD ドメインに参加済み（**SVM 作成時に AD 設定を含める必要あり**）
- CIFS 共有が作成済み

### SMB 環境構築手順

```bash
# 1. AWS Managed Microsoft AD 作成（20-30 分）
aws ds create-microsoft-ad \
  --name fpolicy.local --short-name FPOLICY \
  --password '<AD_PASSWORD>' \
  --vpc-settings VpcId=<VPC>,SubnetIds=<SUBNET1>,<SUBNET2> \
  --edition Standard --region ap-northeast-1

# 2. FSxN SVM 作成（AD 参加付き）
# 重要: 既存の NFS 専用 SVM に後から CIFS を追加することはできない（FSxN の制約）
aws fsx create-storage-virtual-machine \
  --file-system-id <FS_ID> --name FPolicySMB \
  --active-directory-configuration \
    'NetBiosName=FPOLSMB,SelfManagedActiveDirectoryConfiguration={DomainName=fpolicy.local,UserName=Admin,Password=<AD_PASSWORD>,DnsIps=[<AD_DNS1>,<AD_DNS2>],OrganizationalUnitDistinguishedName="OU=Computers,OU=fpolicy,DC=fpolicy,DC=local"}' \
  --root-volume-security-style NTFS

# 3. ボリューム作成（NTFS セキュリティスタイル）
aws fsx create-volume --volume-type ONTAP --name smb_test_vol \
  --ontap-configuration '{
    "JunctionPath": "/smb_test",
    "StorageVirtualMachineId": "<SVM_ID>",
    "SizeInMegabytes": 1024,
    "SecurityStyle": "NTFS"
  }'

# 4. CIFS 共有作成（ONTAP REST API）
curl -sk -u fsxadmin:<PASS> -X POST \
  'https://<MGMT_IP>/api/protocols/cifs/shares' \
  -H 'Content-Type: application/json' \
  -d '{"svm":{"uuid":"<SVM_UUID>"},"name":"smb_test","path":"/smb_test"}'

# 5. FPolicy 設定（CIFS イベント）
# Engine: 同じ fpolicy_aws_engine を使用
# Event: protocol=cifs, file_operations=create,write,delete,rename
# Policy: 同じ構成

# 6. SMB テスト
smbclient //<SVM_IP>/smb_test -U 'FPOLICY\Admin%<AD_PASSWORD>' \
  --option='client min protocol=SMB2' \
  -c 'put /tmp/test.txt SMB-FPOLICY-TEST.txt'

# 7. SQS 確認
aws sqs receive-message --queue-url <QUEUE_URL> --max-number-of-messages 5
```

### SMB 固有の注意事項

- **SVM 作成時に AD 設定必須**: FSxN では既存 NFS 専用 SVM に後から CIFS プロトコルを追加できない
- **OU 指定**: AWS Managed AD では `OU=Computers,OU=<domain>,DC=<domain>,DC=local` を使用
- **SMB ポート 445**: SVM に CIFS プロトコルが含まれている場合のみ開放される
- **認証**: AD ユーザー（`DOMAIN\username`）で認証。`fsxadmin` では SMB 認証不可

---

## 関連ドキュメント

- [イベント駆動 README（クイックスタート）](../event-driven/README.md)
- [イベント駆動アーキテクチャ設計](../event-driven/architecture-design.md)
- [FPolicy 設定リファレンス](../event-driven/fpolicy-configuration-reference.md)
- [FPolicy E2E 検証レポート](../event-driven/fpolicy-e2e-verification-report.md)
- [FPolicy Server デプロイアーキテクチャ](../event-driven/fpolicy-server-deployment-architecture.md)
- [移行ガイド](../event-driven/migration-guide.md)
- [ONTAP FPolicy ドキュメント](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html)
- [FSx for ONTAP FPolicy](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/file-access-auditing.html)

---

## E2E 検証手順（VPC 内アクセス必要）

以下の手順は VPC 内の EC2 インスタンスから実行する必要がある。

### 前提条件

- VPC 内の EC2 に SSH アクセス可能
- FSxN SVM 管理エンドポイント（<SVM_MGMT_IP>）に SSH 可能
- fsxadmin パスワードを把握

### Step 1: NLB Private IP の確認

```bash
aws ec2 describe-network-interfaces \
  --filters "Name=description,Values=ELB net/fp-nlb-fsxn-fp-srv/*" \
  --query 'NetworkInterfaces[*].PrivateIpAddress' --output text
```

### Step 2: ONTAP FPolicy 設定（SVM 管理 CLI）

```bash
# EC2 から FSxN SVM に SSH
ssh fsxadmin@<SVM_MGMT_IP>

# 外部エンジン作成
vserver fpolicy policy external-engine create \
  -vserver FSxN_OnPre \
  -engine-name fpolicy_aws_engine \
  -primary-servers <NLB_PRIVATE_IP> \
  -port 9898 \
  -extern-engine-type asynchronous

# イベント定義
vserver fpolicy policy event create \
  -vserver FSxN_OnPre \
  -event-name fpolicy_file_events \
  -protocol cifs \
  -file-operations create,write,delete,rename

# ポリシー作成
vserver fpolicy policy create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -events fpolicy_file_events \
  -engine fpolicy_aws_engine \
  -is-mandatory false

# スコープ設定
vserver fpolicy policy scope create \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -volumes-to-include "*"

# 有効化
vserver fpolicy enable \
  -vserver FSxN_OnPre \
  -policy-name fpolicy_aws \
  -sequence-number 1

# 接続確認
vserver fpolicy show-engine -vserver FSxN_OnPre
```

### Step 3: テストファイル作成

```bash
# NFSv4.1 でマウント（推奨）
# 重要: vers=4 は NFSv4.2 にネゴシエートされ FPolicy 非サポート
sudo mount -t nfs -o vers=4.1 <SVM_IP>:/vol1 /mnt/fsxn

# テストファイル作成
echo "fpolicy e2e test $(date)" > /mnt/fsxn/test-fpolicy-event.txt
```

### Step 4: FPolicy Server ログ確認

```bash
aws logs filter-log-events \
  --log-group-name "/ecs/fsxn-fpolicy-server-fsxn-fp-srv" \
  --start-time $(python3 -c "import time; print(int((time.time()-60)*1000))") \
  --region ap-northeast-1 \
  --query 'events[*].message' --output text
```

期待されるログ:
```
[Handshake] Policy=fpolicy_aws | Session=...
[Event] /vol1/test-fpolicy-event.txt
[SQS] Sent: /vol1/test-fpolicy-event.txt (create)
```

### Step 5: SQS メッセージ確認

```bash
aws sqs receive-message \
  --queue-url "https://sqs.${AWS_REGION}.amazonaws.com/${AWS_ACCOUNT_ID}/fsxn-fpolicy-ingestion-<STACK_NAME>" \
  --max-number-of-messages 5 \
  --region ${AWS_REGION}
```

### Step 6: EventBridge イベント確認

EventBridge カスタムバス `fsxn-fpolicy-events` にイベントが到着していることを確認。
テスト用 CloudWatch Logs ルールを作成して確認する。
