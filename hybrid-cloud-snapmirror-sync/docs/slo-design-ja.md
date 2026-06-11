# SLO 設計

[日本語](slo-design-ja.md) | [English](slo-design.md)

ハイブリッドクラウド SnapMirror 同期パターンの Service Level Objectives。
CloudWatch Application Signals 向けに設計。

> 参考: [CloudWatch Application Signals SLO](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-ServiceLevelObjectives.html)

## SLO 候補

| # | SLO 名 | SLI メトリクス | タイプ | 目標 | ウィンドウ |
|---|--------|-------------|--------|------|----------|
| 1 | Replication Freshness | QuickDashboardDataAgeSeconds | Period-based | 5分期間の95% で ≤ 600s | 7日 |
| 2 | S3 AP Availability | S3APCanarySuccess | Period-based | 99% 成功 | 7日ローリング |
| 3 | Quick Insight Readiness | QuickRefreshSuccess | Period-based | 95% 成功 | 7日ローリング |
| 4 | Source-to-Insight Latency | SourceToInsightLatencySeconds | Period-based | p95 ≤ 900s | 7日 |
| 5 | Sync Trigger Reliability | SyncTriggerCount vs SyncFailureCount | Request-based | 95% 成功 | 7日 |

## SLO 詳細

### 1. Replication Freshness

- **測定内容**: Amazon Quick のデータがソースに対してどの程度新しいか
- **SLI**: `QuickDashboardDataAgeSeconds ≤ 600` となる5分期間の割合
- **目標**: 95%
- **エラーバジェット**: 5% の期間（約8.4時間/週）が10分を超えてもよい
- **アラートしきい値**: エラーバジェット消費速度 > 2倍

### 2. S3 AP Availability

- **測定内容**: S3 Access Point が到達可能でデータを返すか
- **SLI**: CloudWatch Synthetics カナリア成功率
- **目標**: 99%
- **エラーバジェット**: 約1.7時間/週のダウンタイム
- **アラートしきい値**: 3回連続失敗

### 3. Quick Insight Readiness

- **測定内容**: Amazon Quick のデータセット更新が成功しているか
- **SLI**: QuickRefreshSuccess count / 総試行回数
- **目標**: 95%
- **エラーバジェット**: 5% の更新失敗を許容
- **アラートしきい値**: 2回連続更新失敗

### 4. Source-to-Insight Latency

- **測定内容**: ソースファイル書き込みから Quick で表示されるまでのエンドツーエンド時間
- **SLI**: SourceToInsightLatencySeconds p95
- **目標**: p95 ≤ 15分（900秒）
- **エラーバジェット**: 5% の測定が15分を超えてもよい
- **アラートしきい値**: p95 > 20分が2期間連続

### 5. Sync Trigger Reliability

- **測定内容**: ワンクリック同期トリガーが成功するか
- **SLI**: (SyncTriggerCount - SyncFailureCount) / SyncTriggerCount
- **目標**: 95%
- **エラーバジェット**: 5% のトリガーが失敗してもよい
- **アラートしきい値**: 3回連続トリガー失敗

## 実装メモ

- CloudWatch Application Signals は period-based と request-based の両方の SLO をサポート
- SLO は自動的に `AWSServiceRoleForCloudWatchApplicationSignals` サービスリンクロールを作成
- エラーバジェットは自動追跡され、Application Signals コンソールで可視化
- SLO はコンソール、CLI、または CloudFormation（`AWS::ApplicationSignals::ServiceLevelObjective`）で作成可能

## デモ vs 本番 PoC のしきい値

| SLO | デモしきい値 | 本番 PoC しきい値 |
|-----|------------|-----------------|
| Replication Freshness | データ経過時間 ≤ 10分 | RPO に基づき顧客定義（推奨開始値: ≤ 15分） |
| S3 AP Availability | 99%（7日） | 99.5%+（顧客 SLA 準拠） |
| Quick Readiness | 95% 更新成功 | 99%（本番ダッシュボード） |
| Source-to-Insight | p95 ≤ 15分 | 顧客定義（推奨: ≤ 10分） |
| Sync Reliability | 95% トリガー成功 | 99%（自動スケジュール） |

> **注意**: デモしきい値を本番要件として使用しないでください。本番 SLO は顧客の RPO、ビジネスクリティカリティ、運用キャパシティに基づいて顧客と協力して定義する必要があります。

## インシデント対応フロー

SLO エラーバジェットが消費された場合:

1. CloudWatch ダッシュボード（HybridCloudSnapMirrorSync-Readiness）を確認
2. どの SLI が劣化しているか特定
3. correlation_id で CloudWatch Logs Insights を確認
4. 最近の S3 AP / FSx / IAM 変更を CloudTrail で確認
5. /api/health 経由で SnapMirror 関係の正常性を確認
6. 判断: 根本原因を修正するか、デモフォールバックに切り替える
