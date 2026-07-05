# HA LifeKeeper Monitoring — FSx for ONTAP S3 AP Pattern

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 概要

**SIOS LifeKeeper** で構成された高可用性 (HA) クラスタのログ・フェイルオーバーイベントを、**Amazon FSx for NetApp ONTAP** の S3 Access Points 経由で非侵入的に収集・分析するサーバーレスパターン。

Amazon Bedrock (Nova Pro) による**根本原因分析 (Root Cause Analysis)** と**クラスタヘルススコアリング**により、フェイルオーバーの迅速な原因特定と予兆検知を実現する。

---

## 想定シナリオ

エンタープライズ環境で SAP、Oracle、基幹業務アプリケーションを SIOS LifeKeeper で HA 保護し、共有ストレージとして FSx for ONTAP Multi-AZ を利用している。

**課題**:
- フェイルオーバー発生時の根本原因特定に時間がかかる
- LifeKeeper ログの分析は手動作業が多く、属人化している
- HA クラスタノードに監視エージェントを追加すると障害点が増える
- ストレージ層 (FSx for ONTAP) とアプリケーション層 (LifeKeeper) の障害切り分けが困難

**解決策**:
FSx for ONTAP S3 Access Points を使い、LifeKeeper が書き込むログを**非侵入的に**サーバーレス分析パイプラインで処理。AI による自動分析で運用負荷を軽減する。

---

## SIOS LifeKeeper + FSx for ONTAP の組み合わせ

### アーキテクチャの位置付け

| レイヤー | 担当 | HA 提供範囲 |
|---------|------|------------|
| ストレージ | FSx for ONTAP Multi-AZ | データ可用性・AZ 冗長・自動フェイルオーバー |
| アプリケーション | SIOS LifeKeeper | VIP 制御・サービス監視・自動復旧 |
| 分析 (本パターン) | S3 AP + サーバーレス + Bedrock | 非侵入型ログ分析・AI 根本原因分析 |

### SIOS LifeKeeper とは

SIOS Technology 社が提供する Linux/Windows 向け HA クラスタリングソフトウェア。AWS 上でミッションクリティカルなアプリケーションの高可用性を実現する。

**主な特徴**:
- アプリケーション認識型の Recovery Kit（SAP S/4HANA、Oracle、NFS、IP 等を直接監視）
- クロス AZ フェイルオーバー（単一リージョン内 2 AZ）
- VIP 管理（Elastic IP / Secondary IP）
- 通信パス冗長化によるスプリットブレイン防止
- AWS Partner Solution として公式提供

**実績**: Astro Malaysia 社が SAP + Oracle on AWS 環境で SIOS LifeKeeper を採用し、99.99% の可用性を実現。

### FSx for ONTAP 共有ディスク対応 (V10 以降)

LifeKeeper V10.0.1 以降、FSx for ONTAP を共有ディスクとして直接保護可能になった。従来は DataKeeper（ブロックレプリケーション）のみだったが、共有ディスク構成が追加され、よりシンプルな HA 構成が実現する。

| プロトコル | 必要な Recovery Kit | 備考 |
|-----------|-------------------|------|
| iSCSI | DMMP Recovery Kit | AWS 上の FSx for ONTAP 利用時に必須 |
| NFS | NAS Recovery Kit | 標準的な NFS 共有ディスク構成 |

> SIOS bcblog の検証記事 (2026-05-08) では、RHEL 9.6 + LifeKeeper v10.0.1 + FSx for ONTAP (iSCSI/NFS) の構成でスイッチオーバーが正常に動作することが確認されている。

### FSx for ONTAP がもたらす価値

- **Multi-AZ 共有ストレージ**: LifeKeeper の両ノードから NFS/iSCSI でアクセス可能
- **自動ストレージフェイルオーバー**: ストレージ層の AZ 障害を自動で処理
- **Snapshot**: フェイルオーバー前後のデータ状態を保全
- **S3 Access Points**: ログ分析のための非侵入的データアクセス経路
- **マルチプロトコル**: SMB + NFS + iSCSI + S3 API を単一ボリュームから提供、データの二重持ちを回避
- **クラウドネイティブ**: AWS マネジメントコンソールから直接利用開始可能（別途ライセンス不要）

