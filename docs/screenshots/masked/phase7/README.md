# Phase 7 スクリーンショット（UC15 / UC16 / UC17）

Public Sector ユースケースの **UI/UX 画面のみ** を対象とする。Step Functions の
ワークフローグラフ、CloudFormation スタック画面、CloudWatch Logs 等の
**技術者向け画面は対象外**。

Public Sector の一般職員（FOIA 担当者、都市計画担当者、衛星画像アナリスト等）が
日常業務で実際に見る画面を掲載する。

## 期待されるファイル一覧

### UC15: Defense / Satellite Imagery

| ファイル名 | 内容 | 撮影箇所 |
|-----------|------|---------|
| `phase7-uc15-s3-satellite-uploaded.png` | 衛星画像の配置確認 | S3 コンソール（AP alias 経由） |
| `phase7-uc15-s3-output-bucket.png` | 解析結果の俯瞰 | S3 コンソール（detections / enriched / tiles） |
| `phase7-uc15-sns-alert-email.png` | 変化検出アラートメール | メールクライアント |
| `phase7-uc15-detections-json.png` | 検出結果 JSON のプレビュー | S3 オブジェクトプレビュー |

### UC16: Government Archives / FOIA

| ファイル名 | 内容 | 撮影箇所 |
|-----------|------|---------|
| `phase7-uc16-s3-archives-uploaded.png` | 公文書の配置確認 | S3 コンソール |
| `phase7-uc16-redacted-text-preview.png` | 墨消し済み文書の可視化（`[REDACTED]` マーカー） | S3 オブジェクトプレビュー |
| `phase7-uc16-redaction-metadata-json.png` | 墨消しメタデータ sidecar | S3 オブジェクトプレビュー |
| `phase7-uc16-foia-reminder-email.png` | FOIA 期限リマインダーメール | メールクライアント |
| `phase7-uc16-dynamodb-retention.png` | NARA GRS 保存スケジュール | DynamoDB Explorer |

### UC17: Smart City / Geospatial

| ファイル名 | 内容 | 撮影箇所 |
|-----------|------|---------|
| `phase7-uc17-s3-gis-uploaded.png` | GIS データの配置確認 | S3 コンソール |
| `phase7-uc17-bedrock-report.png` | Bedrock 生成の日本語都市計画レポート | S3 オブジェクトプレビュー or Markdown ビューア |
| `phase7-uc17-risk-map-json.png` | 災害リスクマップ（洪水 / 地震 / 土砂） | S3 オブジェクトプレビュー |
| `phase7-uc17-landuse-distribution.png` | 土地利用分布 JSON | S3 オブジェクトプレビュー |
| `phase7-uc17-dynamodb-landuse-history.png` | 時系列土地利用履歴 | DynamoDB Explorer |

## 撮影時の注意事項

- **CloudShell・ターミナルは閉じる**（映り込み防止）
- ブラウザはシークレットモード or 拡張機能を無効化した専用プロファイル
- AWS コンソール右上のユーザー名を隠す（ブラウザ幅を狭める or マスク処理）
- 通知・タブバー等の雑音を非表示
- 解像度は 1280x800 以上

## マスク対象

[docs/screenshots/MASK_GUIDE.md](../../MASK_GUIDE.md) の「Phase 7 追加項目」
セクションに従ってマスク処理を行う:

- アカウント ID（`<ACCOUNT_ID>`）
- メールアドレス
- 実地理座標
- PII 原文
- FOIA 請求者情報
- 部署名・担当者名

## ディレクトリ運用

```
docs/screenshots/
├── originals/phase7/    # マスク前（.gitignore）
└── masked/phase7/       # マスク済み（公開）
    ├── README.md        # このファイル
    └── phase7-*.png
```
