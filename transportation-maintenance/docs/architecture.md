# UC22: 運輸・鉄道 — 設備点検画像分析 / 保守レポート管理 アーキテクチャ

🌐 **Language / 言語**: 日本語 | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## Architecture Diagram

```mermaid
flowchart TB
    subgraph INPUT["📥 Input — FSx for ONTAP"]
        DATA["鉄道インフラデータ<br/>JPEG/PNG/TIFF（点検画像: 軌道、橋梁、信号設備）<br/>PDF/Excel（保守報告書）<br/>点検ルート・日付別に整理"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC 内実行<br/>• 点検画像検出（ルート・日付別）<br/>• 保守報告書検出（PDF/Excel）<br/>• Manifest 生成（キー、サイズ、最終更新）"]
        DD["2️⃣ Deterioration Detector Lambda<br/>• Rekognition DetectLabels<br/>  - 標準閾値: 80%<br/>  - ⚠️ 安全重要閾値: 60%<br/>（橋梁、信号、レール接合部）<br/>• 劣化指標検出（亀裂、錆、変位）<br/>• Bedrock 重大度分類<br/>（critical/major/minor/observation）<br/>• < 90% → human_review_required: true<br/>• < 1024×768 → requires-reinspection"]
        ME["3️⃣ Maintenance Extractor Lambda<br/>• Textract AnalyzeDocument (Cross-Region us-east-1)<br/>• 修理履歴抽出<br/>（設置日、最終修理日、部品年齢、交換スケジュール）<br/>• Comprehend エンティティ抽出"]
        RL["4️⃣ Report Lambda<br/>• 12ヶ月劣化トレンド分析<br/>• 保守優先度ランキング<br/>（重大度レベル × 部品年齢 順）<br/>• CloudWatch EMF Metrics"]
    end

    subgraph OUTPUT["📤 Output"]
        TREND["reports/{date}/deterioration-trend.json<br/>12ヶ月劣化トレンド"]
        PRIOR["reports/{date}/maintenance-priority.json<br/>保守優先度ランキング"]
        REVIEW["reports/{date}/human-review-queue.json<br/>人間レビュー待ちキュー"]
        ERR["errors/{date}/"]
    end

    DATA --> ALIAS --> DISC
    DISC --> DD
    DISC --> ME
    DD --> RL
    ME --> RL
    RL --> TREND
    RL --> PRIOR
    RL --> REVIEW
    RL --> ERR
```

---

## Safety-Critical Design

### デュアル閾値アーキテクチャ

```mermaid
graph TD
    IMG[点検画像] --> CAT{インフラカテゴリ判定}
    CAT -->|標準| STD[Rekognition ≥ 80%]
    CAT -->|安全重要<br/>橋梁/信号/レール接合部| SAFE[Rekognition ≥ 60%]
    STD --> CLASS[Bedrock 重大度分類]
    SAFE --> CLASS
    CLASS --> CONF{信頼度 < 90%?}
    CONF -->|Yes| HR[human_review_required: true]
    CONF -->|No| AUTO[自動記録]
```

### 低解像度画像ハンドリング

- 解像度 < 1024×768 ピクセル: `requires-reinspection` マーク
- 品質メトリクス記録: 実際の解像度、ファイルサイズ、分析に必要な最小解像度

---

## Key Design Decisions

1. **デュアル閾値** — 安全重要インフラ（60%）vs 標準インフラ（80%）で検出感度を分離
2. **人間レビュー必須化** — 90% 未満の検出は全件エンジニアレビュー。偽陰性リスク最小化
3. **12ヶ月トレンド分析** — 経時劣化パターンの可視化で予防保全計画を支援
4. **重大度 × 部品年齢** — 優先度ランキングの二軸評価
5. **Cross-Region Textract** — 保守報告書の正確な解析のため us-east-1 を使用
6. **エラー分離** — 個別画像の処理失敗がバッチ全体を停止させない

---

## AWS Services Used

| サービス | 役割 |
|---------|------|
| FSx for ONTAP | 点検画像・保守報告書のストレージ |
| S3 Access Points | ONTAP ボリュームへのサーバーレスアクセス |
| Amazon Rekognition | 劣化指標検出（デュアル閾値） |
| Amazon Bedrock | 重大度分類（4段階） |
| Amazon Textract | 保守報告書解析（Cross-Region us-east-1） |
| Amazon Comprehend | エンティティ抽出 |
| Step Functions | ワークフローオーケストレーション |
| EventBridge Scheduler | 日次トリガー |
| SNS | Critical アラート通知 |
| CloudWatch + X-Ray | オブザーバビリティ |
