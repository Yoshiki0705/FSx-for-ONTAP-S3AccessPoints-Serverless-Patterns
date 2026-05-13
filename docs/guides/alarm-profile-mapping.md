# UC 別アラームプロファイル割り当て

**Phase 10 — Observability Alarm Tuning**

## 概要

各 UC のワークロード特性に応じて、CloudWatch Alarm の閾値プロファイルを割り当てる。
プロファイルは `AlarmProfile` CloudFormation パラメータで制御される。

## プロファイル定義

| プロファイル | Step Functions 失敗率閾値 | Discovery Lambda エラー閾値 | 評価期間 | 対象ワークロード |
|---|---|---|---|---|
| **BATCH** | 10% | 3 回/時間 | 3 期間 | 定期バッチ処理、低頻度実行 |
| **REALTIME** | 5% | 1 回/時間 | 1 期間 | リアルタイム処理、SLA 厳格 |
| **HIGH_VOLUME** | 15% | 5 回/時間 | 5 期間 | 大量ファイル処理、一時的エラー許容 |
| **CUSTOM** | ユーザー指定 | ユーザー指定 | 3 期間 | 上記に該当しない特殊要件 |

## UC 別デフォルト割り当て

| UC | 名称 | プロファイル | 根拠 |
|---|---|---|---|
| UC1 | legal-compliance | BATCH | 日次/週次のコンプライアンスチェック。即時性不要 |
| UC2 | financial-idp | REALTIME | 金融文書の即時処理。SLA 厳格（FISC 準拠） |
| UC3 | manufacturing-analytics | BATCH | 製造データの定期分析。バッチ処理パターン |
| UC4 | logistics-ocr | BATCH | 物流伝票の定期 OCR 処理 |
| UC5 | healthcare-dicom | REALTIME | 医療画像の即時処理。患者ケアに影響 |
| UC6 | semiconductor-eda | HIGH_VOLUME | EDA ファイルの大量処理。一時的エラー許容 |
| UC7 | genomics-pipeline | HIGH_VOLUME | ゲノムデータの大量並列処理 |
| UC8 | energy-seismic | HIGH_VOLUME | 地震データの大量処理 |
| UC9 | autonomous-driving | REALTIME | 自動運転データの即時処理。安全性に影響 |
| UC10 | construction-bim | BATCH | BIM モデルの定期処理 |
| UC11 | retail-catalog | REALTIME | 商品カタログのリアルタイム更新 |
| UC12 | media-vfx | HIGH_VOLUME | VFX レンダリングの大量処理 |
| UC13 | education-research | BATCH | 研究データの定期分析 |
| UC14 | insurance-claims | REALTIME | 保険請求の即時処理。顧客対応に影響 |
| UC15 | defense-satellite | BATCH | 衛星画像の定期分析 |
| UC16 | government-archives | BATCH | 公文書の定期アーカイブ処理 |
| UC17 | smart-city-geospatial | REALTIME | 都市データのリアルタイム分析 |

## プロファイル選択の判断基準

### BATCH を選択する場合
- 処理の即時性が不要（分〜時間単位の遅延許容）
- 定期スケジュール実行（日次/週次）
- 一時的なエラーは次回実行で自動回復

### REALTIME を選択する場合
- 処理の即時性が必要（秒〜分単位の SLA）
- エラー発生時に即座に運用チームへの通知が必要
- 顧客対応や安全性に直接影響するワークロード

### HIGH_VOLUME を選択する場合
- 大量ファイル（1000+ ファイル/実行）の並列処理
- 一部ファイルの処理失敗は許容（リトライで回復）
- スロットリングやタイムアウトが発生しやすい

### CUSTOM を選択する場合
- 上記プロファイルのいずれにも該当しない
- 特定の SLA 要件がある
- `CustomFailureThreshold` と `CustomErrorThreshold` で個別指定

## CloudFormation パラメータ

```yaml
Parameters:
  AlarmProfile:
    Type: String
    Default: BATCH
    AllowedValues: [BATCH, REALTIME, HIGH_VOLUME, CUSTOM]
    Description: >
      アラーム閾値プロファイル。BATCH=定期バッチ処理向け（緩い閾値）、
      REALTIME=リアルタイム処理向け（厳しい閾値）、
      HIGH_VOLUME=大量処理向け（エラー許容度高）、
      CUSTOM=個別指定

  CustomFailureThreshold:
    Type: Number
    Default: 10
    MinValue: 1
    MaxValue: 100
    Description: CUSTOM プロファイル時の Step Functions 失敗率閾値（%）

  CustomErrorThreshold:
    Type: Number
    Default: 3
    MinValue: 1
    MaxValue: 100
    Description: CUSTOM プロファイル時の Discovery Lambda エラー閾値（回/時間）
```

## 運用ガイダンス

### プロファイル変更手順

1. CloudFormation スタックの `AlarmProfile` パラメータを変更
2. スタック更新を実行
3. CloudWatch Alarm の閾値が自動的に更新される
4. 変更後 1 時間は誤検知がないか監視

### 閾値チューニングのベストプラクティス

- 初期デプロイ時はデフォルトプロファイルを使用
- 1 週間の運用データを収集後、誤検知率を評価
- 誤検知が多い場合は HIGH_VOLUME に変更
- 検知漏れが多い場合は REALTIME に変更
- 特殊要件がある場合のみ CUSTOM を使用
