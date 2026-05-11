# 契約書・請求書自動処理 — Demo Guide

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本デモでは、契約書・請求書の自動処理パイプラインを実演する。OCR によるテキスト抽出とエンティティ抽出を組み合わせ、非構造化文書から構造化データを自動生成する。

**デモの核心メッセージ**: 紙ベースの契約書・請求書を自動でデジタル化し、金額・日付・取引先等の重要情報を即座に抽出・構造化する。

**想定時間**: 3〜5 分

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **役職** | 経理部門マネージャー / 契約管理担当 |
| **日常業務** | 請求書処理、契約書管理、支払承認 |
| **課題** | 大量の紙文書の手動入力に時間がかかる |
| **期待する成果** | 文書処理の自動化と入力ミスの削減 |

### Persona: 山田さん（経理部門リーダー）

- 月次で 200+ 件の請求書を処理
- 手動入力によるミスと遅延が課題
- 「請求書が届いたら自動で金額と支払期日を抽出したい」

---

## Demo Scenario: 請求書バッチ処理

### ワークフロー全体像

```
文書スキャン       OCR 処理        エンティティ       構造化データ
(PDF/画像)   →   テキスト抽出  →   抽出・分類   →    出力 (JSON)
                                   (AI 解析)
```

---

## Storyboard（5 セクション / 3〜5 分）

### Section 1: Problem Statement（0:00–0:45）

**ナレーション要旨**:
> 月次で届く 200 件以上の請求書。手動で金額・日付・取引先を入力するのは時間がかかり、ミスも発生する。

**Key Visual**: 大量の PDF 請求書ファイル一覧

### Section 2: Document Upload（0:45–1:30）

**ナレーション要旨**:
> スキャン済み文書をファイルサーバーに配置するだけで、自動処理パイプラインが起動する。

**Key Visual**: ファイルアップロード → ワークフロー自動起動

### Section 3: OCR & Extraction（1:30–2:30）

**ナレーション要旨**:
> OCR でテキストを抽出し、AI が文書タイプを判定。請求書・契約書・領収書を自動分類し、各文書から重要フィールドを抽出する。

**Key Visual**: OCR 処理進捗、文書分類結果

### Section 4: Structured Output（2:30–3:45）

**ナレーション要旨**:
> 抽出結果を構造化データとして出力。金額、支払期日、取引先名、請求番号等が JSON 形式で利用可能。

**Key Visual**: 抽出結果テーブル（請求番号、金額、期日、取引先）

### Section 5: Validation & Report（3:45–5:00）

**ナレーション要旨**:
> AI が抽出結果の信頼度を評価し、低信頼度の項目をフラグ。処理サマリーレポートで全体の処理状況を把握。

**Key Visual**: 信頼度スコア付き結果、処理サマリーレポート

---

## Screen Capture Plan

| # | 画面 | セクション |
|---|------|-----------|
| 1 | 請求書 PDF ファイル一覧 | Section 1 |
| 2 | ワークフロー自動起動 | Section 2 |
| 3 | OCR 処理・文書分類結果 | Section 3 |
| 4 | 構造化データ出力（JSON/テーブル） | Section 4 |
| 5 | 処理サマリーレポート | Section 5 |

---

## Narration Outline

| セクション | 時間 | キーメッセージ |
|-----------|------|--------------|
| Problem | 0:00–0:45 | 「月 200 件の請求書を手動処理するのは限界」 |
| Upload | 0:45–1:30 | 「ファイル配置だけで自動処理が開始」 |
| OCR | 1:30–2:30 | 「OCR + AI で文書分類とフィールド抽出」 |
| Output | 2:30–3:45 | 「構造化データとして即座に利用可能」 |
| Report | 3:45–5:00 | 「信頼度評価で人的確認が必要な箇所を明示」 |

---

## Sample Data Requirements

| # | データ | 用途 |
|---|--------|------|
| 1 | 請求書 PDF（10 件） | メイン処理対象 |
| 2 | 契約書 PDF（3 件） | 文書分類デモ |
| 3 | 領収書画像（3 件） | 画像 OCR デモ |
| 4 | 低品質スキャン（2 件） | 信頼度評価デモ |

---

## Timeline

### 1 週間以内に達成可能

| タスク | 所要時間 |
|--------|---------|
| サンプル文書準備 | 3 時間 |
| パイプライン実行確認 | 2 時間 |
| 画面キャプチャ取得 | 2 時間 |
| ナレーション原稿作成 | 2 時間 |
| 動画編集 | 4 時間 |

