# Why Native S3AP Notifications Still Matter

🌐 **Language / 言語**: [日本語](native-s3ap-notifications-evidence.md) | [English](native-s3ap-notifications-evidence.en.md)

## 概要

本ドキュメントは、FSx for ONTAP S3 Access Points に対するネイティブイベント通知機能の必要性を、FPolicy ベースの実装経験から得られた evidence に基づいて整理したものです。

> **位置づけ**: FPolicy による Event-Driven パターンは「動作する回避策」として実証済みですが、ネイティブ機能があれば解消される運用上の課題が明確に存在します。本ドキュメントはその課題を定量化し、AWS サービスチームへのフィードバックとして活用することを目的としています。

## 顧客課題（Working Backwards）

### Press Release（想定）

> 「Amazon FSx for ONTAP の S3 Access Points が Amazon EventBridge へのネイティブイベント通知をサポートしました。これにより、お客様は FPolicy サーバーの運用なしに、ファイル変更をリアルタイムで検知し、サーバーレスワークフローを起動できます。」

### Customer Problem Statement

エンタープライズのお客様は FSx for ONTAP に保存されたファイルデータに対して、変更検知 → 自動処理のパイプラインを構築したいと考えています。現在、S3 Access Points は `GetBucketNotificationConfiguration` をサポートしていないため、以下の 2 つの選択肢しかありません:

1. **ポーリング**: EventBridge Scheduler + ListObjectsV2 による定期スキャン（リアルタイム性なし）
2. **FPolicy**: ONTAP ネイティブの FPolicy External Server を自前で運用（高い運用複雑性）

どちらも「S3 バケットに EventBridge を設定するだけ」という S3 ネイティブの体験とは大きく乖離しています。

## FPolicy 実装から明らかになった運用課題

### 課題 1: 長時間稼働 TCP リスナーの運用

| 項目 | 現状（FPolicy） | ネイティブ通知があれば |
|------|----------------|---------------------|
| 常時稼働コンポーネント | ECS Fargate タスク (24/7) | なし（イベント駆動） |
| 月額コスト（リスナーのみ） | ~$30-50 | $0 |
| 障害ポイント | TCP 接続断、タスク再起動 | なし |
| スケーリング | 手動（タスク数調整） | 自動（EventBridge） |

### 課題 2: Fargate タスク IP 追跡

FPolicy External Engine は IP アドレスで FPolicy サーバーを識別します。Fargate タスクが再起動すると IP が変わるため:

- IP Updater Lambda を実装（ECS タスク状態変更イベント → ONTAP REST API で engine IP 更新）
- 更新中の 30-60 秒間はイベントが失われる可能性
- EC2 + Elastic IP で回避可能だが、Fargate のサーバーレス利点を失う

**ネイティブ通知があれば**: IP 管理は不要。EventBridge ルールを設定するだけ。

### 課題 3: ONTAP External-Engine 再設定

FPolicy サーバーの変更（IP、ポート、証明書）のたびに ONTAP REST API で external-engine を再設定する必要があります:

```bash
# 現在必要な操作（デプロイのたびに実行）
curl -k -u fsxadmin:PASSWORD \
  -X PATCH "https://<MGMT_IP>/api/protocols/fpolicy/<SVM_UUID>/engines/fpolicy_aws_engine" \
  -d '{"primary_servers": ["<NEW_TASK_IP>"]}'
```

**ネイティブ通知があれば**: ONTAP 側の設定変更は不要。

### 課題 4: FPolicy プロトコル/バージョン依存

| 制約 | 影響 |
|------|------|
| NFSv4.2 非サポート | NFSv4.2 のみの環境では FPolicy が使えない |
| XML ベースプロトコル | カスタムパーサーが必要 |
| ONTAP バージョン依存 | Persistent Store は 9.14.1+、is-mandatory は 9.15.1+ |
| SVM 単位の設定 | マルチ SVM 環境では各 SVM に個別設定が必要 |

**ネイティブ通知があれば**: プロトコル非依存。S3 API レベルでのイベント検知。

### 課題 5: イベント耐久性のセマンティクスが不明確

FPolicy のイベント配信保証:
- `is-mandatory=false`: サーバー不可時にイベントが失われる（at-most-once）
- `is-mandatory=true`: ファイル操作がブロックされる（可用性とのトレードオフ）
- Persistent Store: バッファリングするが、ボリューム容量超過時の動作が不明確

**ネイティブ通知があれば**: S3 Event Notifications と同等の at-least-once 配信保証が期待できる。

### 課題 6: クロスアカウントイベントルーティングの複雑性

