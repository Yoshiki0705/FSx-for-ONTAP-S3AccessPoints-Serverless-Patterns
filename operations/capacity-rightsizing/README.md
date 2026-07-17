# OPS1: Capacity Rightsizing — 容量・スループット最適化

🌐 **Language / 言語**: 日本語 | [English](README.en.md)

---

## 概要

FSx for ONTAP のボリューム容量とスループットキャパシティを日次で監視し、
AI による推奨アクションと What-If コストシミュレーションを提供するサーバーレスパターン。

**特徴**:
- Bedrock Nova による自然言語アクション推奨
- What-If シミュレーション (ティア変更時のコスト差分を即座に試算)
- 段階的自動化 (Level 0: レポートのみ → Level 2: 承認ベース実行)
- マルチ FS 横断監視 (1スタックで複数ファイルシステム)
- Gen1/Gen2 自動判別
- DemoMode (ONTAP 実機不要のデモ実行)

---

## アーキテクチャ

```
EventBridge Scheduler (rate/cron)
    │
    ▼
Step Functions
    ├── 1. Collect Lambda (VPC)
    │       ├── ONTAP REST API → ボリューム容量/autosize
    │       └── CloudWatch → スループット/CPU/ストレージ使用率
    │
    ├── 2. Analyze Lambda
    │       ├── 閾値チェック (80%超 → upsize / 20%未満 → downsize)
    │       ├── スループットティア推奨
    │       ├── What-If シナリオ生成
    │       └── Bedrock Nova AI 推奨 (optional)
    │
    └── 3. Report Lambda
            ├── S3 (JSON/HTML レポート)
            ├── CloudWatch (カスタムメトリクス: FSxOps namespace)
            └── [Level 1+] SNS アラート
```

---

## クイックスタート

### DemoMode (ONTAP 実機不要)

```bash
cd operations/capacity-rightsizing
cp samconfig.toml.example samconfig.toml

# shared/ モジュールを Lambda 関数にコピー (初回 & shared/ 変更時に必要)
./build.sh

# ビルド & デプロイ
sam build
sam deploy --parameter-overrides \
  FileSystemIds=fs-demo01 \
  DemoMode=true \
  EnableBedrockSummary=false
```

### 本番デプロイ

```bash
# samconfig.toml を自環境に合わせて編集 (パラメータ取得方法は operations/README.md 参照)
cp samconfig.toml.example samconfig.toml

./build.sh && sam build
sam deploy
```

---

## パラメータ

| パラメータ | デフォルト | 説明 |
|-----------|----------|------|
| `FileSystemIds` | (必須) | 監視対象 FS ID リスト (カンマ区切り) |
| `OntapSecretArn` | `""` | fsxadmin 認証情報 (Secrets Manager ARN) |
| `AutomationLevel` | `0` | 0=レポート, 1=アラート, 2=承認実行, 3=全自動 |
| `ThresholdPercent` | `80` | 高利用率アラート閾値 (%) |
| `LowUtilizationThresholdPercent` | `20` | 低利用率検出閾値 (%) |
| `DemoMode` | `false` | デモモード (モックデータ使用) |
| `NotificationEmail` | `""` | アラート通知先 |
| `ScheduleExpression` | `rate(1 day)` | 実行スケジュール |
| `EnableBedrockSummary` | `true` | AI 推奨生成 |
| `ReportFormat` | `BOTH` | JSON / HTML / BOTH |
| `VpcSubnetIds` | `""` | ONTAP REST API アクセス用サブネット |
| `VpcSecurityGroupIds` | `""` | ONTAP REST API アクセス用 SG |
| `OutputDestination` | `STANDARD_S3` | 出力先 (STANDARD_S3 / FSXN_S3AP) |
| `S3AccessPointAlias` | `""` | S3 AP alias (FSXN_S3AP 時に必須) |

---

## 出力

### CloudWatch カスタムメトリクス (Namespace: `FSxOps`)

| メトリクス | 単位 | Dimensions |
|-----------|------|-----------|
| `AvgVolumeUtilizationPercent` | Percent | FileSystemId |
| `ThroughputUtilizationPercent` | Percent | FileSystemId |
| `RecommendationCount` | Count | FileSystemId |
| `MonthlyCostDeltaUSD` | None | FileSystemId |

### S3 レポート

```
s3://{stack-name}-reports-{account-id}/
  reports/2026/07/13/{fs-id}/
    ├── capacity-report.json
    └── capacity-report.html
```

### 推奨タイプ

| タイプ | トリガー条件 | アクション |
|-------|-------------|----------|
| `upsize` | ボリューム使用率 ≥ ThresholdPercent | autosize 有効化 or 容量拡張 |
| `downsize` | ボリューム使用率 ≤ LowUtilizationThresholdPercent + autosize 無効 | 容量縮小 or autosize(grow_shrink) |
| `tier_upgrade` | スループット利用率 ≥ ThresholdPercent | 次のスループットティアへ変更 |

---

## 関連ソリューションと組み合わせ

| ソリューション | 関係 |
|--------------|------|
| [AWS FSxOntapDynamicStorageScaling](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/automate-storage-capacity-increase.html) | SSD 容量の自動拡張に特化。このパターンはスループット + ボリュームレベル分析 + AI 推奨を追加する構成 |
| [NetApp/fsxn-monitoring-auto-resizing](https://github.com/NetApp/fsxn-monitoring-auto-resizing) | 即時リサイズに特化。このパターンは段階的自動化 (Level 0-3) のアプローチを提供 |
| [NetApp/FSx-ONTAP-monitoring](https://github.com/NetApp/FSx-ONTAP-monitoring) | CloudWatch アラーム + Dashboard 構築。このパターンは分析 + What-If + Human Review レイヤーとして追加可能 |
| [AWS Blog: Automate monitoring at scale](https://aws.amazon.com/blogs/storage/automate-monitoring-at-scale-for-amazon-fsx-for-netapp-ontap-volumes/) | 横断モニタリングのコンセプト記事。このパターンはデプロイ可能なテンプレートとして実装 |

> 上記ソリューションを既に導入済みの場合、このパターンは**追加レイヤー** (分析 + 推奨 + 自動化) として共存できます。

---

## テスト

```bash
# プロジェクトルートから実行
python3 -m pytest operations/capacity-rightsizing/tests/ -v

# または Makefile 経由
make test-ops1
```

---

## Governance Note

本パターンはコスト最適化・容量管理を目的としますが、
データ保持に関する法的要件 (FISC / HIPAA / NARA 等) を上書きするものではありません。

- `AutomationLevel=2` 以上での容量変更は **Human Review** (承認フロー) を経由します
- 変更禁止期間は SSM Change Calendar で制御可能です (Level 2/3)
- 全操作は CloudTrail + CloudWatch Logs に記録されます

---

## 関連ドキュメント

| ドキュメント | 内容 |
|------------|------|
| [operations/docs/metrics-mapping.md](../docs/metrics-mapping.md) | CloudWatch ↔ ONTAP REST 対応表 |
| [operations/docs/ops-adoption-roadmap.md](../docs/ops-adoption-roadmap.md) | 段階的導入ガイド |
| [operations/docs/existing-solutions-reference.md](../docs/existing-solutions-reference.md) | 既存ソリューション比較 |
| [operations/docs/slo-definitions.md](../docs/slo-definitions.md) | SLO/SLI 定義 |
