# 事故写真損害査定・保険金レポート — Demo Guide

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本デモでは、事故写真からの損害査定と保険金請求レポート自動生成パイプラインを実演する。画像解析による損害評価と AI レポート生成で、査定プロセスを効率化する。

**デモの核心メッセージ**: 事故写真を AI が自動解析し、損害程度の評価と保険金請求レポートを即座に生成する。

**想定時間**: 3〜5 分

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **役職** | 損害査定担当 / クレームアジャスター |
| **日常業務** | 事故写真確認、損害評価、保険金算定、レポート作成 |
| **課題** | 大量の請求案件を迅速に処理する必要がある |
| **期待する成果** | 査定プロセスの迅速化と一貫性の確保 |

### Persona: 小林さん（損害査定担当）

- 月に 100+ 件の保険金請求を処理
- 写真から損害程度を判断し、レポートを作成
- 「初期査定を自動化し、複雑な案件に集中したい」

---

## Demo Scenario: 自動車事故の損害査定

### ワークフロー全体像

```
事故写真         画像解析        損害評価          請求レポート
(複数枚)    →   損傷検出    →   程度判定    →    AI 生成
                 部位特定        金額推定
```

---

## Storyboard（5 セクション / 3〜5 分）

### Section 1: Problem Statement（0:00–0:45）

**ナレーション要旨**:
> 月 100 件以上の保険金請求。各案件で複数の事故写真を確認し、損害程度を評価してレポートを作成する。手動では処理が追いつかない。

**Key Visual**: 保険金請求案件一覧、事故写真サンプル

### Section 2: Photo Upload（0:45–1:30）

**ナレーション要旨**:
> 事故写真がアップロードされると、自動査定パイプラインが起動。案件単位で処理。

**Key Visual**: 写真アップロード → ワークフロー自動起動

### Section 3: Damage Detection（1:30–2:30）

**ナレーション要旨**:
> AI が写真を解析し、損傷箇所を検出。損傷の種類（凹み、傷、破損）と部位（バンパー、ドア、フェンダー等）を特定。

**Key Visual**: 損傷検出結果、部位マッピング

### Section 4: Assessment（2:30–3:45）

**ナレーション要旨**:
> 損傷の程度を評価し、修理/交換の判断と概算金額を算出。過去の類似案件との比較も実施。

**Key Visual**: 損害評価結果テーブル、金額推定

### Section 5: Claims Report（3:45–5:00）

**ナレーション要旨**:
> AI が保険金請求レポートを自動生成。損害サマリー、推定金額、推奨対応を含む。査定担当者は確認・承認するだけ。

**Key Visual**: AI 生成請求レポート（損害サマリー + 金額推定）

---

## Screen Capture Plan

| # | 画面 | セクション |
|---|------|-----------|
| 1 | 請求案件一覧 | Section 1 |
| 2 | 写真アップロード・パイプライン起動 | Section 2 |
| 3 | 損傷検出結果 | Section 3 |
| 4 | 損害評価・金額推定 | Section 4 |
| 5 | 保険金請求レポート | Section 5 |

---

## Narration Outline

| セクション | 時間 | キーメッセージ |
|-----------|------|--------------|
| Problem | 0:00–0:45 | 「月 100 件の請求を手動査定するのは限界」 |
| Upload | 0:45–1:30 | 「写真アップロードで自動査定開始」 |
| Detection | 1:30–2:30 | 「AI が損傷箇所と種類を自動検出」 |
| Assessment | 2:30–3:45 | 「損害程度と修理金額を自動推定」 |
| Report | 3:45–5:00 | 「請求レポートを自動生成、確認・承認のみ」 |

---

## Sample Data Requirements

| # | データ | 用途 |
|---|--------|------|
| 1 | 軽微な損傷写真（5 件） | 基本査定デモ |
| 2 | 中程度の損傷写真（3 件） | 評価精度デモ |
| 3 | 重大な損傷写真（2 件） | 全損判定デモ |

---

## Timeline

### 1 週間以内に達成可能

