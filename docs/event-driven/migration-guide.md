# ポーリングからイベント駆動への移行ガイド

## 概要

本ドキュメントは、既存のポーリングベース（EventBridge Scheduler）アーキテクチャから、
イベント駆動（S3 Event Notifications → EventBridge → Step Functions）アーキテクチャへの
段階的移行手順を定義する。

FSx ONTAP S3 AP ネイティブ通知機能が利用可能になった際に、
既存デプロイメントを安全に移行するためのガイドである。

---

## 移行フェーズ概要

| フェーズ | 名称 | 状態 | 目的 |
|---|---|---|---|
| Phase A | 並行稼働（Dual-Mode） | Polling + Event-Driven 両方稼働 | 検証・比較 |
| Phase B | Event-Driven Primary | Event-Driven 主系 + Polling フォールバック | 段階的切替 |
| Phase C | Event-Driven Only | Event-Driven のみ（Polling 削除） | 最終状態 |

```
Phase A: [Polling] ──────────────── [Event-Driven]
         (既存維持)                  (新規追加・検証)

Phase B: [Polling (fallback)] ───── [Event-Driven (primary)]
         (フォールバック)            (主系)

Phase C:                             [Event-Driven (only)]
                                     (Polling 完全削除)
```

---

## Phase A: 並行稼働（Dual-Mode）

### 目的
- イベント駆動パイプラインの動作検証
- ポーリングとイベント駆動の処理結果比較
- レイテンシ改善の定量測定

### 実装手順

#### 1. CloudFormation テンプレート変更

既存テンプレートに `EnableEventDriven` パラメータと Condition を追加する。

```yaml
Parameters:
  # 既存パラメータ（変更なし）
  ScheduleExpression:
    Type: String
    Default: "rate(1 hour)"
    Description: EventBridge Scheduler のスケジュール式

  # 新規追加パラメータ
  EnableEventDriven:
    Type: String
    Default: "false"
    AllowedValues: ["true", "false"]
    Description: イベント駆動モードを有効化する

Conditions:
  # 既存 Condition（変更なし）
  # ...

  # 新規追加 Condition
  CreateEventDrivenResources:
    !Equals [!Ref EnableEventDriven, "true"]
```

#### 2. EventBridge Rule リソース追加（Condition 付き）

```yaml
Resources:
  # 既存の EventBridge Scheduler（変更なし）
  ExistingSchedule:
    Type: AWS::Scheduler::Schedule
    Properties:
      # ... 既存設定維持 ...

  # 新規追加: EventBridge Rule（Condition 付き）
  S3EventRule:
    Type: AWS::Events::Rule
    Condition: CreateEventDrivenResources
    Properties:
      Name: !Sub "${AWS::StackName}-s3-event-rule"
      EventPattern:
        source:
          - aws.s3
        detail-type:
          - "Object Created"
        detail:
          bucket:
            name:
              - !Ref SourceBucket
          object:
            key:
              - prefix: "products/"
      State: ENABLED
      Targets:
        - Id: StepFunctionsTarget
          Arn: !Ref StateMachine
          RoleArn: !GetAtt EventBridgeRole.Arn
```

#### 3. 重複処理防止

並行稼働中は同一ファイルが Polling と Event-Driven の両方で処理される可能性がある。
冪等処理により重複を安全に処理する。

```python
# 冪等キー: file_key + etag
idempotency_key = f"{file_key}:{etag}"

# DynamoDB で処理済みチェック
if is_already_processed(idempotency_key):
    logger.info("Already processed: %s (idempotent skip)", idempotency_key)
    return {"status": "SKIPPED", "reason": "already_processed"}
```

### 検証基準

| 基準 | 測定方法 | 合格条件 |
|---|---|---|
| イベント配信完全性 | Polling 検出ファイル vs Event-Driven 処理ファイル | 100% 一致 |
| 処理正確性 | 出力 JSON の diff | byte-for-byte 同一 |
| レイテンシ改善 | EMF メトリクス比較 | Event-Driven < Polling |
| エラー率 | CloudWatch Errors メトリクス | Event-Driven ≤ Polling |

### ロールバック手順

```bash
# Phase A ロールバック: EventBridge Rule を無効化
aws cloudformation update-stack \
  --stack-name <stack-name> \
  --parameters ParameterKey=EnableEventDriven,ParameterValue=false

# 確認: EventBridge Rule が削除されたことを確認
aws events list-rules --name-prefix <stack-name>
```

---

## Phase B: Event-Driven Primary

