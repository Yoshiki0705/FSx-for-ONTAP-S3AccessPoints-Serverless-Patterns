# Enterprise Workload Examples

🌐 **Language / 言語**: [日本語](enterprise-workload-examples.md) | [English](enterprise-workload-examples.en.md)

## 概要

本リポジトリのパターンは AI/ML ユースケースに限定されません。FSx for ONTAP に保存されたあらゆるエンタープライズファイルデータに対して、S3 Access Points が AWS ネイティブサービスへの接続を提供します。

> **設計ポイント**: ファイルデータは FSx for ONTAP に残り続けます。S3 Access Points は「データを移動せずに AWS サービスと接続する」ためのブリッジです。既存の NFS/SMB アクセスは一切変更されません。

## エンタープライズワークロード例

### 1. SAP 周辺ファイルとエクスポートドキュメント

| 項目 | 内容 |
|------|------|
| **ファイル種別** | SAP IDoc エクスポート、ABAP レポート出力、Crystal Reports PDF、BW データ抽出 |
| **保存場所** | FSx for ONTAP (SAP アプリケーションサーバーから NFS/SMB マウント) |
| **S3 AP 活用** | エクスポートファイルの自動分類、Bedrock による要約生成、Athena でのクエリ分析 |
| **価値** | SAP データを移動せずに AI/分析サービスと連携。既存の SAP ファイルインターフェースを変更不要 |

**アーキテクチャパターン**:
```
SAP App Server → NFS → FSx ONTAP Volume
                              ↓ (S3 Access Point)
                        Lambda (GetObject) → Bedrock (分類/要約)
                                           → Athena (構造化分析)
                                           → S3 (分析結果保存)
```

### 2. EDI / HULFT ランディングゾーン

| 項目 | 内容 |
|------|------|
| **ファイル種別** | EDI (EDIFACT/X12) メッセージ、HULFT 転送ファイル、CSV/固定長データ |
| **保存場所** | FSx for ONTAP (HULFT/EDI ゲートウェイからの受信ディレクトリ) |
| **S3 AP 活用** | 受信ファイルの自動バリデーション、フォーマット変換、異常検知 |
| **価値** | 既存の EDI/HULFT インフラを変更せずに、受信データの自動処理パイプラインを構築 |

**アーキテクチャパターン**:
```
HULFT/EDI Gateway → SMB → FSx ONTAP Volume (/landing/)
                                ↓ (S3 Access Point + EventBridge Scheduler)
                          Step Functions
                            ├─→ Validation Lambda (フォーマットチェック)
                            ├─→ Transform Lambda (正規化)
                            └─→ Notification (異常時アラート)
```

### 3. 監査証跡とコンプライアンスレポート

| 項目 | 内容 |
|------|------|
| **ファイル種別** | 内部監査レポート (PDF)、コンプライアンス証跡、承認フロー記録 |
| **保存場所** | FSx for ONTAP (NTFS ACL による部門別アクセス制御) |
| **S3 AP 活用** | 定期的な完全性チェック、メタデータ抽出、保管期限管理 |
| **価値** | NTFS 権限を維持したまま、自動化された監査・コンプライアンスチェックを実現 |

**アーキテクチャパターン**:
```
Audit System → SMB (NTFS ACL) → FSx ONTAP Volume
                                       ↓ (S3 AP, Windows identity)
                                 Lambda (定期スキャン)
                                   ├─→ 完全性ハッシュ検証
                                   ├─→ 保管期限チェック
                                   └─→ SNS (期限切れアラート)
```

### 4. EC2 ベースの業務アプリケーションからのバッチ出力

| 項目 | 内容 |
|------|------|
| **ファイル種別** | バッチジョブ出力 (CSV/JSON/XML)、帳票 PDF、ログファイル |
| **保存場所** | FSx for ONTAP (EC2 アプリケーションサーバーから NFS マウント) |
| **S3 AP 活用** | バッチ出力の自動後処理、品質チェック、下流システムへの配信 |
| **価値** | バッチアプリケーションの出力先を変更せずに、サーバーレス後処理パイプラインを追加 |

