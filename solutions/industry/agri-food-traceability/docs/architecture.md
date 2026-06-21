# UC21: 農業・食品 — 農地航空画像分析 / トレーサビリティ文書管理 アーキテクチャ

🌐 **Language / 言語**: 日本語 | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## Architecture Diagram

```mermaid
flowchart TB
    subgraph INPUT["📥 Input — FSx for ONTAP"]
        DATA["農業・食品データ<br/>GeoTIFF / GPS 付き JPEG（ドローン/航空画像, 最大 500 MB）<br/>収穫記録、出荷マニフェスト、検査証明書"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC 内実行<br/>• GeoTIFF/JPEG 画像検出（GPS メタデータ確認）<br/>• トレーサビリティ文書検出<br/>• ファイルサイズ上限 500 MB フィルタ"]
        CA["2️⃣ Crop Analyzer Lambda<br/>• Rekognition DetectLabels<br/>• 植生指数（NDVI 相当）分析<br/>• Bedrock 異常分類<br/>（病害虫、灌漑問題）<br/>• 信頼度 ≥ 0.70 のみ保持"]
        TE["3️⃣ Traceability Extractor Lambda<br/>• Textract AnalyzeDocument (Cross-Region us-east-1)<br/>• ロット ID、日付、産地、責任者抽出<br/>• Comprehend ロット分類（≥ 0.80 信頼度）"]
        RL["4️⃣ Report Lambda<br/>• 作物健全性レポート<br/>（圃場別異常カウント、タイプ、座標）<br/>• トレーサビリティ監査サマリ<br/>（ロット別文書数、信頼度分布）<br/>• 120 秒以内に完了"]
    end

    subgraph OUTPUT["📤 Output"]
        CROP["reports/{date}/crop-health.json"]
        TRACE["reports/{date}/traceability-audit.json"]
        ERR["errors/{date}/"]
    end

    DATA --> ALIAS --> DISC
    DISC --> CA
    DISC --> TE
    CA --> RL
    TE --> RL
    RL --> CROP
    RL --> TRACE
    RL --> ERR
```

---

## Key Design Decisions

1. **GPS メタデータベース検出** — GeoTIFF/EXIF GPS データで地理的相関を実現
2. **信頼度閾値の二段階設計** — 作物異常 ≥ 0.70、トレーサビリティ分類 ≥ 0.80
3. **位置情報未検証への対応** — GPS データ欠損時は "location-unverified" として記録し処理継続
4. **120 秒以内のレポート生成** — Report Lambda の SLO 制約
5. **エラー分離** — 個別ファイル失敗がバッチ全体を停止させない

---

## AWS Services Used

| サービス | 役割 |
|---------|------|
| FSx for ONTAP | 農地画像・トレーサビリティ文書のストレージ |
| S3 Access Points | ONTAP ボリュームへのサーバーレスアクセス |
| Amazon Rekognition | 作物画像分析・異常検出 |
| Amazon Bedrock | 異常分類・植生指数解釈 |
| Amazon Textract | 文書解析（Cross-Region us-east-1） |
| Amazon Comprehend | ロット分類・エンティティ抽出 |
| Step Functions | ワークフローオーケストレーション |
| EventBridge Scheduler | 日次トリガー |
| CloudWatch + X-Ray | オブザーバビリティ |
