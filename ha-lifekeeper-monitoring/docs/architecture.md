# HA LifeKeeper Monitoring — Architecture

## 概要

SIOS LifeKeeper で構成された高可用性 (HA) クラスタのログ・イベントを、Amazon FSx for NetApp ONTAP の S3 Access Points 経由で非侵入的に収集・分析するサーバーレスパターン。

Amazon Bedrock による根本原因分析 (Root Cause Analysis) とヘルススコアリングにより、フェイルオーバーイベントの迅速な原因特定と予兆検知を実現する。

---

## アーキテクチャ図

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  VPC (Multi-AZ)                                                             │
│                                                                             │
│  ┌─────────────────────┐         ┌─────────────────────┐                   │
│  │  AZ-a               │         │  AZ-c               │                   │
│  │                     │         │                     │                   │
│  │  ┌───────────────┐  │         │  ┌───────────────┐  │                   │
│  │  │ EC2 (Primary) │  │         │  │ EC2 (Standby) │  │                   │
│  │  │               │  │         │  │               │  │                   │
│  │  │ LifeKeeper    │  │ HA      │  │ LifeKeeper    │  │                   │
│  │  │ + SAP/Oracle  │◄─┼─Heartbeat─►│ + SAP/Oracle  │  │                   │
│  │  │ + VIP         │  │         │  │               │  │                   │
│  │  └───────┬───────┘  │         │  └───────┬───────┘  │                   │
│  │          │NFS/iSCSI  │         │          │NFS/iSCSI  │                   │
│  └──────────┼───────────┘         └──────────┼───────────┘                   │
│             │                                │                               │
│             ▼                                ▼                               │
│  ┌──────────────────────────────────────────────────────────────┐           │
│  │  Amazon FSx for NetApp ONTAP (Multi-AZ)                      │           │
│  │                                                              │           │
│  │  SVM: svm-ha-cluster                                         │           │
│  │  ├── vol_app_data    (SAP/Oracle データ — NFS/iSCSI)         │           │
│  │  ├── vol_app_logs    (アプリケーションログ — NFS)              │           │
│  │  └── vol_lk_logs     (LifeKeeper ログ — NFS)                 │           │
│  │          │                                                   │           │
│  │          │ S3 Access Point                                    │           │
│  └──────────┼───────────────────────────────────────────────────┘           │
│             │                                                               │
└─────────────┼───────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Serverless Analytics Layer (S3 AP 経由・非侵入型)                           │
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │  EventBridge │    │    Step      │    │   Amazon     │                   │
│  │  Scheduler   │───►│  Functions   │───►│   Bedrock    │                   │
│  │  (5 min)     │    │              │    │  (Nova Pro)  │                   │
│  └──────────────┘    │  Discovery   │    └──────────────┘                   │
│                      │      ↓       │                                       │
│  ┌──────────────┐    │  Processing  │    ┌──────────────┐                   │
│  │  FPolicy     │    │      ↓       │    │     SNS      │                   │
│  │  EventBridge │───►│   Report     │───►│  (Alerts)    │                   │
│  │  Rule        │    │              │    └──────────────┘                   │
│  └──────────────┘    └──────────────┘                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## コンポーネント詳細

### 1. HA クラスタ層 (SIOS LifeKeeper + EC2)

| コンポーネント | 役割 |
|---------------|------|
| EC2 Primary | アクティブノード（VIP 保持、アプリケーション稼働） |
| EC2 Standby | スタンバイノード（LifeKeeper 監視、フェイルオーバー待機） |
| SIOS LifeKeeper | HA クラスタリングソフトウェア（アプリ監視・VIP 制御・自動復旧） |
| Recovery Kit | アプリケーション固有の監視・起動・停止ロジック (SAP, Oracle, NFS, IP 等) |
| Communication Path | ノード間ハートビート (TCP/UDP) |

**LifeKeeper の役割**:
- アプリケーション/サービスの正常性監視 (Quick Check / Deep Check)
- 障害検知時の自動フェイルオーバー（VIP 移動 + アプリ起動）
- リソース依存関係に基づく起動/停止順序制御
- 通信パス冗長化によるスプリットブレイン防止

### 2. 共有ストレージ層 (FSx for ONTAP Multi-AZ)

| ボリューム | 用途 | プロトコル |
|-----------|------|-----------|
| vol_app_data | アプリケーションデータ (DB, ファイル) | NFS / iSCSI |
| vol_app_logs | アプリケーションログ | NFS |
| vol_lk_logs | LifeKeeper ログ・設定・イベント | NFS |