### 目的
- Event-Driven を主系として運用
- Polling をフォールバック（低頻度）として維持
- 本番環境での安定性確認

### 実装手順

#### 1. Polling スケジュール頻度を低下

```yaml
Parameters:
  ScheduleExpression:
    Type: String
    Default: "rate(6 hours)"  # 1 hour → 6 hours に変更
    Description: EventBridge Scheduler のスケジュール式（フォールバック用）

  EnableEventDriven:
    Type: String
    Default: "true"  # デフォルトを true に変更
```

#### 2. Polling をキャッチアップモードに変更

Polling Lambda に「Event-Driven で処理済みのファイルをスキップ」するロジックを追加。

```python
def discovery_handler(event, context):
    """Discovery Lambda（Phase B: キャッチアップモード）"""
    # 通常のファイルスキャン
    all_files = scan_s3ap_files()

    # Event-Driven で処理済みのファイルを除外
    unprocessed_files = [
        f for f in all_files
        if not is_already_processed(f["key"], f["etag"])
    ]

    if unprocessed_files:
        logger.warning(
            "Catchup: %d files missed by event-driven, processing via polling",
            len(unprocessed_files),
        )

    return {"objects": unprocessed_files}
```

#### 3. アラート設定

```yaml
# Event-Driven 処理失敗時のアラート
EventDrivenFailureAlarm:
  Type: AWS::CloudWatch::Alarm
  Condition: CreateEventDrivenResources
  Properties:
    AlarmName: !Sub "${AWS::StackName}-event-driven-failures"
    MetricName: ExecutionsFailed
    Namespace: AWS/States
    Statistic: Sum
    Period: 300
    EvaluationPeriods: 3
    Threshold: 5
    ComparisonOperator: GreaterThanOrEqualToThreshold
    AlarmActions:
      - !Ref NotificationTopic
```

### 検証基準

| 基準 | 測定方法 | 合格条件 |
|---|---|---|
| Event-Driven カバレッジ | 処理ファイル数 / 全ファイル数 | ≥ 99.9% |
| Polling キャッチアップ | Polling で追加処理されたファイル数 | ≤ 0.1% |
| エラー率 | 連続 7 日間のエラー率 | < 0.01% |
| レイテンシ P99 | CloudWatch Percentile | < 5 秒 |

### ロールバック手順

```bash
# Phase B ロールバック: Polling を主系に戻す
aws cloudformation update-stack \
  --stack-name <stack-name> \
  --parameters \
    ParameterKey=ScheduleExpression,ParameterValue="rate(1 hour)" \
    ParameterKey=EnableEventDriven,ParameterValue=true

# 注意: EnableEventDriven=true のまま Polling 頻度を戻す
# Event-Driven は引き続き稼働（重複は冪等処理で安全）
```

---

## Phase C: Event-Driven Only

### 目的
- Polling リソースの完全削除
- コスト最適化（Scheduler + Discovery Lambda の削除）
- アーキテクチャの簡素化

### 前提条件

Phase C に移行する前に、以下の条件を全て満たすこと:

- [ ] Phase B で 30 日以上安定稼働
- [ ] Polling キャッチアップが 0 件/日を 14 日連続達成
- [ ] Event-Driven エラー率 < 0.001% を 14 日連続達成
- [ ] ステークホルダーの承認取得

### 実装手順

#### 1. Polling リソース削除

```yaml
Parameters:
  # ScheduleExpression パラメータを削除（または deprecated マーク）
  EnableEventDriven:
    Type: String
    Default: "true"
    AllowedValues: ["true"]  # false を許可しない

  # 新規追加: Polling 削除確認パラメータ
  ConfirmPollingRemoval:
    Type: String
    Default: "false"
    AllowedValues: ["true", "false"]
    Description: Polling リソースの削除を確認する（安全装置）

Conditions:
  RemovePollingResources:
    !Equals [!Ref ConfirmPollingRemoval, "true"]
  KeepPollingResources:
    !Not [!Condition RemovePollingResources]

Resources:
  # Polling リソース（Condition で制御）
  ExistingSchedule:
    Type: AWS::Scheduler::Schedule
    Condition: KeepPollingResources
    Properties:
      # ... 既存設定 ...
```

#### 2. Discovery Lambda の役割変更

Discovery Lambda を「オンデマンドスキャン」用途に変更（定期実行は停止）。

### 検証基準

