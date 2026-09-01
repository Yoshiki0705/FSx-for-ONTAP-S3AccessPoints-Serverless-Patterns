# dev.to シリーズ構成とタグ付けの規約

🌐 **Language / 言語**: 日本語 | [English](devto-series-cleanup-guide.en.md)

このリポジトリから公開している dev.to 記事のシリーズ名とタグを定義します。**シリーズ名は
完全一致で 1 文字も違えられません**（大文字小文字も区別されます）。違うとシリーズが分裂し、
読者はシリーズ内のナビゲーションを使えません。

## 分ける理由

S3 AP のサーバーレスパターン集とファイルポータルは、**読者が違います**。前者はデータ処理
パイプラインを設計する人、後者は利用者に Web UI を渡す人です。1 つのシリーズに混ぜると、
どちらの読者にとっても半分が無関係な記事になります。Permission-Aware RAG も同じ理由で
独立させています。

**言語ごとにもシリーズを分けます。** dev.to はシリーズ内の記事を公開日順に並べるだけなので、
日本語と英語を同じシリーズ名にすると交互に並び、どちらの読者も飛ばし読みを強いられます。

## シリーズ定義

| # | シリーズ名（完全一致） | 言語 | 対象 |
|---|---|---|---|
| 1 | `FSx for ONTAP S3 Access Points` | EN | S3 AP サーバーレスパターン集 |
| 2 | `FSx for ONTAP S3 AP サーバーレスパターン集` | JA | 同上 |
| 3 | `FSx for ONTAP File Portal` | EN | ファイルポータル（Amplify Gen2） |
| 4 | `FSx for ONTAP ファイルポータル` | JA | 同上 |
| 5 | `Permission-Aware RAG` | EN | Permission-Aware RAG |

ファイルポータルシリーズの記事構成は [ファイルポータル記事シリーズの計画](./devto-file-portal-series.md) にあります。

## タグの規約

dev.to のタグは**最大 4 個**で、グローバルな名前空間です。同じ製品を指すタグが記事ごとに
違うと、タグをフォローしている読者にシリーズの一部しか届きません。

### 現状の不整合（要修正）

公開済み記事で、同じ製品に対して 4 通りのタグが使われています。

| 使われているタグ | 記事数 |
|---|---|
| `amazonfsxfornetappontap` | 2 |
| `netapp` | 5 |
| `fsxforontap` | 1 |
| `fsxontap` | 1 |

### 規約

| 位置 | S3 AP シリーズ | ファイルポータルシリーズ | Permission-Aware RAG |
|---|---|---|---|
| 1 | `aws` | `aws` | `aws` |
| 2 | `serverless` | `amplify` | `rag` |
| 3 | `fsxforontap` | `fsxforontap` | `fsxforontap` |
| 4 | 記事固有（`bedrock`, `fpolicy`, `eventdriven` 等） | 記事固有（`react`, `graphql`, `cognito` 等） | 記事固有 |

製品タグは **`fsxforontap` に統一**します。`amazonfsxfornetappontap` は正式名称に忠実ですが
長く、`fsxontap` と `netapp` は他製品の記事と混ざります。

### 実施済み（2026-08-15、ファイルポータルの 3 本）

Part 1〜3 を S3 AP シリーズから移し、タグを規約に揃えました。

| 記事 | 変更前 | 変更後 |
|---|---|---|
| Part 1 | `series: FSx for ONTAP S3 Access Points` / `aws, netapp, serverless, storage` | `series: FSx for ONTAP File Portal` / `aws, amplify, fsxforontap, architecture` |
| Part 2 | 同上 / `aws, netapp, security, serverless` | 同上 / `aws, amplify, fsxforontap, security` |
| Part 3 | 同上 / `aws, bedrock, ai, netapp` | 同上 / `aws, amplify, fsxforontap, bedrock` |

**S3 AP シリーズ側の記事のタグは変更していません。** 上の不整合表はその時点の集計なので、
残りを揃えるかどうかを判断する前に現状を数え直してください（dev.to の Dashboard → Posts）。

> **公開済み記事の再タグ付けは著者の判断です。** タグを変えるとそのタグのフォロワーに
> 届く範囲が変わります。新規記事は上表に従い、既存記事を揃えるかどうかは
> リーチへの影響を見て決めてください。

## 手順（既存記事のシリーズを直す）

1. dev.to にサインインし、プロフィールアイコン → **Dashboard** → **Posts**
2. 対象記事の **Edit**
3. front matter の `series` を上の定義と完全一致させる

```yaml
---
title: "記事タイトル"
published: true
series: "FSx for ONTAP S3 Access Points"
tags: aws, serverless, fsxforontap, fpolicy
---
```

4. 保存
5. 記事ページでシリーズナビゲーションのウィジェットが出ることを確認

## 確認チェックリスト

- [ ] EN の S3 AP 記事はすべて `series: "FSx for ONTAP S3 Access Points"`
- [ ] JA の S3 AP 記事はすべて `series: "FSx for ONTAP S3 AP サーバーレスパターン集"`
- [ ] ファイルポータル記事は言語ごとに専用のシリーズ名
- [ ] Permission-Aware RAG 記事は `series: "Permission-Aware RAG"`
- [ ] 1 記事が 2 つのシリーズに属していない
- [ ] JA と EN が同じシリーズ名を共有していない
- [ ] 製品タグが `fsxforontap` に揃っている（または再タグ付けしない判断を記録した）
- [ ] シリーズナビゲーションが各記事に表示される

## 注意点

- シリーズウィジェットは同じシリーズ名の記事が 2 本以上になった時点で自動的に出ます
- シリーズ内の並び順は公開日昇順です。並べ替えたい場合は公開日を調整する必要があります
- 公開ページへの反映には数分かかることがあります
- リポジトリ内のドラフト（`docs/devto-ja/`、`docs/article-*.md`）の front matter も
  同じ定義に合わせてください。ドラフトと公開済みでシリーズ名がずれると、次の公開時に分裂します
