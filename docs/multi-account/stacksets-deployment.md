# StackSets によるマルチアカウントデプロイガイド

> CloudFormation StackSets を使用した UC テンプレートの一括デプロイ・管理

## 概要

本ドキュメントでは、CloudFormation StackSets を使用して FSxN S3AP Serverless Patterns の UC テンプレートを複数アカウント・複数リージョンに一括デプロイする手順を説明する。

### StackSets の利点

- **一貫性**: 全アカウントで同一テンプレートバージョンを維持
- **効率性**: 手動デプロイの排除、パラメータオーバーライドによるカスタマイズ
- **ガバナンス**: ドリフト検出による設定変更の検知
- **スケーラビリティ**: 新規アカウント追加時の自動デプロイ

---

## 前提条件

### 必要なロール

1. **管理ロール**（管理アカウント）: `fsxn-s3ap-stacksets-admin-role`
2. **実行ロール**（ターゲットアカウント）: `fsxn-s3ap-stacksets-execution-role`

テンプレート: [`shared/cfn/stacksets-admin.yaml`](../../shared/cfn/stacksets-admin.yaml)

### ロールのデプロイ

```bash
# 管理アカウントで管理ロールを作成
aws cloudformation deploy \
  --template-file shared/cfn/stacksets-admin.yaml \
  --stack-name fsxn-stacksets-admin \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    AdminMode=true \
    AdministratorAccountId=123456789012

# 各ターゲットアカウントで実行ロールを作成
aws cloudformation deploy \
  --template-file shared/cfn/stacksets-admin.yaml \
  --stack-name fsxn-stacksets-execution \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    AdminMode=false \
    AdministratorAccountId=123456789012 \
    ExecutionRolePermissionLevel=restricted
```

---

## パラメータオーバーライド戦略

### アカウント固有パラメータ

以下のパラメータはアカウントごとに異なる値を設定する必要がある:

| パラメータ | 説明 | 例 |
|---|---|---|
| `VpcId` | デプロイ先 VPC ID | `vpc-abc123` |
| `SubnetIds` | Lambda 配置サブネット | `subnet-111,subnet-222` |
| `S3AccessPointArn` | S3 AP ARN | `arn:aws:s3:...:accesspoint/xxx` |
| `SecurityGroupId` | Lambda セキュリティグループ | `sg-xxx` |
| `KmsKeyArn` | 暗号化キー ARN | `arn:aws:kms:...:key/xxx` |

### 共有パラメータ

以下のパラメータは全アカウントで共通:

| パラメータ | 説明 | 例 |
|---|---|---|
| `ModelName` | SageMaker モデル名 | `point-cloud-segmentation-v2` |
| `ScheduleExpression` | 実行スケジュール | `rate(1 hour)` |
| `LogRetentionDays` | ログ保持期間 | `14` |
| `Environment` | 環境名 | `production` |
| `ProjectPrefix` | プレフィックス | `fsxn-s3ap` |

### オーバーライド設定例

```bash
aws cloudformation create-stack-instances \
  --stack-set-name fsxn-s3ap-uc09 \
  --accounts 111111111111 222222222222 \
  --regions ap-northeast-1 \
  --parameter-overrides \
    ParameterKey=VpcId,ParameterValue=vpc-abc123 \
    ParameterKey=SubnetIds,ParameterValue="subnet-111,subnet-222" \
    ParameterKey=S3AccessPointArn,ParameterValue=arn:aws:s3:ap-northeast-1:333333333333:accesspoint/shared-ap
```

---

## デプロイ手順

### 初回デプロイ

#### Step 1: テンプレートを S3 にアップロード

```bash
# テンプレートバケットにアップロード
aws s3 cp use-cases/uc09-autonomous-driving/template-deploy.yaml \
  s3://fsxn-s3ap-templates-123456789012/uc09/template-deploy.yaml
```

#### Step 2: StackSet を作成

