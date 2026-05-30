# UC3: Manufacturing Analytics — テストデータ

## 概要

製造 IoT データ分析ワークフローのテスト用サンプルデータ。

## ファイル構成

```
test-data/manufacturing-analytics/
└── sensors/
    └── sample-sensor-data-001.json   # センサーデータサンプル（異常値含む）
```

## サンプルデータの説明

### sample-sensor-data-001.json

温度センサーの時系列データサンプル。以下を含む:
- センサーメタデータ（ID、種類、設置場所、単位）
- サンプル読み取り値（正常値 + 異常値）
- 統計サマリー（平均、最大、最小、標準偏差、異常カウント）

## 使用方法

1. Glue ETL スクリプトのテストインプットとして使用
2. Athena 異常検出クエリのテストデータとして使用
3. Rekognition 画像分析のモックデータとして使用
