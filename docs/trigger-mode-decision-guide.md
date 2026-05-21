# Trigger Mode Decision Guide — POLLING / EVENT_DRIVEN / HYBRID

🌐 **Language / 言語**: [日本語](trigger-mode-decision-guide.md) | [English](trigger-mode-decision-guide.en.md)

## 概要

本リポジトリは 3 つのトリガーモードを提供します。ワークロード要件に応じて最適なモードを選択してください。

## Decision Table

| Mode | Choose when | Avoid when |
|------|-------------|------------|
| **POLLING** | 時間単位・バッチ処理で十分 | サブ分単位の検知が必要 |
| **EVENT_DRIVEN** | ニアリアルタイム取り込みが必要で、再接続時のイベントロスが許容可能 | コンプライアンスが耐久性のあるイベントキャプチャを要求 |
| **HYBRID** | より高速な検知 + 定期的な整合性チェックが必要 | 最もシンプルな運用モデルを求める |

## 詳細比較

| Dimension | POLLING | EVENT_DRIVEN | HYBRID |
|-----------|---------|--------------|--------|
| **検知レイテンシ** | 分〜時間（スケジュール間隔依存） | 秒（FPolicy イベント即時） | 秒 + 定期キャッチアップ |
| **コスト** | 低（EventBridge Scheduler + Lambda 実行時のみ） | 中（Fargate 24/7 稼働） | 中〜高（Fargate + Scheduler） |
| **運用複雑性** | 低（ステートレス、冪等） | 高（TCP リスナー、IP 管理、ONTAP 設定） | 最高（両方の運用 + 整合性ロジック） |
| **イベント耐久性** | 高（ロスなし — 毎回全スキャン） | 中（Fargate 再起動中にギャップ発生） | 高（定期スキャンがギャップを補完） |
| **スケーラビリティ** | 高（Lambda 並列実行） | 中（Fargate タスク数に依存） | 高 |
| **ONTAP 依存** | なし（S3 AP のみ） | 高（FPolicy 設定、external-engine） | 高 |
| **対応プロトコル** | 全て（S3 AP 経由） | NFSv3/NFSv4.0/NFSv4.1/SMB | 全て |

## 各モードの詳細

### POLLING モード

```
EventBridge Scheduler (cron/rate)
  └─→ Step Functions
       ├─→ Discovery Lambda: ListObjectsV2 で差分検出
       ├─→ Map State: 新規/更新ファイルを並列処理
       └─→ Report Lambda: 結果通知
```

**差分検出方式**:
- LastModified タイムスタンプ比較
- DynamoDB に前回スキャン時刻を保持
- 新規・更新ファイルのみ処理

**メリット**:
- S3 AP のみで動作（FPolicy 不要）
- ステートレスで冪等
- 障害時のリカバリが容易（再実行するだけ）

**デメリット**:
- リアルタイム性がない
- スケジュール間隔中の変更は次回実行まで検出されない
- 大量ファイルの ListObjectsV2 はコスト増

### EVENT_DRIVEN モード

```
NFS/SMB File Operation
  └─→ ONTAP FPolicy Engine
       └─→ ECS Fargate (TCP :9898)
            └─→ SQS Queue
                 └─→ Bridge Lambda
                      └─→ EventBridge Custom Bus
                           └─→ Target (Step Functions / Lambda)
```

**メリット**:
- サブ秒のイベント検知
- ファイル操作の種類（create/write/delete/rename）を識別可能
- 不要なスキャンを回避

**デメリット**:
- Fargate タスク再起動時のイベントギャップ（30-60 秒）
- ONTAP FPolicy の設定・管理が必要
- TCP リスナーの運用（IP 追跡、ヘルスチェック）
- NFSv4.2 は FPolicy 非サポート

### HYBRID モード

```
[EVENT_DRIVEN パス]
NFS/SMB → FPolicy → Fargate → SQS → EventBridge → 即時処理

[POLLING パス（定期整合性チェック）]
EventBridge Scheduler → Step Functions → Discovery Lambda → 差分検出 → 補完処理
```

**メリット**:
- リアルタイム検知 + 定期的なギャップ補完
- イベントロスのリスクを最小化
- 両方のパスが独立して動作

**デメリット**:
- 運用複雑性が最も高い
- 重複処理の排除ロジックが必要（DynamoDB idempotency）
- コストが最も高い

## 選択フローチャート

```
リアルタイム検知が必要か？
├── No → POLLING
│        (最もシンプル、コスト最小)
└── Yes
    ├── イベントロスは許容できるか？
    │   ├── Yes → EVENT_DRIVEN
    │   │        (Persistent Store なしでも可)
    │   └── No
    │       ├── Persistent Store (ONTAP 9.14.1+) が利用可能か？
    │       │   ├── Yes → EVENT_DRIVEN + Persistent Store
    │       │   │        (Production / Compliance profile)
    │       │   └── No → HYBRID
    │       │            (POLLING で定期補完)
    │       └── 最もシンプルな運用を優先するか？
    │           ├── Yes → EVENT_DRIVEN + Persistent Store
    │           └── No → HYBRID
    └── (判断に迷う場合)
        → POLLING から開始し、要件に応じて EVENT_DRIVEN に移行
```

## コスト比較（月額概算、ap-northeast-1）

| コンポーネント | POLLING (1時間間隔) | EVENT_DRIVEN | HYBRID |
|--------------|-------------------|--------------|--------|
| EventBridge Scheduler | ~$1 | — | ~$1 |
| Lambda (Discovery) | ~$5-20 | — | ~$5-20 |
| Lambda (Processing) | ワークロード依存 | ワークロード依存 | ワークロード依存 |
| Fargate (24/7) | — | ~$30-50 | ~$30-50 |
| SQS | — | ~$1-5 | ~$1-5 |
| DynamoDB (idempotency) | — | ~$1-5 | ~$5-10 |
| **合計（処理 Lambda 除く）** | **~$6-21** | **~$32-60** | **~$42-86** |

> 上記は小〜中規模ワークロード（1000 ファイル/日程度）の概算。実際のコストはファイル数、サイズ、処理内容に依存。

## 移行パス

```
POLLING ──→ EVENT_DRIVEN ──→ HYBRID
  │              │               │
  │ 追加:        │ 追加:          │
  │ • FPolicy    │ • Scheduler    │
  │ • Fargate    │ • Discovery    │
  │ • SQS        │   Lambda       │
  │ • Bridge     │ • Dedup logic  │
  └──────────────┴───────────────┘
```

## 参考リンク

- [ストリーミング vs ポーリング選択ガイド](streaming-vs-polling-guide.md)
- [イベント駆動 FPolicy クイックスタート](event-driven/README.md)
- [Deployment Profiles](deployment-profiles.md)
- [FPolicy Persistent Store 設定](event-driven/fpolicy-persistent-store.md)
