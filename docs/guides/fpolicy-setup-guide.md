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

## 関連ドキュメント

- [イベント駆動アーキテクチャ設計](../event-driven/architecture-design.md)
- [移行ガイド](../event-driven/migration-guide.md)
- [ONTAP FPolicy ドキュメント](https://docs.netapp.com/us-en/ontap/nas-audit/fpolicy-config-types-concept.html)
- [FSx for ONTAP FPolicy](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/file-access-auditing.html)