| 基準 | 測定方法 | 合格条件 |
|---|---|---|
| 全ファイル処理 | 日次監査スクリプト | 未処理ファイル 0 件 |
| コスト削減 | AWS Cost Explorer | Polling 関連コスト 0 |
| エラー率 | 連続 30 日間 | < 0.001% |

### ロールバック手順

```bash
# Phase C ロールバック: Polling を復活
aws cloudformation update-stack \
  --stack-name <stack-name> \
  --parameters \
    ParameterKey=ConfirmPollingRemoval,ParameterValue=false \
    ParameterKey=EnableEventDriven,ParameterValue=true

# Polling Scheduler が再作成される
# Event-Driven も引き続き稼働（並行稼働 = Phase A 相当に戻る）
```

---

## 後方互換性要件

### 既存パラメータの互換性

| パラメータ | Phase A | Phase B | Phase C |
|---|---|---|---|
| `ScheduleExpression` | 変更なし | 値変更のみ | 削除可能 |
| `S3AccessPointAlias` | 変更なし | 変更なし | 変更なし |
| `MapConcurrency` | 変更なし | 変更なし | 変更なし |
| `LambdaMemorySize` | 変更なし | 変更なし | 変更なし |
| `EnableEventDriven` | 新規追加 | デフォルト変更 | 固定 true |

### Step Functions ワークフロー

- **変更不要**: 既存の State Machine 定義はそのまま使用
- EventBridge Rule のターゲットとして既存 State Machine を指定
- 入力形式の変換は EventBridge Input Transformer で対応

### Lambda 関数コード

- **変更不要**: 既存の Processing Lambda（ImageTagging, CatalogMetadata 等）はそのまま使用
- Event-Driven パスでは EventBridge → Step Functions → Lambda の順で呼び出し
- Lambda の入力形式は Step Functions が統一（既存と同一）

---

## CloudFormation テンプレートパターン

### 完全なテンプレートパターン（Phase A 対応）

```yaml
AWSTemplateFormatVersion: "2010-09-09"
Parameters:
  # 既存パラメータ（全て維持）
  ScheduleExpression:
    Type: String
    Default: "rate(1 hour)"

  # Phase 4 追加パラメータ
  EnableEventDriven:
    Type: String
    Default: "false"
    AllowedValues: ["true", "false"]
    Description: イベント駆動モードを有効化する

Conditions:
  CreateEventDrivenResources:
    !Equals [!Ref EnableEventDriven, "true"]

Resources:
  # === 既存リソース（変更なし） ===
  # EventBridge Scheduler, Step Functions, Lambda Functions...

  # === Phase 4 追加リソース（Condition 付き） ===
  EventBridgeRole:
    Type: AWS::IAM::Role
    Condition: CreateEventDrivenResources
    Properties:
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              Service: events.amazonaws.com
            Action: sts:AssumeRole
      Policies:
        - PolicyName: StartExecution
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: Allow
                Action: states:StartExecution
                Resource: !Ref StateMachine

  S3EventRule:
    Type: AWS::Events::Rule
    Condition: CreateEventDrivenResources
    Properties:
      EventPattern:
        source: ["aws.s3"]
        detail-type: ["Object Created"]
        detail:
          bucket:
            name: [!Ref SourceBucket]
      Targets:
        - Id: StepFunctionsTarget
          Arn: !Ref StateMachine
          RoleArn: !GetAtt EventBridgeRole.Arn
```

---

## 監視・運用

### ダッシュボード指標

| メトリクス | 名前空間 | 説明 |
|---|---|---|
| `EventToProcessingLatency` | FSxN-S3AP-Patterns | イベント発生→処理開始 |
| `EndToEndDuration` | FSxN-S3AP-Patterns | イベント発生→処理完了 |
| `EventVolumePerMinute` | FSxN-S3AP-Patterns | 1分あたりイベント数 |
| `PollingCatchupCount` | FSxN-S3AP-Patterns | Polling キャッチアップ数 |

### アラート設定

| アラート | 条件 | アクション |
|---|---|---|
| Event-Driven 失敗 | 5分間で5回以上失敗 | SNS 通知 + Polling 頻度増加検討 |
| レイテンシ異常 | P99 > 10秒 | SNS 通知 + 調査 |
| Polling キャッチアップ | 1日で10件以上 | SNS 通知 + Event-Driven 調査 |

---

## 参考資料

- [architecture-design.md](./architecture-design.md) — イベント駆動アーキテクチャ設計
- [Amazon EventBridge Rules](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-rules.html)
- [AWS Step Functions Input/Output Processing](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-input-output-filtering.html)
