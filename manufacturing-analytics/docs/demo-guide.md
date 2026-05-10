# IoT センサー異常検知・品質検査 — Demo Guide

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本デモでは、製造ラインの IoT センサーデータから異常を自動検知し、品質検査レポートを生成するワークフローを実演する。

**デモの核心メッセージ**: センサーデータの異常パターンを自動検出し、品質問題の早期発見と予防保全を実現する。

**想定時間**: 3〜5 分

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **役職** | 製造部門マネージャー / 品質管理エンジニア |
| **日常業務** | 生産ライン監視、品質検査、設備保全計画 |
| **課題** | センサーデータの異常を見逃し、不良品が後工程に流出 |
| **期待する成果** | 異常の早期検知と品質トレンドの可視化 |

### Persona: 鈴木さん（品質管理エンジニア）

- 5 つの製造ラインで 100+ センサーを監視
- 閾値ベースのアラートでは誤報が多く、真の異常を見逃しがち
- 「統計的に有意な異常だけを検出したい」

---

## Demo Scenario: センサー異常検知バッチ分析

### ワークフロー全体像

```
センサーデータ      データ収集       異常検知          品質レポート
(CSV/Parquet)  →   前処理     →   統計分析    →    AI 生成
                   正規化          (外れ値検出)
```

---

## Storyboard（5 セクション / 3〜5 分）

### Section 1: Problem Statement（0:00–0:45）

**ナレーション要旨**:
> 製造ラインの 100+ センサーから毎日大量のデータが生成される。単純な閾値アラートでは誤報が多く、本当の異常を見逃すリスクがある。

**Key Visual**: センサーデータのタイムシリーズグラフ、アラート過多の状況

### Section 2: Data Ingestion（0:45–1:30）

**ナレーション要旨**:
> センサーデータがファイルサーバーに蓄積されると、自動的に分析パイプラインが起動する。

**Key Visual**: データファイル配置 → ワークフロー起動

### Section 3: Anomaly Detection（1:30–2:30）

**ナレーション要旨**:
> 統計的手法（移動平均、標準偏差、IQR）でセンサーごとの異常スコアを算出。複数センサーの相関分析も実行。

**Key Visual**: 異常検知アルゴリズム実行中、異常スコアのヒートマップ

### Section 4: Quality Inspection（2:30–3:45）

**ナレーション要旨**:
> 検出された異常を品質検査の観点で分析。どのラインのどの工程で問題が発生しているかを特定。

**Key Visual**: Athena クエリ結果 — ライン別・工程別の異常分布

### Section 5: Report & Action（3:45–5:00）

**ナレーション要旨**:
> AI が品質検査レポートを生成。異常の根本原因候補と推奨対応を提示。

**Key Visual**: AI 生成品質レポート（異常サマリー + 推奨アクション）

---

## Screen Capture Plan

| # | 画面 | セクション |
|---|------|-----------|
| 1 | センサーデータファイル一覧 | Section 1 |
| 2 | ワークフロー起動画面 | Section 2 |
| 3 | 異常検知処理進捗 | Section 3 |
| 4 | 異常分布クエリ結果 | Section 4 |
| 5 | AI 品質検査レポート | Section 5 |

---

## Narration Outline

| セクション | 時間 | キーメッセージ |
|-----------|------|--------------|
| Problem | 0:00–0:45 | 「閾値アラートでは真の異常を見逃す」 |
| Ingestion | 0:45–1:30 | 「データ蓄積で自動的に分析開始」 |
| Detection | 1:30–2:30 | 「統計的手法で有意な異常のみ検出」 |
| Inspection | 2:30–3:45 | 「ライン・工程レベルで問題箇所を特定」 |
| Report | 3:45–5:00 | 「根本原因候補と対応策を AI が提示」 |

---

## Sample Data Requirements

| # | データ | 用途 |
|---|--------|------|
| 1 | 正常センサーデータ（5 ライン × 7 日分） | ベースライン |
| 2 | 温度異常データ（2 件） | 異常検知デモ |
| 3 | 振動異常データ（3 件） | 相関分析デモ |
| 4 | 品質低下パターン（1 件） | レポート生成デモ |

---

## Timeline

### 1 週間以内に達成可能

| タスク | 所要時間 |
|--------|---------|
| サンプルセンサーデータ生成 | 3 時間 |
| パイプライン実行確認 | 2 時間 |
| 画面キャプチャ取得 | 2 時間 |
| ナレーション原稿作成 | 2 時間 |
| 動画編集 | 4 時間 |

### Future Enhancements

- リアルタイムストリーミング分析
- 予防保全スケジュール自動生成
- デジタルツイン連携

---

## Technical Notes

