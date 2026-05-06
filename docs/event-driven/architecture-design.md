# イベント駆動アーキテクチャ設計ドキュメント

## 概要

本ドキュメントは、FSx for NetApp ONTAP S3 Access Points（以下 FSx ONTAP S3 AP）における
イベント駆動アーキテクチャの設計を定義する。現在のポーリングベースアーキテクチャから、
将来の FSx ONTAP S3 AP ネイティブ通知機能を活用したイベント駆動アーキテクチャへの
移行を見据えた設計である。

## ターゲットアーキテクチャ

### 最終目標状態

```
FSx ONTAP S3 AP (ファイル操作)
  → S3 Event Notification (ネイティブ通知)
    → Amazon EventBridge (ルールベースフィルタリング)
      → AWS Step Functions (ワークフロー実行)
        → Processing Lambdas (UC11 互換処理)
```

### アーキテクチャ構成要素

| コンポーネント | 役割 | 備考 |
|---|---|---|
| FSx ONTAP S3 AP | イベントソース | ファイル操作（Put, Delete）をトリガー |
| S3 Event Notification | イベント発行 | 標準 S3 イベント通知形式 |
| Amazon EventBridge | イベントルーティング | パターンマッチングによるフィルタリング |
| AWS Step Functions | ワークフロー実行 | 既存 UC パイプラインを再利用 |
| Lambda Functions | 処理実行 | UC11 互換の画像タグ付け・メタデータ生成 |

---

## イベントスキーマ定義

FSx ONTAP S3 AP ネイティブ通知は、標準 S3 Event Notification 形式に準拠する。

### S3 Event Notification スキーマ

```json
{
  "version": "0",
  "id": "event-id-uuid",
  "detail-type": "Object Created",
  "source": "aws.s3",
  "account": "123456789012",
  "time": "2024-01-15T10:30:00Z",
  "region": "ap-northeast-1",
  "resources": [
    "arn:aws:s3:::bucket-name"
  ],
  "detail": {
    "version": "0",
    "bucket": {
      "name": "fsxn-s3ap-bucket-alias"
    },
    "object": {
      "key": "products/SKU12345_front.jpg",
      "size": 2097152,
      "etag": "d41d8cd98f00b204e9800998ecf8427e",
      "sequencer": "0055AED6DCD90281E5"
    },
    "request-id": "request-id-value",
    "requester": "123456789012",
    "source-ip-address": "10.0.1.100",
    "reason": "PutObject"
  }
}
```

### イベントフィールド定義

| フィールド | 型 | 説明 |
|---|---|---|
| `source` | String | イベントソース（`aws.s3`） |
| `detail-type` | String | イベントタイプ（`Object Created`, `Object Removed`） |
| `detail.bucket.name` | String | S3 AP バケット名/エイリアス |
| `detail.object.key` | String | オブジェクトキー（ファイルパス） |
| `detail.object.size` | Number | ファイルサイズ（バイト） |
| `detail.object.etag` | String | ETag（MD5 ハッシュ） |
| `time` | String | イベント発生タイムスタンプ（ISO 8601） |
| `detail.reason` | String | 操作種別（`PutObject`, `CompleteMultipartUpload`, `DeleteObject`） |

### サポートするイベントタイプ

| イベントタイプ | detail-type | reason |
|---|---|---|
| オブジェクト作成（Put） | `Object Created` | `PutObject` |
| オブジェクト作成（マルチパート） | `Object Created` | `CompleteMultipartUpload` |
| オブジェクト削除 | `Object Removed` | `DeleteObject` |
| オブジェクト削除（マーカー） | `Object Removed` | `DeleteMarkerCreated` |

---

## アーキテクチャ比較

### 3 アーキテクチャ概要

| 項目 | Polling（現行） | Kinesis Hybrid（Phase 3） | Event-Driven（ターゲット） |
|---|---|---|---|
| トリガー方式 | EventBridge Scheduler | Kinesis Data Stream + Scheduler | S3 Event Notification |
| 検出メカニズム | 定期スキャン（ONTAP API） | ストリーム消費 + 定期スキャン | ネイティブ通知 |
| レイテンシ | 分単位（スケジュール間隔依存） | 秒単位（ストリーム遅延） | サブ秒（イベント発火即時） |
| スケーラビリティ | スキャン対象ファイル数に比例 | シャード数で制御 | イベント数に自動スケール |
| コスト構造 | Lambda 実行 + ONTAP API 呼び出し | Kinesis シャード時間 + Lambda | EventBridge イベント + Lambda |
| 複雑性 | 低（シンプルなスケジューラ） | 中（ストリーム管理が必要） | 低（マネージドサービス） |
| 信頼性 | 高（冪等スキャン） | 高（at-least-once 配信） | 高（at-least-once + 冪等処理） |

