# TriggerMode Rollout / Rollback ガイド

## 概要

`TriggerMode` パラメータは、UC テンプレートのイベント駆動採用における**運用制御**です。段階的なロールアウトとロールバックを CloudFormation パラメータ変更のみで実現します。

## 推奨ロールアウト手順

```
POLLING (default) → HYBRID (移行安全モード) → EVENT_DRIVEN (完全イベント駆動)
```

### Step 1: POLLING（全 UC、初期状態）

- 既存の EventBridge Scheduler + Discovery Lambda が動作
- FPolicy パイプラインは稼働しているが、UC には接続されていない
- **リスク**: なし（既存動作と同一）

### Step 2: FPolicy パイプライン検証

- `aws events put-events` でテストイベントをカスタムバスに送信
- CloudWatch Logs でルーティングを確認
- 実際のファイル操作で FPolicy → SQS → EventBridge の E2E を確認

### Step 3: 低リスク UC を HYBRID に切り替え

```bash
aws cloudformation deploy \
  --template-file {uc}/template.yaml \
  --stack-name {stack-name} \
  --parameter-overrides TriggerMode=HYBRID \
  --capabilities CAPABILITY_NAMED_IAM
```

**監視項目**:
- Idempotency Store の重複排除率（DynamoDB `ConditionalCheckFailedException`）
- Step Functions 成功率
- SQS バックログ（`ApproximateAgeOfOldestMessage`）

**HYBRID 安定性基準**:
- 1 週間以上のエラーフリー稼働
- 重複排除率が安定（急増しない）
- Step Functions 成功率 > 99%

### Step 4: レイテンシ重視 UC を EVENT_DRIVEN に切り替え

```bash
aws cloudformation deploy \
  --template-file {uc}/template.yaml \
  --stack-name {stack-name} \
  --parameter-overrides TriggerMode=EVENT_DRIVEN \
  --capabilities CAPABILITY_NAMED_IAM
```

**結果**:
- EventBridge Scheduler + SchedulerRole が削除される
- FPolicy EventBridge Rule のみが UC をトリガー

### Step 5: コンプライアンス UC は HYBRID を維持

Persistent Store replay の E2E 検証が完了するまで、コンプライアンス系 UC は HYBRID を維持する。

## ロールバック手順

```
EVENT_DRIVEN → HYBRID → POLLING
```

**重要**: EVENT_DRIVEN から直接 POLLING に戻さない。HYBRID を経由することで、ロールバック中もイベント駆動パスが維持され、データロスリスクを最小化する。

### ロールバック判定基準

以下のいずれかに該当する場合、ロールバックを実施:

- Step Functions 失敗率 > 5%
- SQS `ApproximateAgeOfOldestMessage` > 600 秒
- FPolicy Server が 5 分以上 ONTAP から切断
- Idempotency Store の重複率が急増（通常の 3 倍以上）

### ロールバック実行

```bash
# EVENT_DRIVEN → HYBRID
aws cloudformation deploy \
  --template-file {uc}/template.yaml \
  --stack-name {stack-name} \
  --parameter-overrides TriggerMode=HYBRID \
  --capabilities CAPABILITY_NAMED_IAM

# HYBRID → POLLING（完全ロールバック）
aws cloudformation deploy \
  --template-file {uc}/template.yaml \
  --stack-name {stack-name} \
  --parameter-overrides TriggerMode=POLLING \
  --capabilities CAPABILITY_NAMED_IAM
```

### ロールバック完了確認

パラメータ変更だけではロールバック完了ではない。以下を全て確認すること:

1. `aws cloudformation wait stack-update-complete` でスタック更新完了を待つ
2. EventBridge Scheduler / Rule の状態を確認（期待通りに作成/削除されているか）
3. SQS バックログが増加していないか確認
4. Step Functions の実行が正常に開始されているか確認
5. FPolicy Server のログで ONTAP 接続が維持されているか確認

## UC 分類と推奨モード

| カテゴリ | UC 例 | 推奨初期モード | EVENT_DRIVEN 移行条件 |
|---------|-------|-------------|---------------------|
| バッチ処理 | genomics, energy-seismic | POLLING | 高頻度ファイル生成時 |
| リアルタイム | media-vfx, retail-catalog | EVENT_DRIVEN | routing 検証後 |
| コンプライアンス | legal-compliance, government-archives | HYBRID | replay E2E 検証後 |
| 大容量ファイル | autonomous-driving, semiconductor-eda | HYBRID + file readiness | size-stability check 実装後 |

## CloudFormation 動作

