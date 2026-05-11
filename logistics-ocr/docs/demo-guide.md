# 配送伝票 OCR・在庫分析 — Demo Guide

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本デモでは、配送伝票の OCR 処理と在庫分析パイプラインを実演する。紙の伝票をデジタル化し、入出庫データを自動集計・分析する。

**デモの核心メッセージ**: 配送伝票を自動でデジタル化し、在庫状況のリアルタイム把握と需要予測を支援する。

**想定時間**: 3〜5 分

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **役職** | 物流マネージャー / 倉庫管理者 |
| **日常業務** | 入出庫管理、在庫確認、配送手配 |
| **課題** | 紙伝票の手動入力による遅延とミス |
| **期待する成果** | 伝票処理の自動化と在庫可視化 |

### Persona: 斎藤さん（物流マネージャー）

- 1 日 500+ 枚の配送伝票を処理
- 手動入力のタイムラグで在庫情報が常に遅れている
- 「伝票をスキャンするだけで在庫に反映させたい」

---

## Demo Scenario: 配送伝票バッチ処理

### ワークフロー全体像

```
配送伝票          OCR 処理       データ構造化       在庫分析
(スキャン画像) →  テキスト抽出 →  フィールド   →   集計レポート
                               マッピング        需要予測
```

---

## Storyboard（5 セクション / 3〜5 分）

### Section 1: Problem Statement（0:00–0:45）

**ナレーション要旨**:
> 1 日 500 枚以上の配送伝票。手動入力では在庫情報の更新が遅れ、欠品や過剰在庫のリスクが高まる。

**Key Visual**: 大量の伝票スキャン画像、手動入力の遅延イメージ

### Section 2: Scan & Upload（0:45–1:30）

**ナレーション要旨**:
> スキャンした伝票画像をフォルダに配置するだけで、OCR パイプラインが自動起動。

**Key Visual**: 伝票画像アップロード → ワークフロー起動

### Section 3: OCR Processing（1:30–2:30）

**ナレーション要旨**:
> OCR で伝票のテキストを抽出し、AI が品名、数量、送り先、日付等のフィールドを自動マッピング。

**Key Visual**: OCR 処理中、フィールド抽出結果

### Section 4: Inventory Analysis（2:30–3:45）

**ナレーション要旨**:
> 抽出データを在庫データベースと照合。入出庫を自動集計し、在庫状況を更新。

**Key Visual**: 在庫集計結果、品目別入出庫推移

### Section 5: Demand Report（3:45–5:00）

**ナレーション要旨**:
> AI が在庫分析レポートを生成。在庫回転率、欠品リスク品目、発注推奨を提示。

**Key Visual**: AI 生成在庫レポート（在庫サマリー + 発注推奨）

---

## Screen Capture Plan

| # | 画面 | セクション |
|---|------|-----------|
| 1 | 伝票スキャン画像一覧 | Section 1 |
| 2 | アップロード・パイプライン起動 | Section 2 |
| 3 | OCR 抽出結果 | Section 3 |
| 4 | 在庫集計ダッシュボード | Section 4 |
| 5 | AI 在庫分析レポート | Section 5 |

---

## Narration Outline

| セクション | 時間 | キーメッセージ |
|-----------|------|--------------|
| Problem | 0:00–0:45 | 「手動入力の遅延で在庫情報が常に古い」 |
| Upload | 0:45–1:30 | 「スキャン配置だけで自動処理開始」 |
| OCR | 1:30–2:30 | 「AI が伝票フィールドを自動認識・構造化」 |
| Analysis | 2:30–3:45 | 「入出庫を自動集計し在庫を即時更新」 |
| Report | 3:45–5:00 | 「欠品リスクと発注推奨を AI が提示」 |

---

## Sample Data Requirements

| # | データ | 用途 |
|---|--------|------|
| 1 | 入庫伝票画像（10 枚） | OCR 処理デモ |
| 2 | 出庫伝票画像（10 枚） | 在庫減算デモ |
| 3 | 手書き伝票（3 枚） | OCR 精度デモ |
| 4 | 在庫マスターデータ | 照合デモ |

---

## Timeline

### 1 週間以内に達成可能

| タスク | 所要時間 |
|--------|---------|
| サンプル伝票画像準備 | 2 時間 |
| パイプライン実行確認 | 2 時間 |
| 画面キャプチャ取得 | 2 時間 |
| ナレーション原稿作成 | 2 時間 |
| 動画編集 | 4 時間 |

### Future Enhancements

- リアルタイム伝票処理（カメラ連携）
- WMS システム連携
- 需要予測モデル統合

---

## Technical Notes

| コンポーネント | 役割 |
|--------------|------|
| Step Functions | ワークフローオーケストレーション |
| Lambda (OCR Processor) | Textract による伝票テキスト抽出 |
| Lambda (Field Mapper) | Bedrock によるフィールドマッピング |
| Lambda (Inventory Updater) | 在庫データ更新・集計 |
| Lambda (Report Generator) | 在庫分析レポート生成 |

### フォールバック

