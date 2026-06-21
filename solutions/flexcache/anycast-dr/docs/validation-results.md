# FC1 Validation Results

🌐 **Language / 言語**: [日本語](validation-results.md)

## Test Environment

| Item | Value |
|------|-------|
| FSx for ONTAP version | TBD |
| FlexCache configuration | TBD |
| Region | ap-northeast-1 |
| SimulationMode | false |
| Test date | TBD |
| benchmark_run_id | TBD |

---

## Measured Metrics

| Metric | Target | Measured | Status |
|--------|--------|----------|--------|
| Route decision latency | < 500 ms | TBD | ⏳ |
| Cache health detection time | < 30 s | TBD | ⏳ |
| Origin unavailable detection time | < 60 s | TBD | ⏳ |
| Time to switch active read path | < 60 s | TBD | ⏳ |
| DynamoDB routing table update latency | < 1 s | TBD | ⏳ |
| Audit event completeness | 100% | TBD | ⏳ |

---

## False Positive / False Negative Analysis

| Scenario | Expected | Observed | Iterations | Notes |
|----------|----------|----------|-----------|-------|
| Healthy cache reported unhealthy (FP) | 0 | TBD | 100 | |
| Unhealthy cache reported healthy (FN) | 0 | TBD | 100 | |
| Transient network issue (short timeout) | No failover | TBD | 10 | |
| Sustained origin failure | Failover within target | TBD | 5 | |

---

## Measurement Methodology

### Route Decision Latency
- Step Functions 実行時間から RouteDecision Lambda の duration を抽出
- CloudWatch Logs Insights で p50/p90/p99 を算出

### Cache Health Detection Time
- HealthCheck Lambda の実行間隔 × 異常検知に要した実行回数
- 意図的にキャッシュを停止してから検知までの経過時間

### Origin Unavailable Detection Time
- Origin ボリュームを意図的にオフラインにしてから、HealthCheck が異常を報告するまでの時間

### Time to Switch Active Read Path
- Origin 障害検知 → RouteDecision → DynamoDB 更新 → DNS/Route 切替完了までの合計時間
- Route 53 TTL を含む end-to-end 時間

### DynamoDB Routing Table Update Latency
- PutItem API の Duration（CloudWatch Logs から抽出）

### Audit Event Completeness
- 全ルート変更イベントに対する DynamoDB 監査レコードの存在率
- CloudWatch Logs との突合

---

## Notes

> **重要**: 本結果はサービス上限値ではありません。特定のテスト環境における validation reference です。
> 実案件では、顧客のネットワーク構成、FlexCache サイズ、ワークロード特性に応じて結果が異なります。

---

## 参考リンク

- [FlexCache AnyCast/DR README](../README.md)
- [Architecture](architecture.md)
- [PoC Checklist](poc-checklist.md)
- [Operations Runbook](operations-runbook.md)
