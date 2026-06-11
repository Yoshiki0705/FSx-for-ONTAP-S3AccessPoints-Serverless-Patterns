# AWS ネイティブオブザーバビリティ設計

[日本語](observability-aws-native-ja.md) | [English](observability-aws-native.md)

AWS ネイティブサービスのみを使用した、ハイブリッドクラウド SnapMirror 同期パターンのオブザーバビリティアーキテクチャを定義します。

> このオブザーバビリティ設計はサードパーティのオブザーバビリティプラットフォームを必要としません。目標は、ハイブリッドデータパイプラインを AWS ネイティブサービスで **説明可能** にすることです — オペレーターが「データは最新か？パイプラインは正常か？何が失敗し、なぜか？」にいつでも回答できるようにします。

## 使用する AWS サービス

| サービス | 役割 |
|---------|------|
| Amazon CloudWatch Metrics | カスタムメトリクス（EMF）、SnapMirror ラグ、データ経過時間 |
| Amazon CloudWatch Logs | Sync Server からの構造化イベントログ |
| Amazon CloudWatch Logs Insights | アドホック調査と相関分析 |
| Amazon CloudWatch Dashboards | 運用レディネスダッシュボード |
| Amazon CloudWatch Alarms | ラグ、障害のしきい値アラート |
| Amazon CloudWatch Synthetics | S3 AP / UI ヘルスの外部カナリア |
| CloudWatch Application Signals | データ鮮度の SLO トラッキング |
| AWS X-Ray | 同期パイプライン全体の分散トレーシング |
| AWS Distro for OpenTelemetry (ADOT) | 計装コレクター |
| AWS CloudTrail | API 監査証跡 |

## CloudWatch カスタムメトリクス (Namespace: HybridCloud/SnapMirrorSync)

| メトリクス | 単位 | 説明 |
|-----------|------|------|
| SnapMirrorLagSeconds | Seconds | 最後の成功レプリケーションからの経過時間 |
| LastReplicationAgeSeconds | Seconds | 最新レプリケーションデータの経過時間 |
| S3APCanarySuccess | Count | 1 = 成功、0 = 失敗（カナリア実行ごと） |
| S3APListLatencyMs | Milliseconds | S3 AP 経由の ListObjectsV2 応答時間 |
| S3APGetLatencyMs | Milliseconds | S3 AP 経由の GetObject 応答時間 |
| QuickRefreshSuccess | Count | 1 = データセット更新成功 |
| QuickDashboardDataAgeSeconds | Seconds | Quick ダッシュボードデータの更新からの経過時間 |
| SourceToInsightLatencySeconds | Seconds | エンドツーエンド: ソース書き込みから Quick 表示まで |
| SyncTriggerCount | Count | ワンクリック同期トリガー回数 |
| SyncFailureCount | Count | 失敗した同期試行回数 |

### ディメンション

| ディメンション | 値 | 目的 |
|-------------|---|------|
| Environment | demo, poc, production | ステージ別メトリクス分離 |
| Volume | vol_source, vol_dest | ボリューム別メトリクス追跡 |
| SVMName | svm_source, svm_dest | SVM レベルの帰属 |

> **注意**: CloudWatch メトリクスにはハイカーディナリティディメンション（request_id、user_id 等）を避け、コストを制御してください。ハイカーディナリティの相関には構造化ログを使用してください。

## CloudWatch ダッシュボード: HybridCloudSnapMirrorSync-Readiness

| ウィジェット | メトリクス / ソース | 目的 |
|------------|-------------------|------|
| SnapMirror Lag | SnapMirrorLagSeconds | 現在のレプリケーション遅延 |
| Last Replication | LastReplicationAgeSeconds | 最後のデータ同期日時 |
| S3 AP Canary | S3APCanarySuccess (sum/period) | 外部ヘルスチェック |
| S3 AP Latency | S3APListLatencyMs p50/p95/p99 | パフォーマンスベースライン |
| Quick Refresh | QuickRefreshSuccess | データセット鮮度 |
| Data Age | QuickDashboardDataAgeSeconds | ビジネスデータの陳腐化 |
| Source-to-Insight | SourceToInsightLatencySeconds p95 | エンドツーエンド SLI |
| Sync Triggers | SyncTriggerCount | 利用パターン |
| Failures | SyncFailureCount | エラー率 |
| Demo Readiness | Composite (all green = ready) | デモの Go/No-go 判定 |

## Embedded Metric Format (EMF) 例

Sync Server が埋め込みメトリクス付きの構造化ログを出力:

```json
{
  "_aws": {
    "Timestamp": 1718006400000,
    "CloudWatchMetrics": [{
      "Namespace": "HybridCloud/SnapMirrorSync",
      "Dimensions": [["Environment", "Volume"]],
      "Metrics": [
        {"Name": "SnapMirrorLagSeconds", "Unit": "Seconds"},
        {"Name": "SyncTriggerCount", "Unit": "Count"}
      ]
    }]
  },
  "Environment": "demo",
  "Volume": "vol_source",
  "SnapMirrorLagSeconds": 3,
  "SyncTriggerCount": 1,
  "correlation_id": "demo-2026-06-10-001",
  "event_type": "sync_completed",
  "status": "success"
}
```

> 参考: [CloudWatch Embedded Metric Format Specification](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format_Specification.html)

## CloudWatch Synthetics カナリア

| カナリア | タイプ | スケジュール | 検証内容 |
|---------|--------|-----------|---------|
| S3AP-List | API canary | 5分 | S3 AP エイリアス経由の ListObjectsV2 がオブジェクトを返す |
| S3AP-Get | API canary | 5分 | ヘルスマーカーファイルの GetObject が成功する |
| SyncUI-Health | Heartbeat | 5分 | Sync Server /api/health が status: ok を返す |

> 参考: [CloudWatch Synthetics Blueprints](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Synthetics_Canaries_Blueprints.html)

## X-Ray / ADOT トレーシング

本番デプロイでは、ADOT で Sync Server を計装し以下をトレース:
- HTTP リクエスト → ONTAP REST API コール → SnapMirror トリガー → ステータスポーリング → 完了

X-Ray アノテーション:
- `snapmirror.uuid`
- `transfer.state`
- `transfer.bytes`
- `environment`

> 参考: [AWS Distro for OpenTelemetry](https://docs.aws.amazon.com/xray/latest/devguide/xray-concepts-tracingheader.html)