```bash
aws cloudformation create-stack-set \
  --stack-set-name fsxn-s3ap-uc09 \
  --template-url https://s3.amazonaws.com/fsxn-s3ap-templates-123456789012/uc09/template-deploy.yaml \
  --description "FSxN S3AP UC09 - Autonomous Driving Point Cloud Processing" \
  --administration-role-arn arn:aws:iam::123456789012:role/fsxn-s3ap-stacksets-admin-role \
  --execution-role-name fsxn-s3ap-stacksets-execution-role \
  --permission-model SELF_MANAGED \
  --parameters \
    ParameterKey=Environment,ParameterValue=production \
    ParameterKey=ProjectPrefix,ParameterValue=fsxn-s3ap \
    ParameterKey=LogRetentionDays,ParameterValue=14 \
  --tags \
    Key=Phase,Value=4 \
    Key=Component,Value=stacksets \
    Key=UseCase,Value=uc09
```

#### Step 3: スタックインスタンスを作成

```bash
aws cloudformation create-stack-instances \
  --stack-set-name fsxn-s3ap-uc09 \
  --accounts 111111111111 222222222222 \
  --regions ap-northeast-1 \
  --operation-preferences \
    MaxConcurrentPercentage=50,FailureTolerancePercentage=0 \
  --parameter-overrides \
    ParameterKey=VpcId,ParameterValue=vpc-workload-a \
    ParameterKey=SubnetIds,ParameterValue="subnet-a1,subnet-a2"
```

#### Step 4: デプロイ状況の確認

```bash
# オペレーション状態を確認
aws cloudformation describe-stack-set-operation \
  --stack-set-name fsxn-s3ap-uc09 \
  --operation-id OPERATION_ID

# スタックインスタンスの状態を確認
aws cloudformation list-stack-instances \
  --stack-set-name fsxn-s3ap-uc09
```

---

### 既存デプロイの更新

#### テンプレート更新

```bash
# 1. 新しいテンプレートをアップロード
aws s3 cp use-cases/uc09-autonomous-driving/template-deploy.yaml \
  s3://fsxn-s3ap-templates-123456789012/uc09/template-deploy-v2.yaml

# 2. StackSet を更新
aws cloudformation update-stack-set \
  --stack-set-name fsxn-s3ap-uc09 \
  --template-url https://s3.amazonaws.com/fsxn-s3ap-templates-123456789012/uc09/template-deploy-v2.yaml \
  --operation-preferences \
    MaxConcurrentPercentage=25,FailureTolerancePercentage=0,RegionConcurrencyType=SEQUENTIAL
```

#### パラメータのみ更新

```bash
aws cloudformation update-stack-instances \
  --stack-set-name fsxn-s3ap-uc09 \
  --accounts 111111111111 \
  --regions ap-northeast-1 \
  --parameter-overrides \
    ParameterKey=ScheduleExpression,ParameterValue="rate(30 minutes)"
```

---

### ロールバック手順

#### 自動ロールバック

StackSets はデフォルトで失敗時に自動ロールバックを実行する。`FailureTolerancePercentage=0` を設定すると、最初の失敗で全体が停止する。

#### 手動ロールバック

```bash
# 1. 前バージョンのテンプレートで StackSet を更新
aws cloudformation update-stack-set \
  --stack-set-name fsxn-s3ap-uc09 \
  --template-url https://s3.amazonaws.com/fsxn-s3ap-templates-123456789012/uc09/template-deploy-v1.yaml \
  --operation-preferences \
    MaxConcurrentPercentage=100,FailureTolerancePercentage=0

# 2. 特定アカウントのみロールバック
aws cloudformation update-stack-instances \
  --stack-set-name fsxn-s3ap-uc09 \
  --accounts 111111111111 \
  --regions ap-northeast-1 \
  --parameter-overrides \
    ParameterKey=ModelName,UsePreviousValue=true
```

#### 緊急時: スタックインスタンスの削除

```bash
# 特定アカウントのスタックインスタンスを削除（リソースも削除）
aws cloudformation delete-stack-instances \
  --stack-set-name fsxn-s3ap-uc09 \
  --accounts 111111111111 \
  --regions ap-northeast-1 \
  --no-retain-stacks
```

---

## ドリフト検出・修復

### 自動ドリフト検出

