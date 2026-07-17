# OPS4: Snapshot Lifecycle — スナップショット保持管理

🌐 **Language / 言語**: 日本語 | [English](README.en.md)

---

## 概要

FSx for ONTAP のスナップショットを日次で監査し、保持ポリシー準拠チェック・
Snapshot Policy ドリフト検出・期限切れスナップショットの Human Review ベース
クリーンアップを提供するサーバーレスパターン。

**主な機能**:
- 法定保持期間プリセット (FISC / HIPAA / NARA / CUSTOM)
- MinRetentionDays 安全装置 (若すぎるスナップショットは絶対に削除推奨しない)
- Snapshot Policy ドリフト検出 (期待数 vs 実数の乖離)
- Human Review 承認フロー (Level 2: 削除前に必ず人間が承認)
- AI 推奨サマリ (Bedrock Nova)

---

## アーキテクチャ

```
EventBridge Scheduler (daily)
    │
    ▼
Step Functions
    ├── 1. Collect Lambda (VPC)
    │       ├── ONTAP REST API → 全ボリュームのスナップショット一覧
    │       └── ONTAP REST API → Snapshot Policy 定義
    │
    ├── 2. Analyze Lambda
    │       ├── 保持ポリシー準拠チェック (MaxRetentionDays 超過 = expired)
    │       ├── MinRetentionDays 保護 (若いスナップショットは除外)
    │       ├── Snapshot Policy ドリフト検出
    │       └── Bedrock AI サマリ (optional)
    │
    └── 3. Report Lambda
            ├── S3 (JSON/HTML 監査レポート)
            ├── CloudWatch (RetentionCompliancePercent 等)
            └── [Level 1+] SNS アラート
```

---

## 保持ポリシープリセット

| プリセット | 保持日数 | 用途 | 根拠 |
|-----------|:-------:|------|------|
| `FISC` | 2,557 (7年) | 金融機関 | FISC 安全対策基準 |
| `HIPAA` | 2,192 (6年) | 医療機関 | HIPAA §164.530(j) |
| `NARA` | 10,950 (30年) | 政府・公文書 | National Archives 基準 |
| `CUSTOM` | (パラメータ指定) | 一般企業 | MaxRetentionDays で自由設定 |

> **重要**: プリセット選択時、保持期間**内**のスナップショットは絶対に削除推奨されません。

---

## クイックスタート

```bash
cd operations/snapshot-lifecycle
cp samconfig.toml.example samconfig.toml

# DemoMode
sam build && sam deploy --parameter-overrides \
  FileSystemIds=fs-demo01 DemoMode=true EnableBedrockSummary=false

# 本番 (CUSTOM 90日保持)
sam build && sam deploy --parameter-overrides \
  FileSystemIds=fs-0123456789abcdef0 \
  OntapSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:fsxn/admin-XXXXXX \
  AutomationLevel=1 RetentionPolicy=CUSTOM MaxRetentionDays=90 \
  NotificationEmail=ops-team@example.com \
  VpcSubnetIds=subnet-xxx,subnet-yyy VpcSecurityGroupIds=sg-xxx
```

---

## パラメータ

| パラメータ | デフォルト | 説明 |
|-----------|----------|------|
| `RetentionPolicy` | `CUSTOM` | 保持ポリシープリセット (FISC/HIPAA/NARA/CUSTOM) |
| `MaxRetentionDays` | `90` | 最大保持日数 (CUSTOM モード) |
| `MinRetentionDays` | `7` | 最小保持日数 (この期間内は絶対に削除推奨しない) |
| `SnapshotReserveWarningPercent` | `80` | スナップショット予約使用率の警告閾値 |
| `FileSystemIds` | (必須) | 監視対象 FS ID リスト |
| `OntapSecretArn` | `""` | fsxadmin 認証情報 |
| `AutomationLevel` | `0` | 0=レポート, 1=アラート, 2=Human Review+削除 |
| `DemoMode` | `false` | モックデータで実行 |
| `EnableBedrockSummary` | `true` | AI 推奨生成 |

---

## 出力

### CloudWatch カスタムメトリクス (Namespace: `FSxOps`)

| メトリクス | 単位 | 説明 |
|-----------|------|------|
| `ExpiredSnapshotCount` | Count | 期限切れスナップショット数 |
| `ExpiredSnapshotSizeGB` | Gigabytes | 期限切れスナップショットの合計サイズ |
| `PolicyDriftVolumeCount` | Count | ポリシードリフトが検出されたボリューム数 |
| `RetentionCompliancePercent` | Percent | 準拠率 (100% = 全スナップショットが保持期間内) |

### S3 監査レポート

```
s3://{stack-name}-reports-{account-id}/
  reports/2026/07/13/{fs-id}/
    ├── snapshot-audit.json
    └── snapshot-audit.html
```

---

## テスト

```bash
python3 -m pytest operations/snapshot-lifecycle/tests/ -v
make test-ops4
```

---

## Governance Note

**本パターンはスナップショットの削除を推奨することがありますが、以下の安全装置を備えています**:

1. **MinRetentionDays**: この期間内のスナップショットは、いかなる場合も削除推奨されません
2. **法定プリセット**: FISC/HIPAA/NARA 選択時は法定保持期間が自動適用されます
3. **Human Review**: `AutomationLevel=2` では削除前に必ず人間の承認が必要です
4. **監査証跡**: 全操作は CloudTrail + CloudWatch Logs に記録されます

> 規制業種で使用する場合は、必ず法務・コンプライアンス部門と `RetentionPolicy` の設定値を確認してください。

---

## 既存ソリューションとの関係

| ソリューション | 関係 |
|--------------|------|
| ONTAP Snapshot Policy (ネイティブ) | 当パターンは Policy の**準拠監査**を行う。Policy 自体の設定は ONTAP の機能。 |
| [NetApp/FSx-ONTAP-monitoring](https://github.com/NetApp/FSx-ONTAP-monitoring) | 監視 (アラーム) のみ。当パターンは保持準拠+ドリフト検出+AI推奨を追加。 |
| AWS Backup | バックアップのライフサイクル管理。当パターンは ONTAP ネイティブ Snapshot に特化。 |

---

## 関連ドキュメント

| ドキュメント | 内容 |
|------------|------|
| [operations/docs/metrics-mapping.md](../docs/metrics-mapping.md) | メトリクス対応表 |
| [operations/docs/ops-adoption-roadmap.md](../docs/ops-adoption-roadmap.md) | 導入ロードマップ |
| [operations/docs/existing-solutions-reference.md](../docs/existing-solutions-reference.md) | 既存ソリューション比較 |