**FSx for ONTAP の役割**:
- Multi-AZ 配置により AZ 障害時もデータアクセス継続
- NFS/iSCSI マルチプロトコルで HA クラスタの共有ストレージとして機能
- Snapshot による一貫性バックアップ
- S3 Access Points でサーバーレス分析への非侵入的データ公開

**重要**: FSx for ONTAP Multi-AZ のストレージフェイルオーバーと LifeKeeper のアプリケーションフェイルオーバーは**独立したレイヤー**である。両方が連携することで、ストレージ層 + アプリケーション層の完全な HA を実現する。

**重要**: FSx for ONTAP Multi-AZ のストレージフェイルオーバーと LifeKeeper のアプリケーションフェイルオーバーは**独立したレイヤー**である。両方が連携することで、ストレージ層 + アプリケーション層の完全な HA を実現する。

### 3. サーバーレス分析層

| コンポーネント | 役割 |
|---------------|------|
| S3 Access Point | FSx for ONTAP ボリュームを S3 API で読み取り（非侵入） |
| EventBridge Scheduler | 定期ポーリング（5分間隔デフォルト） |
| FPolicy EventBridge Rule | ログ書き込みイベント駆動トリガー |
| Step Functions | ワークフローオーケストレーション |
| Discovery Lambda | LifeKeeper ログ検出・分類 |
| Processing Lambda | Bedrock による根本原因分析 + ヘルススコアリング |
| Report Lambda | Markdown レポート生成 + SNS アラート送信 |
| Amazon Bedrock | AI による障害分析・予兆検知 |
| SNS | フェイルオーバーアラート通知 |

---

## SIOS LifeKeeper とは

SIOS Technology 社が提供する Linux/Windows 向け HA クラスタリングソフトウェア。AWS 上で SAP、Oracle、SQL Server 等のミッションクリティカルなアプリケーションの高可用性を実現する。

### AWS における位置付け

