# 関連ソリューション参照 — 重複回避 & アプローチ比較

> このドキュメントは operations/ パターンの設計・実装時に参照し、
> 車輪の再発明を防止し、各ソリューションのアプローチの違いを整理します。

---

## 1. NetApp 公式リポジトリ

### [NetApp/FSx-ONTAP-samples-scripts](https://github.com/NetApp/FSx-ONTAP-samples-scripts)

NetApp が維持する FSx for ONTAP 運用スクリプト集。

#### Management-Utilities (重複リスク: 中〜高)

| ツール | 機能 | このパターンとの関係 |
|--------|------|---------------------|
| `auto_set_fsxn_auto_grow` | Volume autosize を grow モードに設定 | OPS1 で autosize 状態を**読み取り**、有効化を**推奨**する。直接操作は Level 2+ のみ。重複なし (推奨 vs 直接設定) |
| `warm_performance_tier` | SSD ティアのウォームアップ | OPS3 (tiering-optimizer) は**分析+推奨**。ウォームアップ操作自体は対象外。補完関係。 |
| `fsxn-rotate-secret` | Secrets Manager ローテーション | このパターンはローテーション済みシークレットの**利用者**。重複なし。 |
| `fsx-ontap-aws-cli-scripts` | CLI 管理スクリプト集 | スクリプト集 vs サーバーレスパターン。アプローチが根本的に異なる。 |

#### Monitoring (重複リスク: 高)

| ツール | 機能 | このパターンとの関係 |
|--------|------|---------------------|
| `auto-add-cw-alarms` | CloudWatch アラーム自動追加 | OPS1 Level 1 でアラート発報。このパターンは推奨コンテキスト + AI 推奨 + What-If + マルチ FS 横断を追加 |
| `CloudWatch Dashboard` | FS 用 CW Dashboard 作成 | このパターンも Dashboard を作成するが、**OPS 固有メトリクス** (推奨数、コスト差分、Toil 削減) を追加 |
| `monitor-ontap-services` | EMS/SnapMirror/Aggregate 監視 + SNS | OPS1/OPS4 と部分的に重複。このパターンは Step Functions オーケストレーション + Bedrock AI + Human Review を追加 |
| `LUN-monitoring` | LUN メトリクス → CW | このパターンは NAS (NFS/SMB/S3AP) フォーカス。LUN は対象外。重複なし。 |

### [NetApp/FSx-ONTAP-monitoring](https://github.com/NetApp/FSx-ONTAP-monitoring)

`FSx-ONTAP-samples-scripts/Monitoring` の後継リポジトリ (2025年分離)。

| ツール | 機能 | このパターンとの関係 |
|--------|------|--------------|
| CloudWatch Alarms | FS/Volume/CPU 閾値アラーム | このパターン: 閾値超過 → AI 分析 → 推奨 → (Level 2) 自動実行 |
| Grafana Dashboards | Harvest + Grafana 可視化 | このパターン: CloudWatch ネイティブ (追加インフラ不要) + AI 推奨付き |
| NAS Audit Logs → CW | 監査ログ取り込み | このパターンは OPS4 (snapshot-lifecycle) で保持監査。ログ取り込み自体は対象外 |
| Admin Audit Logs → CW | 管理操作ログ取り込み | 監査証跡は CloudTrail + EMF で対応。重複なし |

### [NetApp/fsxn-monitoring-auto-resizing](https://github.com/NetApp/fsxn-monitoring-auto-resizing)

単一 Lambda による FSx for ONTAP の監視 + 自動リサイズ。

| 観点 | fsxn-monitoring-auto-resizing | このパターン (OPS1) |
|------|-------------------------------|---------------------|
| アーキテクチャ | 単一 Lambda + EventBridge | Step Functions + 複数 Lambda |
| 対象 | 1 FS (CFn) / 複数 FS (手動) | マルチ FS (パラメータリスト) |
| 判断 | 閾値超過 → 即リサイズ | 閾値超過 → 分析 → AI 推奨 → (承認後) リサイズ |
| 通知 | SES メール | SNS (メール/Slack/PagerDuty) |
| レポート | なし | JSON/HTML + CloudWatch Dashboard |
| AI 推奨 | なし | Bedrock Nova 自然言語推奨 |
| What-If | なし | コスト差分シミュレーション |
| DemoMode | なし | あり (ONTAP 実機不要) |
| Human Review | なし | Level 2 (承認フロー) |
| Change Calendar | なし | SSM Change Calendar 連携 |

---

## 2. AWS 公式ソリューション

### [FSxOntapDynamicStorageScaling](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/automate-storage-capacity-increase.html)

AWS 公式ドキュメントの CloudFormation テンプレート。

| 観点 | AWS 公式 | このパターン (OPS1) |
|------|---------|---------------------|
| 範囲 | SSD ストレージ容量のみ | 容量 + スループットティア + ボリュームレベル |
| 判断 | CW Alarm 閾値超過 → Lambda → FSx API | 多段分析 (CW + ONTAP REST) → AI 推奨 |
| 逆方向 | 拡張のみ (縮小不可) | 拡張 + 縮小推奨 |
| IaC | CloudFormation | SAM (CloudFormation 互換) |

### [Automate monitoring at scale (AWS Blog, 2024)](https://aws.amazon.com/blogs/storage/automate-monitoring-at-scale-for-amazon-fsx-for-netapp-ontap-volumes/)

AWS Storage Blog の横断モニタリング記事。

- 記事はアプローチを解説するが、デプロイ可能なテンプレートは提供していない
- このパターンは**デプロイ可能な SAM テンプレート**として完成させる
- 記事のアーキテクチャコンセプトは参考にする (CloudWatch カスタムメトリクス + Lambda)

