# PoC Go/No-Go 判定基準テンプレート

## 概要

本テンプレートは、FSx for ONTAP S3AP Serverless Patterns の PoC 実施後に
本番移行の可否を判断するための基準を定義します。

## 判定基準テーブル

### 必須基準（全て PASS で Go）

| # | 基準 | 測定方法 | 閾値 | 結果 |
|---|------|---------|------|------|
| 1 | S3 AP 経由のファイル読み取り成功 | Discovery Lambda 実行 | エラー率 < 1% | ☐ PASS / ☐ FAIL |
| 2 | E2E ワークフロー完走 | Step Functions 実行 | 成功率 > 95% | ☐ PASS / ☐ FAIL |
| 3 | レイテンシ要件充足 | CloudWatch Metrics | P95 < ___ ms | ☐ PASS / ☐ FAIL |
| 4 | コスト許容範囲内 | AWS Cost Explorer | 月額 < ¥___ | ☐ PASS / ☐ FAIL |
| 5 | セキュリティ要件充足 | IAM Access Analyzer | 過剰権限なし | ☐ PASS / ☐ FAIL |

### 推奨基準（80% 以上 PASS で Go）

| # | 基準 | 測定方法 | 閾値 | 結果 |
|---|------|---------|------|------|
| 6 | AI/ML 出力品質 | Human Review サンプリング | 精度 > ___% | ☐ PASS / ☐ FAIL |
| 7 | 運用負荷許容範囲 | 運用チームヒアリング | 週 ___ 時間以内 | ☐ PASS / ☐ FAIL |
| 8 | スケーラビリティ | 負荷テスト | ___ files/hour 処理可能 | ☐ PASS / ☐ FAIL |
| 9 | 障害復旧 | DR テスト | RTO < ___ 分 | ☐ PASS / ☐ FAIL |
| 10 | 監査証跡 | CloudTrail + Logs 確認 | 全操作追跡可能 | ☐ PASS / ☐ FAIL |

## 判定フロー

```
必須基準 5/5 PASS?
  ├─ YES → 推奨基準 8/10 以上 PASS?
  │         ├─ YES → ✅ Go（本番移行承認）
  │         └─ NO  → ⚠️ Conditional Go（改善計画付き）
  └─ NO  → ❌ No-Go（再 PoC or 代替案検討）
```

## 記入例

### プロジェクト情報

| 項目 | 値 |
|------|-----|
| 顧客名 | _______________ |
| ユースケース | UC___ : _______________ |
| PoC 期間 | ___/___/_____ 〜 ___/___/_____ |
| 担当 SA | _______________ |
| 担当 SI | _______________ |

### 環境情報

| 項目 | 値 |
|------|-----|
| AWS リージョン | _______________ |
| FSx for ONTAP 構成 | Single-AZ / Multi-AZ, ___ MBps |
| S3 AP NetworkOrigin | Internet / VPC |
| データ量 | ___ files, ___ GB |
| 実行頻度 | _______________ |

### 判定結果

| 判定 | 日付 | 承認者 |
|------|------|--------|
| ☐ Go / ☐ Conditional Go / ☐ No-Go | ___/___/_____ | _______________ |

### 次フェーズ計画（Go の場合）

| 項目 | 内容 |
|------|------|
| 本番デプロイ予定日 | _______________ |
| Deployment Profile | PoC / Production / Compliance-sensitive |
| 追加要件 | _______________ |
| 見積もり工数 | ___ 人日 |
| 月額コスト見込み | ¥_______________ |

---

> **Governance Caveat**: 本テンプレートは技術的な PoC 判定を支援するものです。最終的なビジネス判断は顧客の意思決定プロセスに従ってください。