| シナリオ | 対応 |
|---------|------|
| OCR 精度低下 | 事前処理済みデータを使用 |
| Bedrock 遅延 | 事前生成レポートを表示 |

---

*本ドキュメントは技術プレゼンテーション用デモ動画の制作ガイドです。*

---

## 出力先について: OutputDestination で選択可能 (Pattern B)

UC12 logistics-ocr は 2026-05-10 のアップデートで `OutputDestination` パラメータをサポートしました
（`docs/output-destination-patterns.md` 参照）。

**対象ワークロード**: 配送伝票 OCR / 在庫分析 / 物流レポート

**2 つのモード**:

### STANDARD_S3（デフォルト、従来どおり）
新しい S3 バケット（`${AWS::StackName}-output-${AWS::AccountId}`）を作成し、
AI 成果物をそこに書き込みます。

```bash
aws cloudformation deploy \
  --template-file logistics-ocr/template-deploy.yaml \
  --stack-name fsxn-logistics-ocr-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (他の必須パラメータ)
```

### FSXN_S3AP（"no data movement" パターン）
AI 成果物を FSxN S3 Access Point 経由でオリジナルデータと**同一の FSx ONTAP ボリューム**に
書き戻します。SMB/NFS ユーザーが業務で使用するディレクトリ構造内で AI 成果物を
直接閲覧できます。標準 S3 バケットは作成されません。

```bash
aws cloudformation deploy \
  --template-file logistics-ocr/template-deploy.yaml \
  --stack-name fsxn-logistics-ocr-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (他の必須パラメータ)
```

**注意事項**:

- `S3AccessPointName` の指定を強く推奨（Alias 形式と ARN 形式の両方で IAM 許可する）
- 5GB 超のオブジェクトは FSxN S3AP では不可（AWS 仕様）、マルチパートアップロード必須
- AWS 仕様上の制約は
  [プロジェクト README の "AWS 仕様上の制約と回避策" セクション](../../README.md#aws-仕様上の制約と回避策)
  および [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md) を参照

---

## 検証済みの UI/UX スクリーンショット

Phase 7 UC15/16/17 と UC6/11/14 のデモと同じ方針で、**エンドユーザーが日常業務で実際に
見る UI/UX 画面**を対象とする。技術者向けビュー（Step Functions グラフ、CloudFormation
スタックイベント等）は `docs/verification-results-*.md` に集約。

### このユースケースの検証ステータス

- ✅ **E2E 実行**: Phase 1-6 で確認済み（根 README 参照）
- 📸 **UI/UX 再撮影**: ✅ 2026-05-10 再デプロイ検証で撮影済み （UC12 Step Functions グラフ、Lambda 実行成功を確認）
- 🔄 **再現方法**: 本ドキュメント末尾の「撮影ガイド」を参照

### 2026-05-10 再デプロイ検証で撮影（UI/UX 中心）

#### UC12 Step Functions Graph view（SUCCEEDED）

![UC12 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc12-demo/uc12-stepfunctions-graph.png)

Step Functions Graph view は各 Lambda / Parallel / Map ステートの実行状況を
色で可視化するエンドユーザー最重要画面。

### 既存スクリーンショット（Phase 1-6 から該当分）

![UC12 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc12-demo/step-functions-graph-succeeded.png)

![UC12 Step Functions Graph（ズーム表示 — 各ステップ詳細）](../../docs/screenshots/masked/uc12-demo/step-functions-graph-zoomed.png)

### 再検証時の UI/UX 対象画面（推奨撮影リスト）

- S3 出力バケット（waybills-ocr/、inventory/、reports/）
- Textract 伝票 OCR 結果（Cross-Region）
- Rekognition 倉庫画像ラベル
- 配送集計レポート

### 撮影ガイド

1. **事前準備**:
   - `bash scripts/verify_phase7_prerequisites.sh` で前提確認（共通 VPC/S3 AP 有無）
   - `UC=logistics-ocr bash scripts/package_generic_uc.sh` で Lambda パッケージ
   - `bash scripts/deploy_generic_ucs.sh UC12` でデプロイ

2. **サンプルデータ配置**:
   - S3 AP Alias 経由で `waybills/` プレフィックスにサンプルファイルをアップロード
   - Step Functions `fsxn-logistics-ocr-demo-workflow` を起動（入力 `{}`）

3. **撮影**（CloudShell・ターミナルは閉じる、ブラウザ右上のユーザー名は黒塗り）:
   - S3 出力バケット `fsxn-logistics-ocr-demo-output-<account>` の俯瞰
   - AI/ML 出力 JSON のプレビュー（`build/preview_*.html` の形式を参考に）
   - SNS メール通知（該当する場合）

4. **マスク処理**:
   - `python3 scripts/mask_uc_demos.py logistics-ocr-demo` で自動マスク
   - `docs/screenshots/MASK_GUIDE.md` に従って追加マスク（必要に応じて）

5. **クリーンアップ**:
   - `bash scripts/cleanup_generic_ucs.sh UC12` で削除
   - VPC Lambda ENI 解放に 15-30 分（AWS の仕様）
