# FR-2 移行パス設計: FPolicy → S3AP ネイティブ通知

## 概要

Amazon FSx for NetApp ONTAP の S3 Access Points が将来的にネイティブイベント通知（S3 Event Notifications 相当）をサポートした場合の、FPolicy からの段階的移行パスを設計する。

## 前提条件

- **FR-2 (Feature Request)**: S3AP ネイティブ通知は AWS ロードマップ上の機能リクエスト
- **現在の状態**: FPolicy + ECS Fargate による TCP ベースのイベント検知が稼働中
- **TriggerMode**: 全 17 UC テンプレートで POLLING / EVENT_DRIVEN / HYBRID を切り替え可能

## 移行フェーズ

### Phase A: 並行稼働（HYBRID モード）

**目的**: S3AP 通知の安定性を確認しながら、FPolicy を維持する

```
┌─────────────────────────────────────────────────────────────────┐
│                    HYBRID Mode (Phase A)                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  FSx ONTAP ──→ FPolicy Server ──→ SQS ──→ Bridge Lambda ──┐   │
│       │                                                     │   │
│       └──→ S3AP Native Notification ──→ EventBridge ──────┐│   │
│                                                            ││   │
│                                    Idempotency Store ←─────┘│   │
│                                         │                    │   │
│                                         ▼                    │   │
│                              UC Step Functions ←─────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**手順**:
1. S3AP ネイティブ通知を有効化（EventBridge バスに送信）
2. `TriggerMode=HYBRID` に設定（CloudFormation スタック更新）
3. Idempotency Store で FPolicy / S3AP 通知の重複を排除
4. 両パスからのイベント到達率を監視（CloudWatch メトリクス）
5. 最低 2 週間の並行稼働で安定性を確認

**CloudFormation 変更**:
```yaml
Parameters:
  TriggerMode:
    Default: "HYBRID"  # POLLING → HYBRID に変更
```

**監視項目**:
- FPolicy イベント数 vs S3AP 通知数の比較
- Idempotency Store の重複排除率
- イベント到達レイテンシ（FPolicy vs S3AP）
- エラー率の比較

### Phase B: FPolicy 無効化

**目的**: S3AP 通知の安定性確認後、FPolicy を停止する

**前提条件（Phase A → B 移行判定基準）**:
- S3AP 通知のイベント到達率 ≥ 99.9%
- S3AP 通知のレイテンシ ≤ FPolicy レイテンシ × 1.5
- 2 週間以上のエラーフリー稼働
- 全 UC で S3AP 通知経由の処理が正常完了

**手順**:
1. `TriggerMode=EVENT_DRIVEN` に変更（CloudFormation スタック更新）
2. FPolicy ポリシーを無効化（ONTAP CLI）
3. ECS Fargate タスクを停止（desired count = 0）
4. 1 週間の監視期間（ロールバック可能な状態を維持）

**CloudFormation 変更**:
```yaml
Parameters:
  TriggerMode:
    Default: "EVENT_DRIVEN"  # HYBRID → EVENT_DRIVEN に変更
