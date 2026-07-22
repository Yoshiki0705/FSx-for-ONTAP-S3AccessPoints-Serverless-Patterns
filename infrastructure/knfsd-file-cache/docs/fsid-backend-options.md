# KNFSD File Cache — FSID Backend 選択ガイド

🌐 **Language / 言語**: [日本語](fsid-backend-options.md) | [English](fsid-backend-options.en.md)

## 背景

KNFSD File Cache が NFS re-export を行う際、各 export path に一意の FSID (File System Identifier) を割り当てる必要があります。この FSID が不正確 or 不安定だとクライアントに `Stale file handle` エラーが発生します。

FSID を管理する方法は 4 つあります。このプロジェクトは FSx for ONTAP を前提とするため、FSx for ONTAP の高可用性を活かした構成を推奨します。

---

## 比較テーブル

| Option | FSID 管理 | バックエンド | 月額コスト | HA/永続性 | マルチノード | 適用シナリオ |
|:---:|------|------|:---:|:---:|:---:|------|
| **A** | knfsd-fsidd (Go) | RDS PostgreSQL (db.t4g.micro) | ~$15 | ✅ RDS Multi-AZ 可 | ✅ | 本番マルチノード |
| **B** | knfsd-fsidd (Go) | Aurora Serverless v2 (0.5 ACU) | ~$5-15 | ✅ Aurora HA | ✅ | 低コスト本番 |
| **C** | 公式 Terraform module | RDS (module 内蔵) | ~$15 | ✅ | ✅ | フル管理（推奨、パス問題あり） |
| **D** | kernel fsidd | SQLite on FSx for ONTAP (NFS) | **$0** | ✅ FSx for ONTAP HA | △ 単一ノード推奨 | テスト/PoC/単一ノード本番 |

---

## Option A: RDS PostgreSQL

```
KNFSD Proxy → knfsd-fsidd (Go) → RDS PostgreSQL (db.t4g.micro)
```

- 公式 `deployment/database/` module をデプロイ
- `FSID_MODE=external`
- IAM 認証対応
- マルチノード対応（複数 proxy が同一 DB を参照）

**デプロイ**:
```bash
# 1. database module
cd /tmp/knfsd-file-cache/deployment/database
terraform apply

# 2. KNFSD cluster (FSID_DATABASE_CONFIG で DB 接続先を指定)
```

---

## Option B: Aurora Serverless v2

```
KNFSD Proxy → knfsd-fsidd (Go) → Aurora Serverless v2 (PostgreSQL)
```

- Option A と同じ接続方式だが、Aurora Serverless でコスト最適化
- アイドル時 0.5 ACU (~$0.06/hr)
- スパイク時に自動スケール
- `FSID_DATABASE_DEPLOY=false` + 自前 Aurora をデプロイ

**メリット**: 書込み極低頻度の FSID テーブルに Full RDS は過剰。Serverless v2 ならアイドルコスト最小。

---

## Option C: 公式 Terraform Module (フルセット)

```
公式 terraform-module-knfsd が全て管理
  ├── KNFSD ASG
  ├── RDS PostgreSQL (database sub-module)
  ├── Security Groups
  ├── IAM
  ├── CloudWatch Dashboard
  └── NLB / DNS round-robin
```

- 最も完成度が高い
- **ただし**: ローカルパス参照の Terraform 問題 (`module.fsid_database` のパス) により、remote source としての利用に制限あり (2026-07 時点)
- 回避策: `git clone` + `examples/fsx-netapp/` をベースにローカル実行

---

## Option D: SQLite on FSx for ONTAP (推奨 — PoC/単一ノード)

```
KNFSD Proxy → kernel fsidd → SQLite on /srv/nfs/vol1/.knfsd/fsids.sqlite
                                            ↑
                                    FSx for ONTAP (NFS mount)
```

- `FSID_MODE=local`
- Linux カーネル付属の `fsidd` サービスを利用
- SQLite ファイルを FSx for ONTAP のボリューム上に配置
- **コスト追加: $0** (FSx for ONTAP は既存)
- FSx for ONTAP の可用性 (99.99% SLA) で SQLite の永続性を確保
- プロキシ置換後も同じ FSID マッピングを維持

**設定**:
```ini
# /etc/nfs.conf (KNFSD AMI に既存)
[reexport]
sqlitedb=/srv/nfs/vol1/.knfsd/fsids.sqlite
backend_plugin=/lib/libnfsreexport_backends/sqlite.so
```

**Terraform 変数**:
```hcl
# terraform.tfvars
fsid_mode = "local"
# proxy-startup.sh がソースマウント完了後に fsidd を起動
# SQLite パスはマウント先の NFS 上 → FSx for ONTAP に永続保存
```

**起動順序** (proxy-startup.sh が自動管理):
1. FSx for ONTAP を NFS mount (`/srv/nfs/vol1/`)
2. SQLite ディレクトリ確認/作成 (`/srv/nfs/vol1/.knfsd/`)
3. fsidd 起動 (SQLite を参照)
4. NFS re-export 開始
5. クライアントがマウント可能に

**制限事項**:
- SQLite は同時書込みに弱い → マルチノードで同時に新 export を追加する場合は A/B を選択
- ソース FSx for ONTAP が unreachable → fsidd も動作不能 (ソースが不達ならキャッシュ自体が無意味なので実害なし)
- SQLite パスのカスタマイズには `/etc/nfs.conf` の修正が必要 (user_data or AMI カスタム)

---

## 選択フローチャート

```
マルチノード (2+ proxy) ?
├── Yes → Option A or B (RDS/Aurora)
│         ├── コスト最小 → B (Aurora Serverless v2)
│         └── シンプルさ優先 → A (RDS t4g.micro)
│
└── No (単一ノード)
    ├── 本番? → Option D (SQLite on FSx for ONTAP)
    │           + FSx for ONTAP の HA で十分な永続性
    └── テスト? → Option D (最もシンプル、$0 追加)
```

---

## 次回テスト計画

Option D (SQLite on FSx for ONTAP) を以下の手順で検証:

1. `FSID_MODE=local` を SSM パラメータに設定
2. `/etc/nfs.conf` の `sqlitedb` パスを `/srv/nfs/vol1/.knfsd/fsids.sqlite` に変更 (user_data で)
3. proxy-startup.sh 実行 → fsidd が起動することを確認
4. フレッシュクライアントから mount → stale handle が発生しないことを確認
5. S3 AP write → NFS read (Dual-Path E2E) が動作することを確認

---

## 関連情報

- KNFSD ソース: `/etc/nfs.conf` の `[reexport]` セクション
- kernel fsidd: Linux 5.16+ で導入、7.1.3-knfsd で利用可能
- SQLite スキーマ: FSID auto-increment + path unique
- knfsd-fsidd (Go): PostgreSQL (pgx) のみ対応、DynamoDB/SQLite は未対応