**アーキテクチャパターン**:
```
EC2 Batch App → NFS → FSx ONTAP Volume (/batch-output/YYYYMMDD/)
                              ↓ (S3 AP + EventBridge Scheduler)
                        Step Functions (日次)
                          ├─→ Discovery (当日出力ファイル検出)
                          ├─→ Quality Check (件数・フォーマット検証)
                          ├─→ Transform (必要に応じて変換)
                          └─→ Delivery (下流システムへ配信)
```

### 5. スキャンドキュメントと規制対象記録

| 項目 | 内容 |
|------|------|
| **ファイル種別** | スキャン PDF/TIFF、契約書、医療記録、法的文書 |
| **保存場所** | FSx for ONTAP (スキャナーからの SMB 共有、長期保管) |
| **S3 AP 活用** | OCR テキスト抽出、自動分類、PII 検出、墨消し |
| **価値** | 紙文書のデジタル化後処理を自動化。原本は FSx に保管したまま、AI による分類・検索を実現 |

**アーキテクチャパターン**:
```
Scanner → SMB → FSx ONTAP Volume (/scanned-docs/)
                       ↓ (S3 AP)
                 Step Functions
                   ├─→ Textract (OCR) ⚠️ Cross-Region
                   ├─→ Comprehend (分類 + PII 検出)
                   ├─→ Bedrock (要約生成)
                   └─→ Output (メタデータ + 検索インデックス)
```

## 共通設計原則

### データは移動しない

```
┌─────────────────────────────────────────────────────────────┐
│  FSx for ONTAP Volume                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Enterprise File Data                               │    │
│  │  (NFS/SMB でアクセス可能 — 変更なし)                 │    │
│  └─────────────────────────────────────────────────────┘    │
│           │                                                 │
│           │ S3 Access Point (読み取り / 書き込み)            │
│           ▼                                                 │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  AWS Native Services                                │    │
│  │  • AI/ML (Bedrock, Textract, Comprehend)            │    │
│  │  • Analytics (Athena, Glue)                         │    │
│  │  • Automation (Step Functions, Lambda)              │    │
│  │  • Storage (S3 for results)                         │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 既存インフラへの影響ゼロ

- NFS/SMB マウントポイントは変更不要
- NTFS ACL / UNIX パーミッションはそのまま維持
- 既存のバックアップ・レプリケーション（SnapMirror）に影響なし
- アプリケーションコードの変更不要

### 段階的導入

1. **Phase 1**: S3 Access Point を作成し、読み取り専用でファイル一覧を取得
2. **Phase 2**: 特定ディレクトリに対して自動処理パイプラインを構築
3. **Phase 3**: イベント駆動（FPolicy）でリアルタイム処理を追加
4. **Phase 4**: 処理結果を同一ボリュームに書き戻し（PutObject）

## 本リポジトリとの対応

| エンタープライズワークロード | 最も近い UC パターン | 適用可能な共通モジュール |
|---------------------------|--------------------|-----------------------|
| SAP 周辺ファイル | UC1 (法務), UC6 (EDA) | Discovery Lambda, Bedrock Helper |
| EDI / HULFT | UC12 (物流 OCR), UC3 (製造) | S3AP Helper, Validation Lambda |
| 監査証跡 | UC1 (法務), UC16 (政府) | Lineage, S3 Object Lock |
| バッチ出力 | UC3 (製造), UC11 (小売) | Discovery Lambda, Output Writer |
| スキャンドキュメント | UC2 (金融 IDP), UC14 (保険) | Textract Helper, Comprehend Helper |

## 参考リンク

- [S3AP 二段階認可モデル](s3ap-authorization-model.md)
- [Trigger Mode Decision Guide](trigger-mode-decision-guide.md)
- [Deployment Profiles](deployment-profiles.md)
- [Output Destination Patterns](output-destination-patterns.md)