| コンポーネント | 役割 |
|--------------|------|
| Step Functions | ワークフローオーケストレーション |
| Lambda (Data Preprocessor) | センサーデータ正規化・前処理 |
| Lambda (Anomaly Detector) | 統計的異常検知 |
| Lambda (Report Generator) | Bedrock による品質レポート生成 |
| Amazon Athena | 異常データの集計・分析 |

### フォールバック

| シナリオ | 対応 |
|---------|------|
| データ量不足 | 事前生成データを使用 |
| 検知精度不足 | パラメータ調整済み結果を表示 |

---

*本ドキュメントは技術プレゼンテーション用デモ動画の制作ガイドです。*

---

## 出力先について: FSxN S3 Access Point (Pattern A)

UC3 manufacturing-analytics は **Pattern A: Native S3AP Output** に分類されます
（`docs/output-destination-patterns.md` 参照）。

**設計**: センサーデータ解析結果、異常検知レポート、画像検査結果は全て FSxN S3 Access Point 経由で
オリジナルセンサー CSV と検査画像と**同一の FSx ONTAP ボリューム**に書き戻されます。標準 S3 バケットは
作成されません（"no data movement" パターン）。

**CloudFormation パラメータ**:
- `S3AccessPointAlias`: 入力データ読み取り用 S3 AP Alias
- `S3AccessPointOutputAlias`: 出力書き込み用 S3 AP Alias（入力と同じでも可）

**デプロイ例**:
```bash
aws cloudformation deploy \
  --template-file manufacturing-analytics/template-deploy.yaml \
  --stack-name fsxn-manufacturing-analytics-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (他の必須パラメータ)
```

**SMB/NFS ユーザーからの見え方**:
```
/vol/sensors/
  ├── 2026/05/line_A/sensor_001.csv    # オリジナルセンサーデータ
  └── analysis/2026/05/                 # AI 異常検知結果（同じボリューム内）
      └── line_A_report.json
```

AWS 仕様上の制約については
[プロジェクト README の "AWS 仕様上の制約と回避策" セクション](../../README.md#aws-仕様上の制約と回避策)
および [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md) を参照。

---

## 検証済みの UI/UX スクリーンショット

Phase 7 UC15/16/17 と UC6/11/14 のデモと同じ方針で、**エンドユーザーが日常業務で実際に
見る UI/UX 画面**を対象とする。技術者向けビュー（Step Functions グラフ、CloudFormation
スタックイベント等）は `docs/verification-results-*.md` に集約。

### このユースケースの検証ステータス

- ✅ **E2E 実行**: Phase 1-6 で確認済み（根 README 参照）
- 📸 **UI/UX 再撮影**: ✅ 2026-05-10 再デプロイ検証で撮影済み （UC3 Step Functions グラフ、Lambda 実行成功を確認）
- 🔄 **再現方法**: 本ドキュメント末尾の「撮影ガイド」を参照

### 2026-05-10 再デプロイ検証で撮影（UI/UX 中心）

#### UC3 Step Functions Graph view（SUCCEEDED）

![UC3 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc3-demo/uc3-stepfunctions-graph.png)

Step Functions Graph view は各 Lambda / Parallel / Map ステートの実行状況を
色で可視化するエンドユーザー最重要画面。

### 既存スクリーンショット（Phase 1-6 から該当分）

*(該当なし。再検証時に新規撮影してください)*

### 再検証時の UI/UX 対象画面（推奨撮影リスト）

- S3 出力バケット（metrics/、anomalies/、reports/）
- Athena クエリ結果（IoT センサー異常検出）
- Rekognition 品質検査画像ラベル
- 製造品質サマリーレポート

### 撮影ガイド

1. **事前準備**:
   - `bash scripts/verify_phase7_prerequisites.sh` で前提確認（共通 VPC/S3 AP 有無）
   - `UC=manufacturing-analytics bash scripts/package_generic_uc.sh` で Lambda パッケージ
   - `bash scripts/deploy_generic_ucs.sh UC3` でデプロイ

2. **サンプルデータ配置**:
   - S3 AP Alias 経由で `sensors/` プレフィックスにサンプルファイルをアップロード
   - Step Functions `fsxn-manufacturing-analytics-demo-workflow` を起動（入力 `{}`）

3. **撮影**（CloudShell・ターミナルは閉じる、ブラウザ右上のユーザー名は黒塗り）:
   - S3 出力バケット `fsxn-manufacturing-analytics-demo-output-<account>` の俯瞰
   - AI/ML 出力 JSON のプレビュー（`build/preview_*.html` の形式を参考に）
   - SNS メール通知（該当する場合）

4. **マスク処理**:
   - `python3 scripts/mask_uc_demos.py manufacturing-analytics-demo` で自動マスク
   - `docs/screenshots/MASK_GUIDE.md` に従って追加マスク（必要に応じて）

5. **クリーンアップ**:
   - `bash scripts/cleanup_generic_ucs.sh UC3` で削除
   - VPC Lambda ENI 解放に 15-30 分（AWS の仕様）