> 「データをS3にコピーして利用するのではなく、FSx for ONTAP上のデータをそのままS3 API経由で活用できる点が大きなメリット」 — [SIOS bcblog インタビュー記事](https://bcblog.sios.jp/netapp-ontap-lifekeeper-high-availability-design/) より（Content was rephrased for compliance with licensing restrictions）

### 公開参考資料

| 資料 | 発行元 | URL |
|------|--------|-----|
| SIOS LifeKeeper と Amazon FSx for NetApp ONTAP を活用した高可用性ソリューション | AWS JAPAN APN Blog | https://aws.amazon.com/jp/blogs/psa/high-availability-solution-with-sios-lifekeeper-and-amazon-fsx-for-netapp-ontap/ |
| NetApp ONTAP と LifeKeeper による高可用性設計 | SIOS Technology (bcblog) | https://bcblog.sios.jp/netapp-ontap-lifekeeper-high-availability-design/ |
| Amazon FSx for NetApp ONTAP を LifeKeeper の共有ディスクとして利用 | SIOS Technology (bcblog) | https://bcblog.sios.jp/amazon-fsx-netapp-ontap-lifekeeper-shared-disk/ |
| SIOS Protection Suite for Linux on AWS | AWS Partner Solutions | https://aws.amazon.com/solutions/partners/sios-protection-suite/ |
| LifeKeeper for Linux — Architecture Guide | AWS Quick Start | https://aws-ia.github.io/cfn-ps-sios-protection-suite/ |
| Deploying HA SAP with SIOS on AWS | AWS Blog (2019) | https://aws.amazon.com/blogs/awsforsap/deploying-highly-available-sap-systems-using-sios-protection-suite-on-aws/ |
| Using SIOS to Protect your Critical Core on AWS | AWS Blog (2020) | https://aws.amazon.com/blogs/awsforsap/using-sios-to-protect-your-critical-core-on-aws/ |
| SQL Server HA with FSx for ONTAP | AWS Blog (2022) | https://aws.amazon.com/blogs/modernizing-with-aws/sql-server-high-availability-amazon-fsx-for-netapp-ontap/ |
| Oracle HA with FSx for ONTAP | AWS Blog (2025) | https://aws.amazon.com/blogs/architecture/building-highly-available-oracle-databases-with-amazon-fsx-for-netapp-ontap/ |
| Astro Malaysia 99.99% Uptime | GlobeNewsWire (2025) | https://www.globenewswire.com/news-release/2025/11/20/3191959/0/en/ |
| LifeKeeper for Linux (AWS Marketplace) | AWS Marketplace | https://aws.amazon.com/marketplace/pp/prodview-5pxfcgrksorlo |

---

## 機能

### Discovery Lambda
- FSx for ONTAP S3 AP 経由で LifeKeeper ログファイルを検出
- フェイルオーバーイベント / ヘルスチェック / 構成変更 / Recovery Kit ログに分類
- 重要度 (CRITICAL / HIGH / MEDIUM / LOW) を自動評価

### Processing Lambda
- LifeKeeper リソース状態遷移を検出 (ISP→OSF, ISS→ISP 等)
- Bedrock (Nova Pro) による根本原因分析
- クラスタヘルススコア算出 (0-100 点)
- ストレージ層 vs アプリケーション層の障害切り分け

### Report Lambda
- Markdown ヘルスレポート生成
- 重要度閾値に基づく SNS フェイルオーバーアラート
- LifeKeeper コマンド (`lcdstatus`, 通信パス確認) の推奨アクション付き

---

## デプロイ

### 前提条件

- AWS SAM CLI
- Python 3.12
- FSx for ONTAP ファイルシステム + S3 Access Point（DemoMode=true の場合は不要）
- Bedrock モデルアクセス有効化 (Amazon Nova Pro)

### クイックデプロイ

```bash
# DemoMode でデプロイ (FSx for ONTAP 不要)
# 前提: AWS SAM CLI が必要です。sam build がコードと共有レイヤーを自動でパッケージングします。
sam build
sam deploy --guided \
  --parameter-overrides \
    DemoMode=true \
    S3AccessPointAlias=your-demo-bucket \
    OutputBucketName=your-output-bucket \
    NotificationEmail=your@email.com
```

> **注意**: `template.yaml` は SAM CLI（`sam build` + `sam deploy`）で使用します。
> `aws cloudformation deploy` コマンドで直接デプロイする場合は `template-deploy.yaml` を使用してください（Lambda zip ファイルの事前パッケージングと S3 アップロードが必要です）。

### 本番デプロイ

```bash
# 前提: AWS SAM CLI が必要です。sam build がコードと共有レイヤーを自動でパッケージングします。
sam build
sam deploy --guided \
  --parameter-overrides \
    DemoMode=false \
    S3AccessPointAlias=your-fsxn-s3ap-alias-s3alias \
    OutputBucketName=your-output-bucket \
    NotificationEmail=ops-team@company.com \
    OntapSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ontap-creds-XXXXXX \
    ScheduleExpression="rate(5 minutes)" \
    FailoverAlertSeverity=HIGH \
    ClusterName=prod-sap-cluster \
    TriggerMode=HYBRID
```

### パラメータ

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| S3AccessPointAlias | (必須) | FSx for ONTAP S3 AP エイリアス |
| DemoMode | false | デモモード有効化 |
| ScheduleExpression | rate(5 minutes) | 監視間隔 |
| TriggerMode | POLLING | POLLING / EVENT_DRIVEN / HYBRID |
| BedrockModelId | apac.amazon.nova-pro-v1:0 | 分析用 Bedrock モデル |
| FailoverAlertSeverity | CRITICAL | SNS アラート最低重要度 |
| ClusterName | lifekeeper-cluster | LifeKeeper クラスタ名 |
| OutputDestination | STANDARD_S3 | レポート出力先 |
| LogRetentionInDays | 90 | CloudWatch Logs 保持期間 |

---

## テスト

```bash
# ユニットテスト
python3 -m pytest solutions/ha/lifekeeper-monitoring/tests/ -v

# DemoMode でのエンドツーエンドテスト
# (事前にデモ用 S3 バケットにサンプルログを配置)
aws stepfunctions start-execution \
  --state-machine-arn <StateMachineArn> \
  --input '{"trigger": "manual", "cluster_name": "demo-cluster"}'
```

---

## ヘルススコア

| スコア | レベル | 意味 | 推奨アクション |
|--------|--------|------|---------------|
| 90-100 | HEALTHY | 正常 | 定期レポート確認 |
| 70-89 | WARNING | 注意 | 通信パス・ストレージ I/O 確認 |
| 50-69 | DEGRADED | 劣化 | LifeKeeper GUI/CLI で状態確認、FSx for ONTAP モニタリング |
| 0-49 | CRITICAL | 危険 | 即時対応。`lcdstatus` + ONTAP 管理 CLI で状態確認 |

---

## ディレクトリ構成

```
solutions/ha/lifekeeper-monitoring/
├── template.yaml              # SAM テンプレート
├── samconfig.toml.example     # デプロイ設定例
├── README.md                  # 本ドキュメント (日本語)
├── README.en.md               # English README + Success Metrics
├── functions/
│   ├── discovery/
│   │   └── handler.py         # LifeKeeper ログ検出
│   ├── processing/
│   │   └── handler.py         # Bedrock 根本原因分析
│   └── report/
│       └── handler.py         # レポート生成・アラート
├── statemachine/
│   └── workflow.asl.json      # Step Functions 定義
├── docs/
│   ├── architecture.md        # アーキテクチャ詳細
│   └── demo-guide.md          # デモガイド (DemoMode)
└── tests/
    ├── conftest.py
    └── test_discovery.py      # ユニットテスト
```

---

## 関連パターン

| パターン | 関連性 |
|---------|--------|
| `solutions/sap/erp-adjacent/` | LifeKeeper で保護された SAP 環境の IDoc/バッチ処理 |
| `solutions/event-driven/fpolicy/` | FPolicy イベント駆動による即時ログ検知 |
| `solutions/flexcache/anycast-dr/` | マルチリージョン DR 構成の参考 |

---

## Governance Note

本パターンは HA クラスタの**運用監視補助**を目的としており、以下の点に注意:

- AI による分析結果は運用判断の**参考情報**であり、自動的なフェイルオーバー制御やリカバリ操作は行わない
- LifeKeeper の構成変更は必ず LifeKeeper GUI/CLI から実施すること
- フェイルオーバー判断は LifeKeeper 自身のヘルスチェック機構に委ねること
- 本パターンは **Human-in-the-loop** を前提とした設計

---

## Performance Considerations

- **監視間隔**: 5 分間隔では最大 5 分の検知遅延が発生する。即時性が必要な場合は `TriggerMode=HYBRID` で FPolicy イベント駆動を併用
- **ログサイズ**: 大量のログファイルがある場合、`MaxFilesPerExecution` でバッチサイズを制御
- **Bedrock コスト**: フェイルオーバーが頻発する環境では Bedrock 呼び出しコストに注意。`FailoverAlertSeverity` で分析対象を絞る
- **S3 AP スループット**: FSx for ONTAP S3 AP はファイルシステム全体の帯域を共有。大量のログ読み取りが業務 I/O に影響しないよう、Snapshot ベースの読み取りも検討

---

## License

MIT
