# Deployment Profiles — FPolicy Event-Driven パターン

🌐 **Language / 言語**: [日本語](deployment-profiles.md) | [English](deployment-profiles.en.md)

## 概要

FPolicy Event-Driven パターンには、要件に応じた 3 つのデプロイメントプロファイルがあります。PoC から本番、コンプライアンス要件の厳しい環境まで、段階的に運用レベルを引き上げることができます。

## プロファイル比較

| Dimension | PoC/Demo | Production | Compliance-sensitive |
|-----------|----------|------------|---------------------|
| **FPolicy Server** | Fargate (direct IP) | EC2 static IP or NLB | EC2 static IP + NLB |
| **is-mandatory** | `false` | `true` (ONTAP 9.15.1+) | `true` (ONTAP 9.15.1+) |
| **Persistent Store** | 不要 | 推奨 | 必須 (ONTAP 9.14.1+) |
| **Retry / Dedup** | Best-effort | DynamoDB idempotency | DynamoDB + S3 Object Lock lineage |
| **Alarm Profile** | Minimal (error only) | Full (latency + error + backlog) | Full + audit trail |
| **Event Loss Tolerance** | 許容 | Near-zero (retry で補完) | Zero (Persistent Store + 監査) |
| **最低 ONTAP バージョン** | 9.14.1+ | 9.15.1+ | 9.15.1+ |
| **想定用途** | 機能検証、デモ、PoC | 本番ワークロード | 金融規制、医療、政府 |

---

## Profile 1: PoC/Demo

### 特徴

- **最小構成**: Fargate タスク 1 台、SQS、EventBridge のみ
- **IP 管理**: Fargate タスク再起動時に IP が変わるため、IP Updater Lambda で ONTAP external-engine を自動更新
- **イベントロス**: Fargate タスク再起動中（約 30-60 秒）のイベントは失われる可能性あり
- **コスト**: 最小（Fargate Spot 利用可能）

### 構成

```yaml
# template.yaml (event-driven-fpolicy/)
Parameters:
  IsMandatory:
    Default: "false"    # ファイル操作をブロックしない
  EnablePersistentStore:
    Default: "false"    # Persistent Store 不使用
  AlarmProfile:
    Default: "minimal"  # エラーアラームのみ
```

### 適用シナリオ

- 初回の FPolicy 動作確認
- パートナー向けデモ
- 開発・テスト環境
- イベントロスが許容される非クリティカルワークロード

---

## Profile 2: Production

### 特徴

- **高可用性**: EC2 static IP または NLB により、ONTAP external-engine の IP 再設定が不要
- **is-mandatory=true**: FPolicy サーバーが利用不可の場合、ファイル操作がブロックされる（イベントロス防止）
- **Persistent Store 推奨**: サーバー切断時のイベントバッファリング
- **冪等性保証**: DynamoDB による重複排除

### 構成

```yaml
Parameters:
  IsMandatory:
    Default: "true"     # サーバー不可時はファイル操作をブロック
  EnablePersistentStore:
    Default: "true"     # イベントバッファリング有効
  AlarmProfile:
    Default: "full"     # レイテンシ + エラー + バックログ
  ComputeType:
    Default: "ec2"      # Static IP
```

### is-mandatory=true の動作

`is-mandatory=true` (ONTAP 9.15.1+) を設定すると:
- FPolicy サーバーが接続されていない場合、対象のファイル操作がブロックされる
- これによりイベントロスを防止するが、サーバー障害時にファイルアクセスが停止するリスクがある
- 本番環境では NLB + 複数タスクによる冗長化が推奨

### Persistent Store の役割

Persistent Store (ONTAP 9.14.1+) は、FPolicy サーバーが切断された場合にイベントを SVM ボリュームに永続化し、再接続時に順序を保って送信します:

- **対象**: asynchronous (非同期) かつ non-mandatory の FPolicy ポリシー
- **イベント順序**: 保証される（発生順にリプレイ）
- **autoflush_interval**: 設定可能（デフォルト PT120S）
- **容量見積もり**: `event_rate × max_outage_duration × avg_event_size × safety_factor`

> **参考**: 1 GB のボリュームで約 200 万イベントをバッファ可能（1 イベント ≈ 500 bytes）

### 適用シナリオ

- 本番データパイプライン
- ニアリアルタイム処理が必要なワークロード
- SLA が定義されている環境

---

## Profile 3: Compliance-sensitive

### 特徴

- **イベントロスゼロ保証**: Persistent Store + is-mandatory + 監査証跡の組み合わせ
- **データリネージ**: S3 Object Lock による改ざん防止付きリネージレコード
- **RPO/RTO 定義**: 明確な復旧目標
- **監査対応**: 全イベントの処理証跡を保持

### 構成

```yaml
Parameters:
  IsMandatory:
    Default: "true"
  EnablePersistentStore:
    Default: "true"
  AlarmProfile:
    Default: "compliance"  # Full + audit trail + SLO violation
  EnableLineage:
    Default: "true"        # S3 Object Lock 7年保管
  EnableReplayStormProtection:
    Default: "true"        # Replay storm 時の流量制御
```

### コンプライアンス要件との対応

| 規制/基準 | 対応する機能 |
|-----------|-------------|
| FISC 安全対策基準 | イベントロスゼロ + 監査証跡 + 暗号化 |
| GDPR | データリネージ + 処理記録 + 削除追跡 |
| SOX | 改ざん防止リネージ (S3 Object Lock) |
| HIPAA | アクセスログ + 暗号化 + 監査 |
| NARA (政府アーカイブ) | 永久保管 + 完全性検証 |

### RPO/RTO 設計

| メトリクス | 目標値 | 実現方法 |
|-----------|--------|---------|
| RPO (Recovery Point Objective) | 0 events | Persistent Store + is-mandatory |
| RTO (Recovery Time Objective) | < 5 min | ECS auto-recovery + IP Updater |
| Replay Recovery Time | < 30 min (100K events) | Sustainable rate: 100 events/sec |

### 適用シナリオ

- 金融機関（FISC 対応）
- 医療機関（HIPAA 対応）
- 政府機関（NARA / FOIA 対応）
- 規制産業全般

---

## プロファイル選択フローチャート

```
イベントロスは許容できるか？
├── Yes → PoC/Demo
└── No
    ├── 規制/コンプライアンス要件があるか？
    │   ├── Yes → Compliance-sensitive
    │   └── No → Production
    └── (判断に迷う場合は Production から開始し、
         必要に応じて Compliance-sensitive に昇格)
```

## 段階的移行パス

```
PoC/Demo ──────→ Production ──────→ Compliance-sensitive
  │                  │                      │
  │ 追加:            │ 追加:                │
  │ • EC2/NLB        │ • S3 Object Lock     │
  │ • Persistent     │ • Lineage v2         │
  │   Store          │ • SLO Runbooks       │
  │ • DynamoDB       │ • Replay Storm       │
  │   idempotency    │   Protection         │
  │ • Full alarms    │ • Audit trail        │
  └──────────────────┴──────────────────────┘
```

## 参考リンク

- [FPolicy Persistent Store 設定ガイド](event-driven/fpolicy-persistent-store.md)
- [SLO Violation Runbooks](runbooks/)
- [Replay Storm Testing](../tests/load/)
- [ONTAP FPolicy — NetApp Documentation](https://docs.netapp.com/us-en/ontap/nas-audit/persistent-stores.html)