### Architecture 1: Polling（現行 — EventBridge Scheduler）

```
EventBridge Scheduler (rate/cron)
  → Step Functions (StartExecution)
    → Discovery Lambda (ONTAP API scan)
      → Processing Lambdas (Map state)
```

**特徴:**
- シンプルで信頼性が高い
- ONTAP API を直接呼び出してファイル一覧を取得
- スケジュール間隔がレイテンシの下限を決定
- ファイル数増加に伴いスキャン時間が増加

**適用シナリオ:**
- バッチ処理（日次/時次）
- レイテンシ要件が緩い（分単位で許容）
- ファイル数が少ない（〜1000 ファイル/スキャン）

### Architecture 2: Kinesis Hybrid（Phase 3 — Polling + Streaming）

```
EventBridge Scheduler → Discovery Lambda → Kinesis Data Stream
                                                    ↓
                                          Stream Consumer Lambda
                                                    ↓
                                          Step Functions (per-file)
```

**特徴:**
- ポーリングで検出 → Kinesis でバッファリング → 個別処理
- ストリーム消費により処理の並列度を制御
- バックプレッシャー対応（シャード分割）
- ポーリング間隔 + ストリーム遅延がレイテンシ

**適用シナリオ:**
- 高スループット処理（1000+ ファイル/時間）
- 処理順序の保証が必要
- バックプレッシャー制御が必要

### Architecture 3: Event-Driven（ターゲット — Native Notifications）

```
FSx ONTAP S3 AP (PutObject)
  → S3 Event Notification
    → EventBridge Rule (pattern filter)
      → Step Functions (StartExecution)
        → Processing Lambdas
```

**特徴:**
- ファイル操作と同時にイベント発火（サブ秒レイテンシ）
- EventBridge ルールによる高度なフィルタリング
- スキャン不要（イベント駆動で個別ファイル処理）
- マネージドサービスによる自動スケーリング

**適用シナリオ:**
- リアルタイム処理（サブ秒レイテンシ要件）
- 大量ファイル（10000+ ファイル/時間）
- 選択的処理（特定パターンのみ処理）

---

## レイテンシ分析

### エンドツーエンドレイテンシ比較

| フェーズ | Polling | Kinesis Hybrid | Event-Driven |
|---|---|---|---|
| イベント検出 | 0〜60 分（スケジュール間隔） | 0〜60 分（スキャン間隔） | < 100 ms（即時通知） |
| イベント配信 | N/A | 200〜500 ms（Kinesis） | < 50 ms（EventBridge） |
| ワークフロー開始 | < 1 秒（Step Functions） | < 1 秒（Step Functions） | < 1 秒（Step Functions） |
| 処理実行 | 処理内容依存 | 処理内容依存 | 処理内容依存 |
| **合計（検出〜処理開始）** | **分単位** | **秒単位** | **サブ秒** |

### レイテンシ内訳

#### Polling パス
```
ファイル作成 → [待機: 0〜3600秒] → Scheduler 起動 → Discovery スキャン (5〜30秒)
  → ファイル検出 → Step Functions 開始 (< 1秒) → 処理開始
合計: 数秒〜60分（平均: スケジュール間隔の半分）
```

#### Kinesis Hybrid パス
```
ファイル作成 → [待機: 0〜3600秒] → Scheduler 起動 → Discovery スキャン (5〜30秒)
  → Kinesis Put (< 100ms) → Consumer 取得 (200〜500ms) → 処理開始
合計: 数秒〜60分（検出後は秒単位）
```

#### Event-Driven パス
```
ファイル作成 → S3 Event Notification (< 100ms) → EventBridge ルール評価 (< 50ms)
  → Step Functions 開始 (< 1秒) → 処理開始
合計: < 2秒（典型的には 500ms 以下）
```

### レイテンシ改善率