| タスク | 所要時間 |
|--------|---------|
| サンプル写真データ準備 | 2 時間 |
| パイプライン実行確認 | 2 時間 |
| 画面キャプチャ取得 | 2 時間 |
| ナレーション原稿作成 | 2 時間 |
| 動画編集 | 4 時間 |

### Future Enhancements

- 動画からの損傷検出
- 修理工場見積もりとの自動照合
- 不正請求検知

---

## Technical Notes

| コンポーネント | 役割 |
|--------------|------|
| Step Functions | ワークフローオーケストレーション |
| Lambda (Image Analyzer) | Bedrock/Rekognition による損傷検出 |
| Lambda (Damage Assessor) | 損害程度評価・金額推定 |
| Lambda (Report Generator) | Bedrock による請求レポート生成 |
| Amazon Athena | 過去案件データの参照・比較 |

### フォールバック

| シナリオ | 対応 |
|---------|------|
| 画像解析精度不足 | 事前解析済み結果を使用 |
| Bedrock 遅延 | 事前生成レポートを表示 |

---

*本ドキュメントは技術プレゼンテーション用デモ動画の制作ガイドです。*

---

## 検証済みの UI/UX スクリーンショット（2026-05-10 AWS 検証）

Phase 7 と同じ方針で、**保険査定担当者が日常業務で実際に使う UI/UX 画面**を撮影。
技術者向け画面（Step Functions グラフ等）は除外。

### 出力先の選択: 標準 S3 vs FSxN S3AP

UC14 は 2026-05-10 のアップデートで `OutputDestination` パラメータをサポートしました。
**同一 FSx ボリュームに AI 成果物を書き戻す** ことで、請求処理担当者が
請求ケースのディレクトリ構造内で損害評価 JSON・OCR 結果・請求レポートを閲覧できます
（"no data movement" パターン、PII 保護の観点でも有利）。

```bash
# STANDARD_S3 モード（デフォルト、従来どおり）
--parameter-overrides OutputDestination=STANDARD_S3 ...

# FSXN_S3AP モード（AI 成果物を FSx ONTAP ボリュームに書き戻し）
--parameter-overrides \
  OutputDestination=FSXN_S3AP \
  OutputS3APPrefix=ai-outputs/ \
  ...
```

AWS 仕様上の制約と回避策は [プロジェクト README の "AWS 仕様上の制約と回避策"
セクション](../../README.md#aws-仕様上の制約と回避策) 参照。

### 1. 保険金請求レポート — 査定担当者向けサマリー

事故写真 Rekognition 解析 + 見積書 Textract OCR + 査定推奨判定を統合したレポート。
判定 `MANUAL_REVIEW` + 信頼度 75% で、自動化できない項目を担当者がレビュー。

<!-- SCREENSHOT: uc14-claims-report.png
     内容: 保険金請求レポート（請求 ID、損害サマリー、見積相関、推奨判定）
            + Rekognition 検出ラベル一覧 + Textract OCR 結果
     マスク: アカウント ID、バケット名 -->
![UC14: 保険金請求レポート](../../docs/screenshots/masked/uc14-demo/uc14-claims-report.png)

### 2. S3 出力バケット — 査定アーティファクトの俯瞰

査定担当者が請求ケースごとのアーティファクトを確認する画面。
`assessments/` (Rekognition 分析) + `estimates/` (Textract OCR) + `reports/` (統合レポート)。

<!-- SCREENSHOT: uc14-s3-output-bucket.png
     内容: S3 コンソールで assessments/, estimates/, reports/ プレフィックス
     マスク: アカウント ID -->
![UC14: S3 出力バケット](../../docs/screenshots/masked/uc14-demo/uc14-s3-output-bucket.png)

### 実測値（2026-05-10 AWS デプロイ検証）

- **Step Functions 実行**: SUCCEEDED
- **Rekognition**: 事故写真で `Maroon` 90.79%, `Business Card` 84.51% 等を検出
- **Textract**: cross-region us-east-1 経由で見積書 PDF から `Total: 1270.00 USD` 等を OCR
- **生成アーティファクト**: assessments/*.json, estimates/*.json, reports/*.txt
- **実スタック**: `fsxn-insurance-claims-demo`（ap-northeast-1、2026-05-10 検証時）