```

**ONTAP 側**:
```bash
# FPolicy ポリシーを無効化（ONTAP 9.11+ 推奨形式）
fpolicy disable -vserver FSxN_OnPre -policy-name fpolicy_aws
```

**ロールバック手順**:
```bash
# 問題発生時: FPolicy を再有効化 + TriggerMode=HYBRID に戻す
fpolicy enable -vserver FSxN_OnPre -policy-name fpolicy_aws -sequence-number 1
# CloudFormation: TriggerMode=HYBRID にスタック更新
```

### Phase C: FPolicy リソースクリーンアップ

**目的**: 不要になった FPolicy 関連リソースを削除する

**前提条件（Phase B → C 移行判定基準）**:
- Phase B 開始から 30 日以上経過
- ロールバック不要の最終判断

**削除対象リソース**:
1. ECS Fargate タスク定義 + サービス
2. SQS Ingestion Queue
3. Bridge Lambda
4. IP Updater Lambda + EventBridge Rule
5. ECR リポジトリ（FPolicy Server イメージ）
6. ONTAP FPolicy ポリシー + エンジン + イベント定義
7. Persistent Store ボリューム（使用時）
8. `event-driven-fpolicy/` CloudFormation スタック

**保持するリソース**:
- EventBridge カスタムバス `fsxn-fpolicy-events`（S3AP 通知の送信先として再利用）
- UC 別 EventBridge Rules（ソースが `fsxn.fpolicy` → `fsxn.s3ap` に変更）
- Idempotency Store（HYBRID → EVENT_DRIVEN 移行で不要になるが、監査ログとして保持可能）

## イベントスキーマ互換性分析

### FPolicy イベント（現在）

```json
{
  "source": "fsxn.fpolicy",
  "detail-type": "FPolicy File Operation",
  "detail": {
    "event_id": "uuid",
    "operation_type": "create",
    "file_path": "/vol1/legal/contract.pdf",
    "volume_name": "vol1",
    "svm_name": "FSxN_OnPre",
    "timestamp": "2026-05-14T10:30:00Z",
    "file_size": 0,
    "client_ip": "10.0.1.100",
    "user_name": "DOMAIN\\user01",
    "protocol": "smb"
  }
}
```

### S3AP ネイティブ通知（想定）

```json
{
  "source": "aws.s3",
  "detail-type": "Object Created",
  "detail": {
    "bucket": {
      "name": "access-point-alias-ext-s3alias"
    },
    "object": {
      "key": "legal/contract.pdf",
      "size": 1048576,
      "etag": "abc123"
    },
    "request-id": "...",
    "source-ip-address": "10.0.1.100"
  }
}
```

### スキーマ変換マッピング

| FPolicy フィールド | S3AP 通知フィールド | 変換ロジック |
|---|---|---|
| `operation_type` | `detail-type` | `Object Created` → `create`, `Object Deleted` → `delete` |
| `file_path` | `detail.object.key` | S3 キー形式（ボリュームプレフィックスなし） |
| `volume_name` | N/A | S3AP alias から推定可能 |
| `svm_name` | N/A | S3AP 設定から推定可能 |
| `file_size` | `detail.object.size` | 直接マッピング |
| `client_ip` | `detail.source-ip-address` | 直接マッピング |
| `user_name` | N/A | S3AP 通知には含まれない可能性 |
| `protocol` | N/A | S3AP 経由のため常に "s3" |

### 互換性の課題

1. **user_name の欠落**: S3AP 通知には NTFS ユーザー情報が含まれない可能性がある。Permission-aware RAG など、ユーザー情報が必要な UC では FPolicy を維持する必要がある。

2. **operation_type の粒度**: S3 イベントは `ObjectCreated` / `ObjectRemoved` の 2 種類。FPolicy の `rename` / `setattr` に相当するイベントがない可能性がある。

3. **リアルタイム性**: S3AP 通知のレイテンシは S3 Event Notifications と同等（数秒）。FPolicy は TCP 接続で即座に通知されるため、レイテンシ要件が厳しい UC では FPolicy が優位。

4. **EventBridge Rule の変更**: `source` フィールドが `fsxn.fpolicy` → `aws.s3` に変わるため、全 UC の EventBridge Rule を更新する必要がある。

## TriggerMode パラメータによる切り替え

移行は `TriggerMode` パラメータの変更のみで実現可能:

```
Phase A: TriggerMode = HYBRID
  → EventBridge Scheduler: 有効
  → FPolicy EventBridge Rule: 有効
  → S3AP EventBridge Rule: 有効（新規追加）
  → Idempotency Store: 重複排除

Phase B: TriggerMode = EVENT_DRIVEN
  → EventBridge Scheduler: 無効
  → FPolicy EventBridge Rule: 無効（FPolicy 停止後）
  → S3AP EventBridge Rule: 有効
  → Idempotency Store: 不要

Phase C: TriggerMode = EVENT_DRIVEN (リソース削除後)
  → S3AP EventBridge Rule のみ有効
```

## リスクと緩和策

| リスク | 影響 | 緩和策 |
|--------|------|--------|
| S3AP 通知の遅延 | UC 処理の遅延 | Phase A で FPolicy との並行稼働で検証 |
| user_name 情報の欠落 | Permission-aware 機能の劣化 | FPolicy を維持する UC を特定 |
| S3AP 通知の信頼性 | イベントロス | Idempotency Store + DLQ で検知 |
| ロールバック失敗 | サービス停止 | Phase B で FPolicy リソースを 30 日間保持 |

## タイムライン（想定）

| 時期 | マイルストーン |
|------|--------------|
| FR-2 GA | S3AP ネイティブ通知の一般提供開始 |
| GA + 2 週間 | Phase A 開始（HYBRID モード） |
| GA + 1 ヶ月 | Phase A 完了判定 |
| GA + 1.5 ヶ月 | Phase B 開始（FPolicy 無効化） |
| GA + 2.5 ヶ月 | Phase B 完了判定 |
| GA + 3 ヶ月 | Phase C（クリーンアップ） |

## 参考

- [Amazon S3 Event Notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventNotifications.html)
- [FSx for ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html)
- [EventBridge Content Filtering](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-patterns-content-based-filtering.html)