### Future Enhancements

- 会計システムへの自動連携
- 承認ワークフロー統合
- 多言語文書対応（英語・中国語）

---

## Technical Notes

| コンポーネント | 役割 |
|--------------|------|
| Step Functions | ワークフローオーケストレーション |
| Lambda (OCR Processor) | Textract による文書テキスト抽出 |
| Lambda (Entity Extractor) | Bedrock による エンティティ抽出 |
| Lambda (Classifier) | 文書タイプ分類 |
| Amazon Athena | 抽出データの集計分析 |

### フォールバック

| シナリオ | 対応 |
|---------|------|
| OCR 精度低下 | 事前処理済みテキストを使用 |
| Bedrock 遅延 | 事前生成結果を表示 |

---

*本ドキュメントは技術プレゼンテーション用デモ動画の制作ガイドです。*

---

## 出力先について: FSxN S3 Access Point (Pattern A)

UC2 financial-idp は **Pattern A: Native S3AP Output** に分類されます
（`docs/output-destination-patterns.md` 参照）。

**設計**: 請求書 OCR 結果、構造化メタデータ、BedRock サマリーは全て FSxN S3 Access Point 経由で
オリジナル請求書 PDFと**同一の FSx ONTAP ボリューム**に書き戻されます。標準 S3 バケットは
作成されません（"no data movement" パターン）。

**CloudFormation パラメータ**:
- `S3AccessPointAlias`: 入力データ読み取り用 S3 AP Alias
- `S3AccessPointOutputAlias`: 出力書き込み用 S3 AP Alias（入力と同じでも可）

**デプロイ例**:
```bash
aws cloudformation deploy \
  --template-file financial-idp/template-deploy.yaml \
  --stack-name fsxn-financial-idp-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (他の必須パラメータ)
```

**SMB/NFS ユーザーからの見え方**:
```
/vol/invoices/
  ├── 2026/05/invoice_001.pdf          # オリジナル請求書
  └── summaries/2026/05/                # AI 生成サマリー（同じボリューム内）
      └── invoice_001.json
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

- ⚠️ **E2E 検証**: 一部機能のみ（本番環境では追加検証推奨）
- 📸 **UI/UX 撮影**: ✅ SFN Graph 完了（Phase 8 Theme D, commit 081cc66）

### 2026-05-10 再デプロイ検証で撮影（UI/UX 中心）

#### UC2 Step Functions Graph view（SUCCEEDED）

![UC2 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc2-demo/uc2-stepfunctions-graph.png)

Step Functions Graph view は各 Lambda / Parallel / Map ステートの実行状況を
色で可視化するエンドユーザー最重要画面。

### 既存スクリーンショット（Phase 1-6 から該当分）

![UC2 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc2-demo/step-functions-graph-succeeded.png)

### 再検証時の UI/UX 対象画面（推奨撮影リスト）

- S3 出力バケット（textract-results/、comprehend-entities/、reports/）
- Textract OCR 結果 JSON（契約書・請求書から抽出されたフィールド）
- Comprehend エンティティ検出結果（組織名、日付、金額）
- Bedrock 生成の要約レポート

### 撮影ガイド

1. **事前準備**:
   - `bash scripts/verify_phase7_prerequisites.sh` で前提確認（共通 VPC/S3 AP 有無）
   - `UC=financial-idp bash scripts/package_generic_uc.sh` で Lambda パッケージ
   - `bash scripts/deploy_generic_ucs.sh UC2` でデプロイ

2. **サンプルデータ配置**:
   - S3 AP Alias 経由で `invoices/` プレフィックスにサンプルファイルをアップロード
   - Step Functions `fsxn-financial-idp-demo-workflow` を起動（入力 `{}`）

3. **撮影**（CloudShell・ターミナルは閉じる、ブラウザ右上のユーザー名は黒塗り）:
   - S3 出力バケット `fsxn-financial-idp-demo-output-<account>` の俯瞰
   - AI/ML 出力 JSON のプレビュー（`build/preview_*.html` の形式を参考に）
   - SNS メール通知（該当する場合）

4. **マスク処理**:
   - `python3 scripts/mask_uc_demos.py financial-idp-demo` で自動マスク
   - `docs/screenshots/MASK_GUIDE.md` に従って追加マスク（必要に応じて）

5. **クリーンアップ**:
   - `bash scripts/cleanup_generic_ucs.sh UC2` で削除
   - VPC Lambda ENI 解放に 15-30 分（AWS の仕様）
