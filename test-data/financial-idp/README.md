# UC2: Financial IDP — テストデータ

## 概要

金融帳票 OCR・エンティティ抽出ワークフローのテスト用サンプルデータ。

## ファイル構成

```
test-data/financial-idp/
└── invoices/
    └── sample-invoice-001.json   # OCR 結果サンプル（請求書）
```

## サンプルデータの説明

### sample-invoice-001.json

Textract OCR 結果のサンプル。以下のフィールドを含む:
- 請求書番号、取引先名、日付、金額
- 明細行（品目、数量、単価、金額）
- エンティティ抽出結果（組織名、日付、金額）
- 信頼度スコア

## 使用方法

1. Lambda ハンドラーのユニットテストで使用
2. Bedrock サマリー生成のインプットとして使用
3. Athena 分析クエリのテストデータとして使用

## 注意事項

- 実際の OCR は Amazon Textract（us-east-1 クロスリージョン）で実行されます
- このサンプルは OCR 後の構造化データ形式です
- 実環境テストには Textract API アクセスが必要です
