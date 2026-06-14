# UC30: Lake Formation タグベースアクセス制御（LF-TBAC）でロール別データ可視性

UC30 の構造化データ（Quick Sight / Athena）に対し、**ロール別のデータ可視性**を
Lake Formation のタグベースアクセス制御（LF-TBAC）で実現する設計ノート。

> 本書は技術ガイダンスであり、法的・コンプライアンス助言ではありません。

## 背景

- 当検証アカウントは Lake Formation がデータカタログを統制（Athena 実行ロールに LF 権限が必要）
- 単純な IAM/Glue 権限では足りず、**LF 権限**（DESCRIBE/SELECT）が前提
- ロール（sales/finance/it/...）ごとにアクセスできるテーブル/列を分けたい場合、LF-TBAC が有効

## 設計

### 1. LF-Tag の定義

```bash
aws lakeformation create-lf-tag --tag-key role \
  --tag-values sales marketing finance information-technology operations legal developers
aws lakeformation create-lf-tag --tag-key classification \
  --tag-values public internal confidential
```

### 2. テーブルへのタグ付与

```bash
# 例: sales_pipeline テーブルに role=sales を付与
aws lakeformation add-lf-tags-to-resource \
  --resource '{"Table":{"DatabaseName":"quick_workspace_db","Name":"sales_pipeline"}}' \
  --lf-tags '[{"TagKey":"role","TagValues":["sales"]}]'
```

### 3. ロール（プリンシパル）への LF-Tag 付き権限付与

```bash
# 例: 営業ロールのプリンシパルに role=sales のテーブルへ SELECT を許可
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier=arn:aws:iam::<acct>:role/<sales-role> \
  --resource '{"LFTagPolicy":{"ResourceType":"TABLE","Expression":[{"TagKey":"role","TagValues":["sales"]}]}}' \
  --permissions SELECT DESCRIBE
```

### 4. 列レベル制御（任意）

機密列（例: `amount_jpy`）を `classification=confidential` でタグ付けし、
特定ロールのみ列 SELECT を許可することで、列単位の可視性制御も可能。

## Quick Sight との関係

- Quick Sight のデータセットは Athena 経由で LF 統制下のテーブルを参照
- Quick Sight 側の **行レベルセキュリティ（RLS）** と LF-TBAC は**多層防御**として併用できる
  - LF-TBAC: カタログ/テーブル/列レベル（データ基盤側）
  - Quick RLS: ダッシュボードの行可視性（BI 側）

## 運用上の注意

- LF-Tag 設計はロール体系（本UCの7ロール）と整合させる
- タグ付与・権限付与は IaC 化（再現性・監査性）
- 付与状況は定期棚卸し（最小権限、未使用権限の除去）

> 本UCの検証では Athena 実行ロールへ DB DESCRIBE / テーブル SELECT・DESCRIBE を直接付与（簡易構成）。
> 本番でロール別可視性が必要な場合に LF-TBAC を採用する。
