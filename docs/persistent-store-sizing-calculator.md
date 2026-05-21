# FPolicy Persistent Store Sizing Calculator

🌐 **Language / 言語**: [日本語](persistent-store-sizing-calculator.md) | [English](persistent-store-sizing-calculator.en.md)

## 概要

ONTAP FPolicy Persistent Store（ONTAP 9.14.1+）のボリュームサイズと Replay Recovery Time を計算するためのガイドです。

## 計算式

### ボリュームサイズ

```
required_size = event_rate_per_sec × max_outage_duration_sec × avg_event_size_bytes × safety_factor
```

### Replay Recovery Time

```
replay_recovery_time = buffered_events / sustainable_processing_rate
```

## サイジングテーブル

### ボリュームサイズ見積もり

| シナリオ | イベント/秒 | 最大停止時間 | イベントサイズ | 安全係数 | 必要容量 | バッファ可能イベント数 |
|---------|-----------|------------|-------------|---------|---------|-------------------|
| 開発/テスト | 10 | 5 分 (300s) | 500 B | 2.0 | 3 MB | ~6,000 |
| 小規模本番 | 50 | 5 分 (300s) | 500 B | 2.0 | 15 MB | ~30,000 |
| 中規模本番 | 100 | 5 分 (300s) | 500 B | 2.0 | 30 MB | ~60,000 |
| 大規模本番 | 500 | 10 分 (600s) | 500 B | 2.0 | 300 MB | ~600,000 |
| 高負荷 | 1,000 | 10 分 (600s) | 500 B | 2.0 | 600 MB | ~1,200,000 |
| 極高負荷 | 5,000 | 10 分 (600s) | 500 B | 2.0 | 3 GB | ~6,000,000 |

### Replay Recovery Time 見積もり

| バッファ済みイベント | 処理レート | Recovery Time | 備考 |
|-------------------|-----------|--------------|------|
| 10,000 | 100 events/sec | 100 秒 (< 2 分) | 小規模、即座に追いつく |
| 50,000 | 100 events/sec | 500 秒 (≈ 8 分) | 中規模 |
| 100,000 | 100 events/sec | 1,000 秒 (≈ 17 分) | 大規模 |
| 100,000 | 500 events/sec | 200 秒 (≈ 3 分) | 高スループット処理 |
| 1,000,000 | 100 events/sec | 10,000 秒 (≈ 2.8 時間) | 極大規模、要設計 |
| 1,000,000 | 500 events/sec | 2,000 秒 (≈ 33 分) | 高スループット + 極大規模 |

## Sustainable Processing Rate の制約要因

Replay 時のスループットは以下のボトルネックで決まります:

| コンポーネント | 制約 | 対策 |
|--------------|------|------|
| FPolicy Server (TCP 受信) | CPU/メモリ依存 | t4g.small 以上に変更 |
| SQS SendMessage | 3,000 msg/sec per queue | バッチ送信 (SendMessageBatch) |
| Bridge Lambda (SQS → EventBridge) | Lambda 同時実行数 | Reserved Concurrency 設定 |
| EventBridge PutEvents | 10,000 entries/sec per account | 通常は十分 |
| DynamoDB (Idempotency) | WCU 依存 | On-Demand or 十分な WCU |
| Downstream Lambda | 同時実行数 | MaxConcurrency 制御 |

## 推奨サイズ（クイックリファレンス）

| Deployment Profile | 推奨ボリュームサイズ | 想定シナリオ |
|-------------------|-------------------|------------|
| PoC/Demo | 不要（Persistent Store なし） | イベントロス許容 |
| Production | 100 MB - 1 GB | 5 分停止 × 100-1000 events/sec |
| Compliance-sensitive | 1 GB - 5 GB | 10 分停止 × 1000+ events/sec |

## 設定例

```bash
# 1 GB Persistent Store ボリューム作成
curl -k -u fsxadmin:PASSWORD \
  -X POST "https://<ONTAP_MGMT_IP>/api/storage/volumes" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "fpolicy_persistent_store",
    "svm": {"uuid": "<SVM_UUID>"},
    "size": "1GB",
    "type": "rw",
    "nas": {
      "path": "/fpolicy_persistent_store",
      "security_style": "unix"
    },
    "guarantee": {"type": "none"}
  }'
```

## 監視推奨

| メトリクス | 閾値 | アクション |
|-----------|------|----------|
| ボリューム使用率 | > 80% | アラート + 容量拡張検討 |
| Replay 所要時間 | > SLO 目標 | 処理レート改善 or ボリューム拡張 |
| バッファ済みイベント数 | > 想定最大値の 50% | 停止時間短縮 or 容量拡張 |

## 参考リンク

- [FPolicy Persistent Store 設定ガイド](event-driven/fpolicy-persistent-store.md)
- [Deployment Profiles](deployment-profiles.md)
- [ONTAP Persistent Store — NetApp Documentation](https://docs.netapp.com/us-en/ontap/nas-audit/persistent-stores.html)