| 比較 | 改善率 |
|---|---|
| Polling → Event-Driven | 99%+ 削減（分 → サブ秒） |
| Kinesis Hybrid → Event-Driven | 90%+ 削減（秒 → サブ秒） |

---

## EventBridge ルールパターン

### 基本ルールパターン

#### 1. ファイルプレフィックスフィルタ

特定ディレクトリ配下のファイルのみ処理する。

```json
{
  "source": ["aws.s3"],
  "detail-type": ["Object Created"],
  "detail": {
    "object": {
      "key": [{"prefix": "products/"}]
    }
  }
}
```

#### 2. ファイルサフィックスフィルタ

特定拡張子のファイルのみ処理する。

```json
{
  "source": ["aws.s3"],
  "detail-type": ["Object Created"],
  "detail": {
    "object": {
      "key": [{"suffix": ".jpg"}, {"suffix": ".png"}]
    }
  }
}
```

#### 3. イベントタイプフィルタ

特定の操作種別のみ処理する。

```json
{
  "source": ["aws.s3"],
  "detail-type": ["Object Created"],
  "detail": {
    "reason": ["PutObject", "CompleteMultipartUpload"]
  }
}
```

#### 4. ソースボリュームフィルタ

特定の S3 AP バケット（= FSx ONTAP ボリューム）のみ処理する。

```json
{
  "source": ["aws.s3"],
  "detail-type": ["Object Created"],
  "detail": {
    "bucket": {
      "name": ["fsxn-retail-catalog-s3ap"]
    }
  }
}
```

### 複合ルールパターン（UC11 Retail Catalog 向け）

```json
{
  "source": ["aws.s3"],
  "detail-type": ["Object Created"],
  "detail": {
    "bucket": {
      "name": ["fsxn-retail-catalog-s3ap"]
    },
    "object": {
      "key": [{"prefix": "products/"}]
    },
    "reason": ["PutObject", "CompleteMultipartUpload"]
  }
}
```

### ルールパターン設計指針

| フィルタ種別 | ユースケース | 例 |
|---|---|---|
| prefix | ディレクトリベースの処理分離 | `products/`, `raw/`, `incoming/` |
| suffix | ファイルタイプベースの処理分岐 | `.jpg`, `.png`, `.dicom`, `.pdf` |
| event type | 操作種別による処理制御 | 作成のみ処理、削除は無視 |
| source volume | マルチボリューム環境での分離 | ボリューム別に異なるパイプライン |

---

## セキュリティ考慮事項

### イベントソース検証

EventBridge ルールでソース ARN を検証し、不正なイベント注入を防止する。

```json
{
  "source": ["aws.s3"],
  "resources": [
    {"prefix": "arn:aws:s3:::expected-bucket-name"}
  ]
}
```

### 冪等処理

イベント駆動アーキテクチャでは at-least-once 配信が前提となるため、
処理の冪等性を保証する設計が必要。

- **冪等キー**: `object.key` + `object.etag` の組み合わせ
- **重複検出**: DynamoDB による処理済みイベント記録
- **出力の冪等性**: 同一入力に対して同一出力を保証

### IAM 最小権限

- EventBridge ルール: 特定の Step Functions のみ StartExecution 許可
- Step Functions: 特定の Lambda 関数のみ InvokeFunction 許可
- Lambda: 必要最小限の S3/Rekognition/Bedrock 権限

---

## 将来の拡張

### FSx ONTAP S3 AP ネイティブ通知対応時の変更点

1. **イベントソース変更**: S3 Bucket → FSx ONTAP S3 AP
2. **EventBridge ルール更新**: `source` フィールドの変更（`aws.s3` → `aws.fsx` の可能性）
3. **バケット名変更**: S3 AP エイリアスへの更新
4. **テンプレート更新**: S3 Bucket リソース → FSx ONTAP S3 AP 参照

### 段階的移行パス

Phase A → Phase B → Phase C の 3 段階移行により、
既存のポーリングベースシステムからイベント駆動アーキテクチャへ
安全に移行する（詳細は `migration-guide.md` を参照）。

---

## 参考資料

- [Amazon S3 Event Notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventNotifications.html)
- [Amazon EventBridge Event Patterns](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-patterns.html)
- [AWS Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html)
- [FSx for NetApp ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html)