### [Performance warnings and recommendations (FSx Console)](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/performance-insights-FSxN.html)

FSx コンソール上の組み込みパフォーマンス警告。

- Gen2 FS のみ利用可能
- 推奨は定型文 (カスタマイズ不可)
- このパターンの追加機能: Gen1 対応 + AI カスタム推奨 + プログラマティックアクセス

---

## 3. AWS 関連ブログ・ドキュメント (参照リンク)

| タイトル | URL | 関連 OPS |
|---------|-----|---------|
| Automate monitoring at scale for FSx for ONTAP volumes | [AWS Blog](https://aws.amazon.com/blogs/storage/automate-monitoring-at-scale-for-amazon-fsx-for-netapp-ontap-volumes/) | OPS1 |
| Simplifying FSx for ONTAP monitoring using Amazon Managed Grafana | [re:Post](https://repost.aws/articles/ARIXhwrbtiSomPpjaTd2Eq5g/simplifying-amazon-fsx-for-netapp-ontap-monitoring-using-amazon-managed-grafana) | OPS1, OPS6 |
| Monitoring FSx for ONTAP with Amazon CloudWatch | [AWS Docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/monitoring-cloudwatch.html) | 全 OPS |
| Performance warnings and recommendations | [AWS Docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/performance-insights-FSxN.html) | OPS1 |
| Creating a storage capacity utilization alarm | [AWS Docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/alarm-low-primary-storage.html) | OPS1 |
| Updating storage capacity dynamically | [AWS Docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/automate-storage-capacity-increase.html) | OPS1 |
| Volume data tiering | [AWS Docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/volume-data-tiering.html) | OPS3 |
| Best practices for enterprise deployments | [AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/fsx-ontap-enterprise-deployment/best-practices.html) | 全 OPS |
| How a customer reduced storage TCO by 28% | [AWS Blog](https://aws.amazon.com/blogs/storage/how-a-customer-reduced-storage-tco-by-28-with-amazon-fsx-for-netapp-ontap/) | OPS3, OPS5 |
| Cost-optimized file storage with FSx for ONTAP and Komprise | [AWS Blog](https://aws.amazon.com/jp/blogs/storage/cost-optimized-file-storage-with-amazon-fsx-for-netapp-ontap-and-komprise/) | OPS3, OPS5 |
| Monitoring FSx for ONTAP with Harvest and Grafana | [AWS Docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/monitoring-harvest-grafana.html) | OPS1, OPS6 |
| FSx for ONTAP second-generation file system metrics | [AWS Docs](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/so-file-system-metrics.html) | OPS1 |
| Monitoring FSx for ONTAP performance with CloudWatch | [NetApp Blog](https://community.netapp.com/t5/Tech-ONTAP-Blogs/Monitoring-Amazon-FSx-for-NetApp-ONTAP-performance-with-Amazon-CloudWatch/ba-p/462330) | OPS1, OPS6 |
| CloudWatch Dashboard for FSx for ONTAP | [NetApp Blog](https://community.netapp.com/t5/Tech-ONTAP-Blogs/Amazon-CloudWatch-dashboard-for-FSx-for-ONTAP/ba-p/457334) | OPS1 |
| Data discovery: what's on your FSx for ONTAP volumes | [aws-news.com](https://aws-news.com/article/2026-05-21-data-discovery-how-to-find-out-whats-on-your-amazon-fsx-for-netapp-ontap-volumes) | OPS5 |
| FSx for ONTAP metadata catalog (S3 Tables + Iceberg) | [GitHub](https://github.com/aws-samples/sample-fsx-ontap-metadata-catalog) | OPS5 |

---

## 4. 設計アプローチの比較

各ソリューションは異なるユースケースに適しています。組み合わせて使用することもできます。

| 観点 | NetApp fsxn-monitoring-auto-resizing | AWS FSxOntapDynamicStorageScaling | このプロジェクト (operations/) |
|------|--------------------------------------|----------------------------------|-------------------------------|
| 得意な領域 | 単一 FS の自動リサイズ | SSD 容量の自動拡張 | 横断分析 + 推奨 + 段階的自動化 |
| 運用スタイル | 閾値超過で即座にリサイズ | CloudWatch Alarm → Lambda → FSx API | レポート → (アラート) → (承認) → 実行 |
| 導入の容易さ | Lambda 1つで開始可能 | CFn テンプレート 1つ | SAM テンプレート (Step Functions 構成) |
| AI 推奨 | — | — | Bedrock Nova (オプション) |
| 適したフェーズ | 即座に auto-resize が必要な場合 | SSD 容量拡張のみ自動化したい場合 | 分析→推奨→承認フローを段階的に構築したい場合 |

**組み合わせパターン**:
- 既に `fsxn-monitoring-auto-resizing` で auto-resize を運用中 → このパターンを「分析 + 推奨レイヤー」として追加導入可能
- 既に `FSx-ONTAP-monitoring` の CloudWatch Dashboard を利用中 → OPS パターンのカスタムメトリクス (推奨数、コスト差分) を同じダッシュボードに追加可能

---

## 5. 実装時の注意事項

### 既存ソリューションとの共存

- 既に CloudWatch アラームや Dashboard がある環境では、このパターンは**追加レイヤー** (分析 + 推奨 + 自動化) として共存できます
- 既存のアラーム設定を変更する必要はありません

### ライセンス確認

- NetApp リポジトリは Apache 2.0 → コード参考は可能だがコピーは帰属表示が必要
- AWS 公式テンプレート (FSxOntapDynamicStorageScaling) の参照は自由だが、コード流用時は AWS ライセンスに従う
