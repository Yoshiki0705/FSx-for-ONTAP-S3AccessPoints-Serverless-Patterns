# Production Readiness — Maturity Model

🌐 **Language / 言語**: [日本語](production-readiness.md) | [English](production-readiness.en.md)

## 概要

本ドキュメントは、PoC から本番環境への段階的な成熟度モデルを定義します。各レベルで必要な成果物、設計項目、運用項目を明確にし、「今どこにいて、次に何をすべきか」を判断できるようにします。

### Field-Ready Baseline

Phase 13 は最終到達点ではなく、以下のための実用的なベースラインです:
- **Informed evaluation** — 評価に必要な情報が揃っている
- **Governed experimentation** — 統制された試行錯誤が可能
- **Structured delivery** — 構造化されたデリバリーパスがある
- **Production-readiness planning** — 本番化計画の材料が揃っている

各レベルの完了条件は [Exit Criteria](#exit-criteria各レベル完了条件) を参照してください。

---

## Maturity Model

```
Level 1          Level 2          Level 3          Level 4
Sandbox    →    Scheduled    →    Monitored    →    Production
(手動実行)      (定期実行)        (可観測性付き)     (本番運用)
```

---

## Level 1: Sandbox（手動実行）

### 目的
- パターンの動作確認
- S3 AP 経由のファイルアクセス検証
- AI/ML サービスの出力品質確認

### 必要な成果物
- [ ] CloudFormation テンプレートのデプロイ成功
- [ ] S3 AP 経由の ListObjectsV2 / GetObject 動作確認
- [ ] サンプルファイルでの AI/ML 処理結果確認
- [ ] Step Functions 手動実行の成功

### 設計項目
| 項目 | Level 1 の状態 |
|------|--------------|
| トリガー | 手動実行（コンソール or CLI） |
| データ | サンプルデータ（test-data/ 配下） |
| エラー処理 | Lambda デフォルト retry のみ |
| 監視 | CloudWatch Logs 目視確認 |
| セキュリティ | デフォルト IAM（テンプレート付属） |
| コスト | 実行時のみ課金 |

### 所要時間: 1-2 時間

---

## Level 2: Scheduled（定期実行）

### 目的
- EventBridge Scheduler による自動実行
- 実データでの継続的な処理
- 基本的なエラー検知

### 必要な成果物
- [ ] EventBridge Scheduler 設定（rate or cron）
- [ ] 実データでの処理成功確認（最低 1 週間）
- [ ] DLQ (Dead Letter Queue) 設定
- [ ] 基本アラーム（Step Functions 失敗時 SNS 通知）

### 設計項目
| 項目 | Level 2 の状態 |
|------|--------------|
| トリガー | EventBridge Scheduler (rate(1h) 等) |
| データ | 実データ（FSx for ONTAP Volume） |
| エラー処理 | DLQ + SNS 通知 |
| 監視 | CloudWatch Alarm (エラー率) |
| セキュリティ | 最小権限 IAM + S3 AP Policy |
| コスト | 月額 $6-21（POLLING モード） |

### 所要時間: 1-2 日

---

## Level 3: Monitored（可観測性付き）

### 目的
- 包括的な可観測性の確立
- パフォーマンス・コストの可視化
- 障害の早期検知と対応

### 必要な成果物
- [ ] CloudWatch Dashboard（処理件数、レイテンシ、エラー率）
- [ ] X-Ray トレーシング有効化
- [ ] EMF メトリクス出力（FilesProcessed, Duration, Errors）
- [ ] Alarm Profile 設定（BATCH / REALTIME / HIGH_VOLUME）
- [ ] コスト可視化（Cost Scheduling メトリクス）
- [ ] 運用 Runbook（障害対応手順）

### 設計項目
| 項目 | Level 3 の状態 |
|------|--------------|
| トリガー | Scheduler + Business Hours 最適化 |
| データ | 実データ + 差分検出（LastModified 比較） |
| エラー処理 | DLQ + Retry + SNS + Runbook |
| 監視 | Dashboard + Alarm + X-Ray + EMF |
| セキュリティ | IAM + AP Policy + VPC Endpoint Policy |
| コスト | 月額 $20-60 + 可視化 |

### 所要時間: 3-5 日

---

## Level 4: Production（本番運用）

### 目的
- マルチアカウント対応
- CI/CD パイプライン
- DR / 障害復旧
- コンプライアンス・監査対応
- SLO 定義と運用

### 必要な成果物
- [ ] StackSets によるマルチアカウントデプロイ
- [ ] CI/CD パイプライン（cfn-lint + pytest + デプロイ自動化）
- [ ] データリネージ（DynamoDB + S3 Object Lock）
- [ ] SLO 定義と違反時 Runbook
- [ ] DR 設計（SnapMirror + Cross-Region）
- [ ] セキュリティレビュー完了
- [ ] 運用引き継ぎドキュメント
- [ ] 定期的な AI 出力品質レビュー体制

### 設計項目
| 項目 | Level 4 の状態 |
|------|--------------|
| トリガー | POLLING + EVENT_DRIVEN (HYBRID) |
| データ | 実データ + 冪等性保証 + リネージ |
| エラー処理 | Full retry + DLQ + Runbook + 自動復旧 |
| 監視 | SLO + Dashboard + Alarm + X-Ray + Lineage |
| セキュリティ | Full dual-layer + SCP + VPC EP + 監査ログ |
| コスト | 月額 $50-200 + コスト異常検知 |
| DR | SnapMirror + Cross-Region backup |
| CI/CD | StackSets + GitHub Actions + cfn-lint |

### 所要時間: 2-4 週間

---

## Maturity Level と Success Metrics の対応

| Level | 対応する Success Metrics | 測定の焦点 |
|-------|------------------------|-----------|
| Level 1 (Sandbox) | デプロイ成功、手動実行成功 | 動作確認 |
| Level 2 (Scheduled) | 処理件数/実行、処理時間、エラー率 | 安定性確認 |
| Level 3 (Monitored) | レイテンシ P90/P99、コスト/実行、アラート応答時間 | 性能・コスト可視化 |
| Level 4 (Production) | SLO 達成率、Human Review 率、監査証跡完全性、コスト目標達成 | 運用品質 |

> 各 UC の Success Metrics（Outcome / Metric / Measurement Method）は、上記の Level に応じて段階的に測定・評価してください。Level 1 では動作確認のみ、Level 4 では全指標の継続的モニタリングが必要です。

---

## Exit Criteria（各レベル完了条件）

### Level 1 → Level 2 への移行条件
- [ ] CloudFormation デプロイが成功し、手動実行で期待結果が得られた
- [ ] S3 AP 経由の ListObjectsV2 / GetObject が正常動作した
- [ ] AI/ML 処理結果の品質が業務要件を満たすことを確認した

### Level 2 → Level 3 への移行条件
- [ ] EventBridge Scheduler による定期実行が 1 週間以上安定動作した
- [ ] エラー時の SNS 通知が正しく届くことを確認した
- [ ] 対象データセットでの処理時間が測定・記録された
- [ ] DLQ にメッセージが蓄積されていないことを確認した

### Level 3 → Level 4 への移行条件
- [ ] CloudWatch Dashboard でメトリクスが可視化されている
- [ ] Alarm Profile が設定され、閾値超過時に通知が届く
- [ ] X-Ray トレーシングで実行パスが確認可能
- [ ] 運用 Runbook が作成され、障害対応訓練が実施された
- [ ] コスト可視化が有効で、月次レビューが実施されている
- [ ] セキュリティレビューが完了している

### 運用上の注意事項（Level 3 以上）

#### FSx Throughput Capacity 変更時の S3 AP 影響

FSx for ONTAP の throughput capacity を変更すると、**S3 Access Points が一時的に利用不可**になる場合があります（Phase 14 で観測）。

| 項目 | 詳細 |
|------|------|
| 影響範囲 | 同一ファイルシステム上の全 SVM の全 S3 AP |
| エラー | `ServiceUnavailable` または `ConnectionClosedError` |
| 復旧時間 | 不明（AWS サポートに確認中） |
| NFS/SMB への影響 | AWS ドキュメントでは通常影響なしと記載。S3 AP のみが影響を受けた可能性（未検証） |

**推奨事項**:
- Throughput capacity 変更はメンテナンスウィンドウ中に実施する
- S3 AP 経由のワークロードが停止しても許容できるタイミングで実施する
- 変更後に S3 AP の正常動作を確認してからワークロードを再開する
- CloudWatch Alarm で S3 AP ヘルスチェックを設定し、復旧を検知する

## Level 別チェックマトリクス

### CI/CD バッジとの対応

| Level | 対応するバッジ / 検証状態 |
|-------|------------------------|
| Level 1 (Sandbox) | `sam build` 成功、`sam deploy` 成功 |
| Level 2 (Scheduled) | ![tests](https://img.shields.io/badge/tests-passed-brightgreen) pytest 全テスト PASS |
| Level 3 (Monitored) | ![cfn-lint](https://img.shields.io/badge/cfn--lint-0%20errors-brightgreen) cfn-lint + ruff 0 errors |
| Level 4 (Production) | ![region](https://img.shields.io/badge/verified-ap--northeast--1-blue) AWS 実環境検証済み + セキュリティチェック PASS |

| 項目 | L1 | L2 | L3 | L4 |
|------|:--:|:--:|:--:|:--:|
| CloudFormation デプロイ | ✅ | ✅ | ✅ | ✅ |
| EventBridge Scheduler | — | ✅ | ✅ | ✅ |
| DLQ | — | ✅ | ✅ | ✅ |
| SNS 通知 | — | ✅ | ✅ | ✅ |
| CloudWatch Dashboard | — | — | ✅ | ✅ |
| X-Ray | — | — | ✅ | ✅ |
| Alarm Profile | — | — | ✅ | ✅ |
| Business Hours Scheduling | — | — | ✅ | ✅ |
| Runbook | — | — | ✅ | ✅ |
| StackSets | — | — | — | ✅ |
| CI/CD | — | — | — | ✅ |
| Data Lineage | — | — | — | ✅ |
| SLO | — | — | — | ✅ |
| DR | — | — | — | ✅ |
| Governance Checklist | — | — | — | ✅ |
| Human-in-the-loop | — | — | — | ✅ (規制対象) |

---

## 参考リンク

- [Deployment Profiles](deployment-profiles.md) — FPolicy 固有の PoC/Prod/Compliance 分類
- [Governance Checklist](governance-checklist.md) — 規制・公共セクター向け
- [Partner/SI Delivery Checklist](partner-si-delivery-checklist.md) — 提案・構築チェック
- [Trigger Mode Decision Guide](trigger-mode-decision-guide.md) — モード選択
