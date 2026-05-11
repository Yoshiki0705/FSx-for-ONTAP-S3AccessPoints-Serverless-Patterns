# BIM モデル変更検知・安全コンプライアンス — Demo Guide

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本デモでは、BIM モデルの変更検知と安全コンプライアンスチェックパイプラインを実演する。設計変更を自動検出し、建築基準への適合性を検証する。

**デモの核心メッセージ**: BIM モデルの変更を自動追跡し、安全基準違反を即座に検出。設計レビューサイクルを短縮する。

**想定時間**: 3〜5 分

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **役職** | BIM マネージャー / 構造設計エンジニア |
| **日常業務** | BIM モデル管理、設計変更レビュー、コンプライアンス確認 |
| **課題** | 複数チームの設計変更を追跡し、基準適合を確認するのが困難 |
| **期待する成果** | 変更の自動検知と安全基準チェックの効率化 |

### Persona: 木村さん（BIM マネージャー）

- 大規模建設プロジェクトで 20+ の設計チームが並行作業
- 日々の設計変更が安全基準に影響しないか確認が必要
- 「変更があったら自動で安全チェックを走らせたい」

---

## Demo Scenario: 設計変更の自動検知と安全検証

### ワークフロー全体像

```
BIM モデル更新     変更検知        コンプライアンス     レビューレポート
(IFC/RVT)    →   差分解析    →   ルール照合     →    AI 生成
                  要素比較        安全基準チェック
```

---

## Storyboard（5 セクション / 3〜5 分）

### Section 1: Problem Statement（0:00–0:45）

**ナレーション要旨**:
> 大規模プロジェクトで 20 チームが並行して BIM モデルを更新。変更が安全基準に違反していないか、手動確認では追いつかない。

**Key Visual**: BIM モデルファイル一覧、複数チームの更新履歴

### Section 2: Change Detection（0:45–1:30）

**ナレーション要旨**:
> モデルファイルの更新を検知し、前バージョンとの差分を自動解析。変更された要素（構造部材、設備配置等）を特定。

**Key Visual**: 変更検知トリガー、差分解析開始

### Section 3: Compliance Check（1:30–2:30）

**ナレーション要旨**:
> 変更された要素に対して安全基準ルールを自動照合。耐震基準、防火区画、避難経路等の適合性を検証。

**Key Visual**: ルール照合処理中、チェック項目一覧

### Section 4: Results Analysis（2:30–3:45）

**ナレーション要旨**:
> 検証結果を確認。違反項目、影響範囲、重要度を一覧表示。

**Key Visual**: 違反検出結果テーブル、重要度別分類

### Section 5: Review Report（3:45–5:00）

**ナレーション要旨**:
> AI が設計レビューレポートを生成。違反の詳細、是正案、影響を受ける他の設計要素を提示。

**Key Visual**: AI 生成レビューレポート

---

## Screen Capture Plan

| # | 画面 | セクション |
|---|------|-----------|
| 1 | BIM モデルファイル一覧 | Section 1 |
| 2 | 変更検知・差分表示 | Section 2 |
| 3 | コンプライアンスチェック進捗 | Section 3 |
| 4 | 違反検出結果 | Section 4 |
| 5 | AI レビューレポート | Section 5 |

---

## Narration Outline

| セクション | 時間 | キーメッセージ |
|-----------|------|--------------|
| Problem | 0:00–0:45 | 「並行作業の変更追跡と安全確認が追いつかない」 |
| Detection | 0:45–1:30 | 「モデル更新を自動検知し差分を解析」 |
| Compliance | 1:30–2:30 | 「安全基準ルールを自動照合」 |
| Results | 2:30–3:45 | 「違反項目と影響範囲を即座に把握」 |
| Report | 3:45–5:00 | 「是正案と影響分析を AI が提示」 |

---

## Sample Data Requirements

| # | データ | 用途 |
|---|--------|------|
| 1 | ベース BIM モデル（IFC 形式） | 比較元 |
| 2 | 変更後モデル（構造変更あり） | 差分検知デモ |
| 3 | 安全基準違反モデル（3 件） | コンプライアンスデモ |

---

## Timeline

### 1 週間以内に達成可能

| タスク | 所要時間 |
|--------|---------|
| サンプル BIM データ準備 | 3 時間 |
| パイプライン実行確認 | 2 時間 |
| 画面キャプチャ取得 | 2 時間 |
| ナレーション原稿作成 | 2 時間 |
| 動画編集 | 4 時間 |