- **AWS Partner Solution** として公式に提供 ([SIOS Protection Suite for Linux on AWS](https://aws.amazon.com/solutions/partners/sios-protection-suite/))
- AWS Marketplace から直接デプロイ可能
- CloudFormation Quick Start テンプレートが用意されている ([aws-ia.github.io](https://aws-ia.github.io/cfn-ps-sios-protection-suite/))
- SAP on AWS、Oracle on AWS のHA構成で広く採用

### 主な特徴

- **アプリケーション認識型**: Recovery Kit により SAP S/4HANA、Oracle DB、NFS、IP 等を直接監視
- **クロス AZ フェイルオーバー**: 単一 AWS リージョン内で 2 AZ 間のフェイルオーバー
- **VIP 管理**: Elastic IP / Secondary IP による仮想 IP フェイルオーバー
- **通信パス冗長**: 複数経路のハートビートでスプリットブレイン防止
- **99.99% 可用性実績**: Astro Malaysia 社事例（SAP + Oracle on AWS）

### FSx for ONTAP 共有ディスク対応 (LifeKeeper V10 以降)

LifeKeeper V10.0.1 以降、Amazon FSx for NetApp ONTAP を共有ディスクとして直接保護できるようになった（[SIOS bcblog 構築手順](https://bcblog.sios.jp/amazon-fsx-netapp-ontap-lifekeeper-shared-disk/)）。

従来、AWS 上の LifeKeeper クラスタでは **DataKeeper によるブロックレベルレプリケーション**のみがストレージ保護の選択肢だった。FSx for ONTAP 対応により、**共有ディスク構成**が可能となり、より柔軟なアーキテクチャ設計が実現する。

| プロトコル | 必要な Recovery Kit | 備考 |
|-----------|-------------------|------|
| iSCSI | DMMP (Device-Mapper-MultiPath) Recovery Kit | AWS 上の FSx for ONTAP 利用時に必須 |
| NFS | NAS Recovery Kit | 標準的な NFS 共有ディスク構成 |

**検証済み構成** (SIOS bcblog, 2026-05-08):
- EC2 インスタンス: t3.small × 2 (異なる AZ)
- OS: Red Hat Enterprise Linux 9.6.0
- LifeKeeper: v10.0.1
- FSx for ONTAP: 単一ファイルシステム内に iSCSI 用 / NFS 用ボリュームを作成
- 動作確認: スイッチオーバー後にプライマリ/スタンバイのアクセス権が正常に切り替わることを検証済み

### 参考資料

- **[SIOS LifeKeeper と Amazon FSx for NetApp ONTAP を活用したミッションクリティカルシステム向けの高可用性ソリューション (AWS JAPAN APN Blog)](https://aws.amazon.com/jp/blogs/psa/high-availability-solution-with-sios-lifekeeper-and-amazon-fsx-for-netapp-ontap/)** — LifeKeeper + FSx for ONTAP の組み合わせによる HA 構成の公式解説
- **[NetApp ONTAP と LifeKeeper による高可用性設計 (SIOS bcblog)](https://bcblog.sios.jp/netapp-ontap-lifekeeper-high-availability-design/)** — ONTAP + LifeKeeper のアーキテクチャ設計詳細
- **[Amazon FSx for NetApp ONTAP を LifeKeeper の共有ディスクとして利用 (SIOS bcblog)](https://bcblog.sios.jp/amazon-fsx-netapp-ontap-lifekeeper-shared-disk/)** — FSx for ONTAP を LifeKeeper 共有ディスクとして構成する手順
- [SIOS Protection Suite for Linux on AWS — Partner Solution](https://aws.amazon.com/solutions/partners/sios-protection-suite/)
- [SIOS LifeKeeper for Linux on AWS — Architecture Guide](https://aws-ia.github.io/cfn-ps-sios-protection-suite/)
- [Deploying highly available SAP systems using SIOS Protection Suite on AWS (AWS Blog, 2019)](https://aws.amazon.com/blogs/awsforsap/deploying-highly-available-sap-systems-using-sios-protection-suite-on-aws/)
- [Using SIOS to Protect your Critical Core on AWS (AWS Blog, 2020)](https://aws.amazon.com/blogs/awsforsap/using-sios-to-protect-your-critical-core-on-aws/)
- [SIOS LifeKeeper for Linux on AWS Marketplace](https://aws.amazon.com/marketplace/pp/prodview-5pxfcgrksorlo)
- [Astro Malaysia: 99.99% Uptime for SAP and Oracle with SIOS (2025)](https://www.globenewswire.com/news-release/2025/11/20/3191959/0/en/Astro-Malaysia-Ensures-99-99-Uptime-for-Critical-SAP-and-Oracle-Operations-with-SIOS-High-Availability-Solution.html)

---

## FSx for ONTAP + LifeKeeper の組み合わせの価値

### なぜこの組み合わせか

| レイヤー | 提供する HA | 担当 |
|---------|-----------|------|
| ストレージ | データ可用性・AZ 冗長・Snapshot | FSx for ONTAP Multi-AZ |
| アプリケーション | サービス可用性・VIP 制御・自動復旧 | SIOS LifeKeeper |
| 分析 | 非侵入的ログ収集・AI 障害分析 | S3 AP + サーバーレス |

従来の HA 構成では、ログ分析のためにクラスタノードに追加のエージェントを導入したり、NFS マウントを追加してログサーバーに転送する必要があった。これは HA 構成自体の複雑性を増し、潜在的な障害点を追加する。

**FSx for ONTAP S3 Access Points** を使うことで:

1. **非侵入**: EC2 ノードに追加ソフトウェア不要
2. **HA 影響なし**: ログ分析が HA クラスタの I/O に影響しない
3. **既存ログの再利用**: LifeKeeper が標準的に出力するログをそのまま分析
4. **リアルタイム**: FPolicy イベント駆動で即時検知可能
5. **AI 分析**: Bedrock による根本原因の自動特定

### 典型的なユースケース

1. **SAP on AWS + LifeKeeper**: SAP Central Instance の HA 構成で、SAP ログ + LifeKeeper イベントを統合分析
2. **Oracle on AWS + LifeKeeper**: Oracle DB のフェイルオーバー履歴とストレージ I/O パターンを相関分析
3. **カスタムアプリケーション**: 独自 Recovery Kit で保護されたアプリのヘルストレンド分析
4. **マルチクラスタ運用**: 複数の LifeKeeper クラスタの健全性を一元的にダッシュボード化

---

## データフロー

```
1. LifeKeeper がログを FSx for ONTAP ボリュームに書き込み
   (通常の NFS マウント経由 — HA 構成に変更なし)

2. EventBridge Scheduler が定期的に Step Functions を起動
   (または FPolicy が新規ログ書き込みを検出してイベント駆動)

3. Discovery Lambda が S3 AP 経由でログファイルを検出
   - フェイルオーバーイベント、ヘルスチェック、構成変更を分類
   - 重要度 (CRITICAL/HIGH/MEDIUM/LOW) を評価

4. Processing Lambda がログ内容を解析
   - LifeKeeper リソース状態遷移を検出 (ISP→OSF→ISS→ISP)
   - Bedrock で根本原因分析を実行
   - クラスタヘルススコアを算出 (0-100)

5. Report Lambda がレポートを生成
   - Markdown ヘルスレポートを S3 に保存
   - 重要度閾値を超えた場合に SNS アラートを送信
```

---

## セキュリティ設計

### IAM 最小権限

| Lambda | 権限 |
|--------|------|
| Discovery | S3 AP 読み取り (ListObjects, GetObject) のみ |
| Processing | S3 AP 読み取り + Bedrock InvokeModel + S3 出力書き込み |
| Report | S3 出力書き込み + SNS Publish |

### ネットワーク分離

- HA クラスタ (EC2 + LifeKeeper) は VPC Private Subnet に配置
- サーバーレス分析層は S3 AP (Internet Origin) 経由でアクセス
- 分析 Lambda は VPC 外（VPC Lambda ではない）— HA クラスタのネットワークに影響しない

### データ分類

- LifeKeeper ログ: INTERNAL（フェイルオーバーイベント、リソース状態、ノード名を含む）
- 分析結果: INTERNAL（クラスタ構成情報を含む可能性）
- SNS 通知: 最小限の情報のみ（クラスタ名、スコア、推奨アクション）

---

## 運用設計

### ヘルススコアの解釈

| スコア | レベル | 意味 |
|--------|--------|------|
| 90-100 | HEALTHY | 正常稼働。直近のフェイルオーバーなし |
| 70-89 | WARNING | 注意。軽微なイベントまたは通信パス一時障害 |
| 50-69 | DEGRADED | 劣化。フェイルオーバー発生または複数の通信パス障害 |
| 0-49 | CRITICAL | 危険。複数回のフェイルオーバーまたは深刻な障害 |

### アラートレベル設定

- **本番環境**: `FailoverAlertSeverity=HIGH` — フェイルオーバー発生時に即座に通知
- **検証環境**: `FailoverAlertSeverity=CRITICAL` — 重大障害のみ通知
- **開発環境**: アラート無効化推奨

### 監視頻度の目安

| 環境 | ScheduleExpression | 根拠 |
|------|-------------------|------|
| 本番 (SAP/Oracle) | rate(5 minutes) | フェイルオーバー検知の即時性 |
| 本番 (その他) | rate(15 minutes) | バランスの取れた監視 |
| 検証 | rate(1 hour) | コスト最適化 |
| 開発 | 手動実行 | 必要時のみ |

---

## コスト考慮事項

| コンポーネント | 月額目安 | 備考 |
|---------------|---------|------|
| S3 AP 読み取り | $0.01-0.10 | ログサイズに依存 |
| Lambda (3関数) | $0.50-5.00 | 実行回数・時間に依存 |
| Step Functions | $0.10-1.00 | 状態遷移数に依存 |
| Bedrock (Nova Pro) | $1.00-10.00 | フェイルオーバー分析回数に依存 |
| SNS | $0.01 | 通知回数に依存 |
| **合計** | **$2-20/月** | HA クラスタ本体のコストの 1% 未満 |

> **注意**: FSx for ONTAP ファイルシステム自体のコスト (Multi-AZ, 128+ MBps) は別途発生する。
> このパターンが追加するコストは分析層のみ。

---

## 制約事項

1. **LifeKeeper ログ形式**: 本パターンはキーワードベースの分類を行う。LifeKeeper のバージョンによりログ形式が異なる場合、分類ロジックの調整が必要
2. **リアルタイム性**: ポーリング間隔 (デフォルト 5 分) がフェイルオーバー検知の遅延となる。即時性が必要な場合は FPolicy イベント駆動 (EVENT_DRIVEN/HYBRID) を使用
3. **S3 AP 制約**: FSx for ONTAP S3 Access Points の標準制約が適用される（最大 5GB/オブジェクト、サポート操作に制限あり）
4. **Bedrock リージョン**: Bedrock モデルの利用可能リージョンに制約あり

---

## 関連パターン

- `sap-erp-adjacent/` — SAP IDoc/HULFT ファイル処理（LifeKeeper で保護された SAP 環境のデータ処理に適用可能）
- `event-driven-fpolicy/` — FPolicy イベント駆動パイプライン（LifeKeeper ログの即時検知に利用）
- `flexcache-anycast-dr/` — FlexCache DR パターン（マルチリージョン HA 構成の参考）