現在のアーキテクチャ:
```
Account A (FSx for ONTAP + FPolicy)
  → Fargate → SQS → Bridge Lambda → EventBridge Custom Bus
    → EventBridge Rule → Cross-Account Target (Account B)
```

**ネイティブ通知があれば**:
```
Account A (FSx for ONTAP + S3 AP)
  → EventBridge (native) → Cross-Account Rule → Account B
```

### 課題 7: S3 ネイティブパターンとの統合不足

S3 バケットでは以下が「設定するだけ」で動作しますが、S3 AP for FSx for ONTAP では不可:

| S3 ネイティブ機能 | S3 バケット | S3 AP for FSx for ONTAP |
|-----------------|------------|---------------------|
| EventBridge 通知 | ✅ | ❌ |
| S3 Event Notifications (SQS/SNS/Lambda) | ✅ | ❌ |
| S3 Inventory | ✅ | ❌ |
| S3 Batch Operations | ✅ | ❌ |
| Object Lifecycle | ✅ | ❌ |

## 定量的インパクト

### 運用コスト比較（月額、中規模ワークロード）

| コンポーネント | FPolicy 方式 | ネイティブ通知（想定） |
|--------------|-------------|---------------------|
| Fargate (24/7) | $30-50 | $0 |
| IP Updater Lambda | $1-2 | $0 |
| SQS Queue | $1-5 | $0-1 (EventBridge) |
| Bridge Lambda | $1-3 | $0 |
| ONTAP 設定管理工数 | 2-4 時間/月 | 0 |
| **合計** | **$33-60 + 運用工数** | **$0-1** |

### 実装複雑性比較

| メトリクス | FPolicy 方式 | ネイティブ通知（想定） |
|-----------|-------------|---------------------|
| CloudFormation リソース数 | 15-20 | 3-5 |
| Lambda 関数数 | 2 (IP Updater + Bridge) | 0 |
| 外部依存 (ONTAP REST API) | あり | なし |
| 初期セットアップ時間 | 2-4 時間 | 10-15 分 |
| トラブルシューティング対象 | TCP接続、FPolicy設定、IP更新、SQS | EventBridge ルールのみ |

## 顧客セグメント別インパクト

| セグメント | 現在の課題 | ネイティブ通知による改善 |
|-----------|-----------|----------------------|
| **ISV / SaaS** | FPolicy 運用の専門知識が必要 | S3 互換のイベント駆動パターンをそのまま適用 |
| **エンタープライズ IT** | ONTAP 管理者と AWS 管理者の連携が必要 | AWS 側のみで完結 |
| **SI パートナー** | FPolicy の設計・構築・運用をスコープに含める必要 | 標準的な EventBridge パターンで提案可能 |
| **規制産業** | イベント耐久性の証明が困難 | S3 Event Notifications と同等の SLA |

## 推奨される機能仕様（提案）

### Option A: EventBridge 統合

```
FSx for ONTAP Volume (via S3 AP)
  → EventBridge (s3:ObjectCreated, s3:ObjectRemoved, etc.)
    → Any EventBridge Target
```

### Option B: S3 Event Notifications 互換

```
FSx for ONTAP Volume (via S3 AP)
  → S3 Event Notification Configuration
    → SQS / SNS / Lambda (直接)
```

### 望ましい特性

- at-least-once 配信保証
- S3 イベントスキーマ互換（既存の S3 イベント処理コードを再利用可能）
- クロスアカウント配信サポート
- フィルタリング（prefix, suffix）
- NFS/SMB 経由の変更も検知（S3 API 経由の変更だけでなく）

## 現在の回避策の成熟度

本リポジトリの FPolicy Event-Driven パターンは以下の成熟度に達しています:

- ✅ NFSv3 + SMB の両プロトコルで E2E 検証済み
- ✅ Persistent Store によるイベントロスゼロ設計（ONTAP 9.14.1+）
- ✅ IP 自動更新による Fargate 再起動対応
- ✅ DynamoDB による冪等性保証
- ✅ Replay Storm Protection（流量制御）
- ✅ 3 つの Deployment Profiles（PoC / Production / Compliance）

これらは「動作する回避策」として十分に機能しますが、ネイティブ機能があれば不要になる複雑性です。

## 参考リンク

- [FSx for ONTAP S3 AP Improvements Feature Requests](fsxn-s3ap-improvements.md)
- [Trigger Mode Decision Guide](../trigger-mode-decision-guide.md)
- [Deployment Profiles](../deployment-profiles.md)
- [FPolicy Event-Driven パターン](../../event-driven-fpolicy/README.md)