### Future Enhancements

- 3D ビジュアライゼーション連携
- リアルタイム変更通知
- 施工段階との整合性チェック

---

## Technical Notes

| コンポーネント | 役割 |
|--------------|------|
| Step Functions | ワークフローオーケストレーション |
| Lambda (Change Detector) | BIM モデル差分解析 |
| Lambda (Compliance Checker) | 安全基準ルール照合 |
| Lambda (Report Generator) | Bedrock によるレビューレポート生成 |
| Amazon Athena | 変更履歴・違反データの集計 |

### フォールバック

| シナリオ | 対応 |
|---------|------|
| IFC パース失敗 | 事前解析済みデータを使用 |
| ルール照合遅延 | 事前検証済み結果を表示 |

---

*本ドキュメントは技術プレゼンテーション用デモ動画の制作ガイドです。*

---

## 出力先について: OutputDestination で選択可能 (Pattern B)

UC10 construction-bim は 2026-05-10 のアップデートで `OutputDestination` パラメータをサポートしました
（`docs/output-destination-patterns.md` 参照）。

**対象ワークロード**: 建設 BIM / 図面 OCR / 安全コンプライアンスチェック

**2 つのモード**:

### STANDARD_S3（デフォルト、従来どおり）
新しい S3 バケット（`${AWS::StackName}-output-${AWS::AccountId}`）を作成し、
AI 成果物をそこに書き込みます。

```bash
aws cloudformation deploy \
  --template-file construction-bim/template-deploy.yaml \
  --stack-name fsxn-construction-bim-demo \
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
  --template-file construction-bim/template-deploy.yaml \
  --stack-name fsxn-construction-bim-demo \
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
- 📸 **UI/UX 再撮影**: ✅ 2026-05-10 再デプロイ検証で撮影済み （UC10 Step Functions グラフ、Lambda 実行成功を確認）
- 🔄 **再現方法**: 本ドキュメント末尾の「撮影ガイド」を参照

### 2026-05-10 再デプロイ検証で撮影（UI/UX 中心）

#### UC10 Step Functions Graph view（SUCCEEDED）

![UC10 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc10-demo/uc10-stepfunctions-graph.png)

Step Functions Graph view は各 Lambda / Parallel / Map ステートの実行状況を
色で可視化するエンドユーザー最重要画面。

### 既存スクリーンショット（Phase 1-6 から該当分）

![UC10 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc10-demo/step-functions-graph-succeeded.png)

![UC10 Step Functions Graph（ズーム表示 — 各ステップ詳細）](../../docs/screenshots/masked/uc10-demo/step-functions-graph-zoomed.png)

### 再検証時の UI/UX 対象画面（推奨撮影リスト）

- S3 出力バケット（drawings-ocr/、bim-metadata/、safety-reports/）
- Textract 図面 OCR 結果（Cross-Region）
- BIM バージョン差分レポート
- Bedrock 安全コンプライアンスチェック

### 撮影ガイド

1. **事前準備**:
   - `bash scripts/verify_phase7_prerequisites.sh` で前提確認（共通 VPC/S3 AP 有無）
   - `UC=construction-bim bash scripts/package_generic_uc.sh` で Lambda パッケージ
   - `bash scripts/deploy_generic_ucs.sh UC10` でデプロイ

2. **サンプルデータ配置**:
   - S3 AP Alias 経由で `drawings/` プレフィックスにサンプルファイルをアップロード
   - Step Functions `fsxn-construction-bim-demo-workflow` を起動（入力 `{}`）

3. **撮影**（CloudShell・ターミナルは閉じる、ブラウザ右上のユーザー名は黒塗り）:
   - S3 出力バケット `fsxn-construction-bim-demo-output-<account>` の俯瞰
   - AI/ML 出力 JSON のプレビュー（`build/preview_*.html` の形式を参考に）
   - SNS メール通知（該当する場合）

4. **マスク処理**:
   - `python3 scripts/mask_uc_demos.py construction-bim-demo` で自動マスク
   - `docs/screenshots/MASK_GUIDE.md` に従って追加マスク（必要に応じて）

5. **クリーンアップ**:
   - `bash scripts/cleanup_generic_ucs.sh UC10` で削除
   - VPC Lambda ENI 解放に 15-30 分（AWS の仕様）
