# UC1: Legal Compliance — テストデータ

## 概要

法務・コンプライアンス監査ワークフローのテスト用サンプルデータ。

## ファイル構成

```
test-data/legal-compliance/
└── contracts/
    └── sample-contract-001.json   # ACL メタデータサンプル（違反パターン含む）
```

## サンプルデータの説明

### sample-contract-001.json

NTFS ACL メタデータのサンプル。以下の違反パターンを含む:
- `everyone_full_control: true` — 「Everyone フルコントロール」の高リスク違反

## 使用方法

1. S3 AP 経由で FSx for ONTAP ボリュームにサンプルファイルを配置
2. Step Functions ワークフローを実行
3. ACL 収集 → Athena 分析 → レポート生成の流れを確認

## 注意事項

- 実際の NTFS ACL は ONTAP REST API 経由で収集されます
- このサンプルは Lambda ハンドラーのユニットテスト用です
- 実環境テストには FSx for ONTAP + S3 AP の構成が必要です
