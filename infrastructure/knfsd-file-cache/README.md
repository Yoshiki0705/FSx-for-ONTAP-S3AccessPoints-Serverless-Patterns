# KNFSD File Cache — FSx for ONTAP NFS Read Acceleration

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md)

> **ステータス**: KNFSD File Cache は 2026 年 7 月時点で **Preview** です。
> **検証実績**: Cache miss 55ms → hit 2ms (**32x speedup**) — 2026-07-22, ap-northeast-1

## 概要

FSx for ONTAP の NFS エクスポートを KNFSD File Cache で透過的にキャッシュし、大規模コンピュートフリートに VPC 内速度で再提供するための検証・デプロイ環境です。

## アーキテクチャ

```
┌─── 既存環境 (このプロジェクト) ───────────────────────────┐
│                                                          │
│  FSx for ONTAP ◄── S3 AP ──► Lambda (serverless 処理)   │
│       ▲                                                  │
│       │ NFS mount (source)                               │
│       ▼                                                  │
│  KNFSD File Cache (EC2, このディレクトリでデプロイ)        │
│       ▲                                                  │
│       │ NFS re-export (cached, 32x speedup)              │
│       ▼                                                  │
│  Compute Fleet / テストクライアント                        │
└──────────────────────────────────────────────────────────┘
```

## クイックスタート (3 コマンド)

```bash
# 1. AMI ビルド + デプロイ (全自動、~40 分)
git clone https://github.com/awslabs/knfsd-file-cache.git /tmp/knfsd-file-cache
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# ↑ VPC ID, Subnet, FSx NFS IP を編集

# 2. デプロイ
./scripts/deploy.sh

# 3. 検証
./scripts/validate.sh
```

詳細手順は [デモガイド](docs/demo-guide.md) を参照。

## FSID Backend の選択

NFS re-export にはファイルハンドル (FSID) の一貫管理が必須です。用途に応じて選択:

| Option | 方式 | コスト | 用途 | tfvars 設定 |
|:---:|------|:---:|------|------|
| **D** (推奨) | SQLite on FSx for ONTAP | **$0** | テスト/PoC/単一ノード | `fsid_mode = "local"` |
| **A** | RDS PostgreSQL | ~$15/月 | マルチノード本番 | `fsid_mode = "external"` + `fsid_db_engine = "rds"` |
| **B** | Aurora Serverless v2 | ~$5-15/月 | 低コスト本番 | `fsid_mode = "external"` + `fsid_db_engine = "aurora-serverless"` |

> **Option D が推奨**: FSx for ONTAP の NFS マウント上に SQLite を配置。追加コスト $0 で FSx for ONTAP の 99.99% SLA による永続性を確保。

詳細は [FSID Backend 選択ガイド](docs/fsid-backend-options.md) を参照。

## ディレクトリ構成

```
infrastructure/knfsd-file-cache/
├── README.md / README.en.md          # 概要 + クイックスタート
├── terraform/
│   ├── main.tf                       # EC2 + IAM + SG + SSM (37 params)
│   ├── rds.tf                        # Option A/B: RDS or Aurora (条件作成)
│   ├── variables.tf                  # 全変数 (AWS CLI 確認コマンド付き)
│   ├── outputs.tf                    # IP, mount commands, FSID mode
│   ├── versions.tf                   # Provider constraints
│   └── terraform.tfvars.example      # 全 Option のコメント付き例
├── scripts/
│   ├── deploy.sh                     # One-command (AMI build + terraform apply)
│   ├── validate.sh                   # 5-check post-deploy validation
│   ├── benchmark-throughput.sh       # Cache miss/hit measurement
│   └── test-dual-path.sh            # KNFSD + S3 AP simultaneous access
├── docs/
│   ├── demo-guide.md / .en.md       # 実環境検証済み 7 ステップガイド
│   ├── troubleshooting.md / .en.md  # 実際に遭遇した問題 + 解決策
│   ├── fsid-backend-options.md / .en.md  # A/B/D 比較 + 選択フローチャート
│   └── verification-results.md      # テスト結果テンプレート
├── tests/                            # pytest integration tests
└── dashboards/                       # CloudWatch ダッシュボード JSON
```

## コスト

| フェーズ | リソース | コスト |
|---------|---------|--------|
| AMI ビルド | Spot c6g.16xlarge × 25分 | ~$0.30 |
| テスト (1時間) | m6gd.xlarge | ~$0.29 |
| **テスト合計** | | **< $1 (KNFSD 増分のみ。FSx for ONTAP 環境は別途必要)** |
| 本番 (月額) | im4gn.16xlarge × 24/7 | ~$4,190 |
| FSID DB (Option A) | RDS db.t4g.micro | ~$15/月 |
| FSID DB (Option B) | Aurora Serverless v2 | ~$5-15/月 |
| FSID DB (Option D) | SQLite on FSx for ONTAP | **$0** |

## セキュリティ考慮事項

| 項目 | リスク | 対策 |
|------|--------|------|
| NFS v3 通信暗号化なし | VPC 内平文通信 | VPC 内のみ使用。SG が VPC CIDR に制限 |
| NVMe キャッシュ暗号化 | 平文保存 | インスタンス終了でハードウェアワイプ |
| Public IP | NFS はインターネットに**非公開** | SG が VPC CIDR のみ許可。Public IP は EC2 API アクセス用 |
| FSID DB 認証情報 | Terraform state に含まれる | `sensitive = true` + remote state 推奨 |

## HA / 可用性

| 項目 | テスト | 本番 |
|------|:---:|:---:|
| Proxy 数 | 1 | 2+ (ASG) |
| FSID Backend | D (SQLite) | A or B (RDS/Aurora) |
| 負荷分散 | なし | NLB or DNS round-robin |
| AZ 配置 | Single AZ | FSx for ONTAP と同一 AZ |
| Proxy instance | On-Demand | On-Demand (Compute: Spot) |

## 関連ドキュメント

- [デモガイド (JA)](docs/demo-guide.md) | [(EN)](docs/demo-guide.en.md)
- [トラブルシューティング (JA)](docs/troubleshooting.md) | [(EN)](docs/troubleshooting.en.md)
- [FSID Backend 選択ガイド (JA)](docs/fsid-backend-options.md) | [(EN)](docs/fsid-backend-options.en.md)
- [KNFSD + S3 AP Dual-Path Architecture](../../docs/knfsd-s3ap-dual-path-architecture.md)
- [代替アーキテクチャ比較](../../docs/comparison-alternatives.md)
- [KNFSD File Cache 公式 GitHub](https://github.com/awslabs/knfsd-file-cache)
- [AWS Solutions Guidance](https://docs.aws.amazon.com/solutions/knfsd-file-cache-on-aws/)