テンプレートで `EnableDriftDetection=true` を設定すると、24 時間ごとに自動でドリフト検出が実行される。

### 手動ドリフト検出

```bash
# StackSet 全体のドリフト検出
aws cloudformation detect-stack-set-drift \
  --stack-set-name fsxn-s3ap-uc09 \
  --operation-preferences \
    MaxConcurrentPercentage=100,FailureTolerancePercentage=100

# 結果の確認
aws cloudformation describe-stack-set-operation \
  --stack-set-name fsxn-s3ap-uc09 \
  --operation-id OPERATION_ID
```

### ドリフト修復

```bash
# ドリフトが検出された場合、StackSet を再デプロイして修復
aws cloudformation update-stack-set \
  --stack-set-name fsxn-s3ap-uc09 \
  --use-previous-template \
  --operation-preferences \
    MaxConcurrentPercentage=25,FailureTolerancePercentage=0
```

### ドリフト検出結果の解釈

| ステータス | 意味 | アクション |
|---|---|---|
| `IN_SYNC` | テンプレートと一致 | なし |
| `DRIFTED` | 手動変更あり | 修復または承認 |
| `NOT_CHECKED` | 未検出 | ドリフト検出を実行 |

---

## StackSets 互換性チェックリスト

既存 UC テンプレートを StackSets でデプロイする前に、以下を確認する:

### 必須チェック項目

- [ ] **ハードコード Account ID なし**: `!Ref AWS::AccountId` を使用
- [ ] **ハードコード Region なし**: `!Ref AWS::Region` を使用
- [ ] **VPC/Subnet パラメータ化**: パラメータとして外部から指定可能
- [ ] **リソース名の一意性**: `!Sub` でスタック名やアカウント ID を含める
- [ ] **S3 バケット名の一意性**: グローバルに一意な名前を生成
- [ ] **KMS キーのパラメータ化**: キー ARN をパラメータとして受け取る
- [ ] **IAM ロール名の一意性**: プレフィックス + アカウント情報を含める
- [ ] **Export 名の一意性**: スタック名を含めて衝突を防止

### 推奨チェック項目

- [ ] **Conditions の活用**: オプション機能は Condition で制御
- [ ] **デフォルト値の設定**: 全パラメータにデフォルト値を設定
- [ ] **タグの統一**: Phase, Component, UseCase, Account タグを付与
- [ ] **ログ保持期間の設定**: CloudWatch Log Group に RetentionInDays を設定
- [ ] **暗号化の有効化**: DynamoDB, S3, SNS に KMS 暗号化を設定

### テンプレート検証コマンド

```bash
# cfn-lint でテンプレートを検証
cfn-lint use-cases/uc09-autonomous-driving/template-deploy.yaml

# ハードコード Account ID の検出
grep -rn "[0-9]\{12\}" use-cases/*/template-deploy.yaml | grep -v "Ref\|Sub\|#"

# StackSets 互換性テスト（dry-run）
aws cloudformation validate-template \
  --template-url https://s3.amazonaws.com/BUCKET/template.yaml
```

---

## 運用ベストプラクティス

### デプロイ戦略

1. **段階的デプロイ**: 開発 → ステージング → 本番の順にデプロイ
2. **カナリアデプロイ**: 1 アカウントで検証後、残りに展開
3. **リージョン順序**: プライマリリージョン → セカンダリリージョンの順

### 障害対応

1. **FailureTolerancePercentage=0**: 最初の失敗で停止（本番推奨）
2. **MaxConcurrentPercentage=25**: 同時デプロイを制限
3. **RegionConcurrencyType=SEQUENTIAL**: リージョン間は順次実行

### 監視

- CloudTrail で StackSets API コールを監視
- EventBridge で StackSet 操作完了イベントを検知
- ドリフト検出結果を定期的に確認

---

## 関連ドキュメント

- [Cross-Account S3 AP アクセスパターン](./cross-account-s3ap.md)
- [Cross-Account IAM ロール設計](./cross-account-iam.md)
- [AWS RAM リソース共有](./ram-sharing.md)
- [Shared Services アーキテクチャ](./shared-services-architecture.md)
