# UC5: Healthcare DICOM — テストデータ

## 概要

医療 DICOM 匿名化ワークフローのテスト用サンプルデータ。

## ファイル構成

```
test-data/healthcare-dicom/
└── studies/
    └── sample-dicom-metadata-001.json   # DICOM メタデータサンプル（PII 含む）
```

## サンプルデータの説明

### sample-dicom-metadata-001.json

DICOM ファイルのメタデータ抽出結果サンプル。以下を含む:
- DICOM メタデータ（Study UID, Modality, Body Part, 解像度等）
- PII 検出結果（患者名、患者 ID、施設名、紹介医）
- 匿名化対象タグリスト
- HIPAA Safe Harbor 準拠状態

## 使用方法

1. PII 検出 Lambda のユニットテストで使用
2. 匿名化 Lambda のインプットとして使用
3. Comprehend Medical エンティティ抽出のモックデータとして使用

## 注意事項

- 実際の DICOM ファイルは含まれていません（プライバシー保護）
- 公開 DICOM データセットは [TCIA](https://www.cancerimagingarchive.net/) から入手可能
- 実環境テストには Comprehend Medical API アクセスが必要です
- 本サンプルの PII は全て架空のデータです
