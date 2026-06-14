# サンプルデータ — AI 専用ボリューム シード

このディレクトリは、デモで FSx for ONTAP の **AI 専用ボリューム** に投入するシードデータです。
各サブフォルダーは業務ロール（部門）に対応し、業務ユーザーが Windows エクスプローラーで
ドラッグ&ドロップして維持する想定のファイルを格納しています。

> すべて **架空・マスク済み** のサンプルです。実在の顧客名・担当者名は含みません。

## ロール構成（Amazon Quick が想定する業務ロールに準拠）

| フォルダー | ロール | Amazon Quick での想定（参考） |
|-----------|--------|------------------------------|
| `sales/` | 営業 | Lead scoring / Sales forecasting / CRM（[/quick/sales/](https://aws.amazon.com/quick/sales/)） |
| `marketing/` | マーケティング | キャンペーン・ブランド・コンテンツ（Quick FAQ: marketing） |
| `finance/` | 財務・経理 | 予算・経費・フォーキャスト（Quick FAQ: finance） |
| `information-technology/` | 情報システム | インシデント対応・IT FAQ・セキュリティ（[/quick/information-technology/](https://aws.amazon.com/quick/information-technology/)） |
| `operations/` | オペレーション | SOP・業務プロセス（Quick FAQ: operations） |
| `legal/` | 法務 | 契約・コンプライアンス（Quick FAQ: legal） |
| `developers/` | 開発 | コーディング規約・オンボーディング（[/quick/developers/](https://aws.amazon.com/quick/developers/)） |

> 出典: Amazon Quick FAQ は「sales, marketing, IT, operations, finance, legal」を対象ロールとして明記。developers は専用ページあり。情報は time-sensitive であり、最新は公式サイトを参照。

## 使い方（デモ）

```
# AI 専用ボリューム（SMB 共有）へコピー（例）
\\fsxn-share\ai-knowledge\  ← この sample-data/ai-knowledge/ 配下を丸ごとコピー
```

各ロールのメンバーは、自分のフォルダー（`ai-knowledge/<role>/`）に NTFS ACL で書き込み権限を持ち、
ファイルの追加・更新・削除を行う。S3 Access Point 経由で Bedrock Knowledge Base が同期する。

## ディレクトリ

```
sample-data/ai-knowledge/
├── sales/
├── marketing/
├── finance/
├── information-technology/
├── operations/
├── legal/
└── developers/
```