| TriggerMode 変更 | Scheduler | SchedulerRole | FPolicy Rule | FPolicyEventRuleRole |
|-----------------|-----------|---------------|-------------|---------------------|
| POLLING → HYBRID | 維持 | 維持 | **作成** | **作成** |
| HYBRID → EVENT_DRIVEN | **削除** | **削除** | 維持 | 維持 |
| EVENT_DRIVEN → HYBRID | **作成** | **作成** | 維持 | 維持 |
| HYBRID → POLLING | 維持 | 維持 | **削除** | **削除** |


## MSP / マルチテナント命名ガイダンス

MSP や複数顧客環境では、共有リソース名にテナント識別子を含めてクロステナント衝突を防止する。

### 推奨パラメータ

| パラメータ | 用途 | 例 |
|-----------|------|-----|
| `CustomerId` | 顧客識別子 | `acme`, `globex` |
| `EnvironmentName` | 環境名 | `prod`, `staging`, `dev` |
| `Region` | デプロイリージョン | `apne1`, `use1` |

### 命名規則

```
{customer}-{env}-fsxn-fpolicy-events          # EventBridge Bus
{customer}-{env}-s3ap-idempotency-store       # DynamoDB Table
{customer}-{env}-shared-observability         # OAM Sink Stack
{customer}-{env}-{uc}-workflow                # Step Functions
```

### CloudFormation パラメータ化例

```yaml
Parameters:
  CustomerId:
    Type: String
    Description: 顧客識別子（MSP 環境用）
    Default: "default"

Resources:
  IdempotencyTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: !Sub "${CustomerId}-${Environment}-s3ap-idempotency-store"
```

### 注意事項

- 固定名（`fsxn-s3ap-idempotency-store` 等）は単一テナント環境向け
- マルチテナント環境では必ず `CustomerId` プレフィックスを付与
- EventBridge Bus 名も顧客別に分離することで、ルーティングの独立性を確保
- OAM Sink は共有サービスアカウントに 1 つ、各顧客アカウントから Link で接続


## TriggerMode Governance

### 変更管理

TriggerMode の変更は運用制御として扱い、以下のプロセスで管理する:

1. **変更申請**: TriggerMode 変更の理由、対象 UC、期待される効果を記載
2. **事前検証**: routing テスト結果、idempotency 検証、アラーム準備状況を確認
3. **承認**: rollback owner を指定し、変更ウィンドウを設定
4. **実行**: CloudFormation stack update
5. **事後確認**: ロールバック完了確認チェックリストを実施
6. **記録**: 変更履歴を Change Manager / GitOps PR / deployment pipeline logs に記録

### 変更追跡

CloudFormation stack events だけでなく、以下でも TriggerMode 変更を追跡可能にする:

- **GitOps**: パラメータファイル (`params/{uc}-{env}.json`) を Git 管理
- **AWS Change Manager**: 変更テンプレートに TriggerMode 変更を定義
- **CI/CD Pipeline**: デプロイパイプラインのログに TriggerMode 値を記録
- **CloudWatch Metrics**: カスタムメトリクスで各 UC の現在の TriggerMode を可視化

### 責任分界

| 役割 | 責任 |
|------|------|
| UC Owner | TriggerMode 変更の申請、ビジネス要件の定義 |
| Platform Team | 変更の技術レビュー、routing 検証 |
| SRE | アラーム準備確認、rollback 実行 |
| Security | ontap_api guardrails の維持、audit log 確認 |


## TriggerMode Change Approval Matrix

| 変更 | 必要なエビデンス | 承認者 |
|------|----------------|--------|
| POLLING → HYBRID | routing テスト結果, idempotency 検証 | Platform Team + UC Owner |
| HYBRID → EVENT_DRIVEN | alarm readiness, SFN success rate, SQS backlog 安定 | Platform Team + SRE |
| EVENT_DRIVEN → HYBRID (rollback) | インシデント or rollback request | SRE (即時実行可) |
| HYBRID → POLLING (full rollback) | 持続的な routing/event 障害 | Platform Team + SRE |

## MSP RACI Matrix

マルチテナント環境での責任分界:

| Activity | Customer | MSP | AWS Partner SA |
|----------|----------|-----|----------------|
| AWS Account provisioning | A | R | C |
| OAM Sink setup | C | R | C |
| ONTAP credential rotation | A/R | C | - |
| Alarm response (first) | C | R | - |
| TriggerMode change approval | A | R | C |
| FR-2 migration decision | A/R | C | C |
| Replay storm test | C | R | - |
| UC template customization | A | R | C |

**凡例**: R = Responsible, A = Accountable, C = Consulted, I = Informed
