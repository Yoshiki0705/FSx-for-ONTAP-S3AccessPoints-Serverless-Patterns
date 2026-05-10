# シーケンシング QC・バリアント集計 — Demo Guide

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本デモでは、次世代シーケンシング（NGS）データの品質管理とバリアント集計パイプラインを実演する。シーケンシング品質を自動検証し、バリアントコール結果を集計・レポート化する。

**デモの核心メッセージ**: シーケンシングデータの QC を自動化し、バリアント集計レポートを即座に生成。解析の信頼性を担保する。

**想定時間**: 3〜5 分

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **役職** | バイオインフォマティシャン / ゲノム解析研究者 |
| **日常業務** | シーケンシングデータ QC、バリアントコール、結果解釈 |
| **課題** | 大量サンプルの QC を手動で確認するのは時間がかかる |
| **期待する成果** | QC 自動化とバリアント集計の効率化 |

### Persona: 加藤さん（バイオインフォマティシャン）

- 週に 100+ サンプルのシーケンシングデータを処理
- QC 基準を満たさないサンプルの早期検出が必要
- 「QC パスしたサンプルだけを自動で下流解析に送りたい」

---

## Demo Scenario: シーケンシングバッチ QC

### ワークフロー全体像

```
FASTQ/BAM ファイル    QC 解析        品質判定         バリアント集計
(100+ サンプル)  →   メトリクス  →   Pass/Fail   →   レポート生成
                     算出            フィルタ
```

---

## Storyboard（5 セクション / 3〜5 分）

### Section 1: Problem Statement（0:00–0:45）

**ナレーション要旨**:
> 週 100 サンプル以上のシーケンシングデータ。品質の悪いサンプルが下流解析に混入すると、結果全体の信頼性が低下する。

**Key Visual**: シーケンシングデータファイル一覧

### Section 2: Pipeline Trigger（0:45–1:30）

**ナレーション要旨**:
> シーケンシングラン完了後、QC パイプラインが自動起動。全サンプルを並列処理。

**Key Visual**: ワークフロー起動、サンプル一覧

### Section 3: QC Metrics（1:30–2:30）

**ナレーション要旨**:
> 各サンプルの QC メトリクスを算出: リード数、Q30 率、マッピング率、カバレッジ深度、重複率。

**Key Visual**: QC メトリクス算出処理中、メトリクス一覧

### Section 4: Quality Filtering（2:30–3:45）

**ナレーション要旨**:
> QC 基準に基づいて Pass/Fail を判定。Fail サンプルの原因を分類（低品質リード、低カバレッジ等）。

**Key Visual**: Pass/Fail 判定結果、Fail 原因分類

### Section 5: Variant Summary（3:45–5:00）

**ナレーション要旨**:
> QC パスサンプルのバリアントコール結果を集計。サンプル間比較、バリアント分布、AI サマリーレポートを生成。

**Key Visual**: バリアント集計レポート（統計サマリー + AI 解釈）

---

## Screen Capture Plan

| # | 画面 | セクション |
|---|------|-----------|
| 1 | シーケンシングデータ一覧 | Section 1 |
| 2 | パイプライン起動画面 | Section 2 |
| 3 | QC メトリクス結果 | Section 3 |
| 4 | Pass/Fail 判定結果 | Section 4 |
| 5 | バリアント集計レポート | Section 5 |

---

## Narration Outline

| セクション | 時間 | キーメッセージ |
|-----------|------|--------------|
| Problem | 0:00–0:45 | 「低品質サンプルの混入は解析全体の信頼性を損なう」 |
| Trigger | 0:45–1:30 | 「ラン完了で自動的に QC 開始」 |
| Metrics | 1:30–2:30 | 「主要 QC メトリクスを全サンプルで算出」 |
| Filtering | 2:30–3:45 | 「基準に基づき Pass/Fail を自動判定」 |
| Summary | 3:45–5:00 | 「バリアント集計と AI サマリーを即座に生成」 |

---

## Sample Data Requirements

| # | データ | 用途 |
|---|--------|------|
| 1 | 高品質 FASTQ メトリクス（20 サンプル） | ベースライン |
| 2 | 低品質サンプル（Q30 < 80%、3 件） | Fail 検出デモ |
| 3 | 低カバレッジサンプル（2 件） | 分類デモ |
| 4 | バリアントコール結果（VCF サマリー） | 集計デモ |

---

## Timeline

### 1 週間以内に達成可能

| タスク | 所要時間 |
|--------|---------|
| サンプル QC データ準備 | 3 時間 |
| パイプライン実行確認 | 2 時間 |
| 画面キャプチャ取得 | 2 時間 |
| ナレーション原稿作成 | 2 時間 |
| 動画編集 | 4 時間 |

### Future Enhancements

- リアルタイムシーケンシング監視
- 臨床レポート自動生成
- マルチオミクス統合解析

---

## Technical Notes

| コンポーネント | 役割 |
|--------------|------|
| Step Functions | ワークフローオーケストレーション |
| Lambda (QC Calculator) | シーケンシング QC メトリクス算出 |
| Lambda (Quality Filter) | Pass/Fail 判定・分類 |
| Lambda (Variant Aggregator) | バリアント集計 |
| Lambda (Report Generator) | Bedrock によるサマリーレポート生成 |

### フォールバック

| シナリオ | 対応 |
|---------|------|
| 大容量データ処理遅延 | サブセットで実行 |
| Bedrock 遅延 | 事前生成レポートを表示 |

---

*本ドキュメントは技術プレゼンテーション用デモ動画の制作ガイドです。*

---

## 検証済みの UI/UX スクリーンショット

Phase 7 UC15/16/17 と UC6/11/14 のデモと同じ方針で、**エンドユーザーが日常業務で実際に
見る UI/UX 画面**を対象とする。技術者向けビュー（Step Functions グラフ、CloudFormation
スタックイベント等）は `docs/verification-results-*.md` に集約。

### このユースケースの検証ステータス

- ✅ **E2E 実行**: Phase 1-6 で確認済み（根 README 参照）
- 📸 **UI/UX 再撮影**: 未実施（本セッションでは UC6/UC11/UC14 を代表として撮影）
- 🔄 **再現方法**: 本ドキュメント末尾の「撮影ガイド」を参照

### 既存スクリーンショット（Phase 1-6 から該当分）

#### UC7 Comprehend Medical ゲノミクス解析結果（Cross-Region us-east-1）

![UC7 Comprehend Medical ゲノミクス解析結果（Cross-Region us-east-1）](../../docs/screenshots/masked/phase2/phase2-comprehend-medical-genomics-analysis-fullpage.png)


### 再検証時の UI/UX 対象画面（推奨撮影リスト）

- S3 出力バケット（fastq-qc/、variant-summary/、entities/）
- Athena クエリ結果（バリアント頻度集計）
- Comprehend Medical 医学エンティティ（Genes, Diseases, Mutations）
- Bedrock 生成の研究レポート

### 撮影ガイド

1. **事前準備**:
   - `bash scripts/verify_phase7_prerequisites.sh` で前提確認（共通 VPC/S3 AP 有無）
   - `UC=genomics-pipeline bash scripts/package_generic_uc.sh` で Lambda パッケージ
   - `bash scripts/deploy_generic_ucs.sh UC7` でデプロイ

2. **サンプルデータ配置**:
   - S3 AP Alias 経由で `fastq/` プレフィックスにサンプルファイルをアップロード
   - Step Functions `fsxn-genomics-pipeline-demo-workflow` を起動（入力 `{}`）

3. **撮影**（CloudShell・ターミナルは閉じる、ブラウザ右上のユーザー名は黒塗り）:
   - S3 出力バケット `fsxn-genomics-pipeline-demo-output-<account>` の俯瞰
   - AI/ML 出力 JSON のプレビュー（`build/preview_*.html` の形式を参考に）
   - SNS メール通知（該当する場合）

4. **マスク処理**:
   - `python3 scripts/mask_uc_demos.py genomics-pipeline-demo` で自動マスク
   - `docs/screenshots/MASK_GUIDE.md` に従って追加マスク（必要に応じて）

5. **クリーンアップ**:
   - `bash scripts/cleanup_generic_ucs.sh UC7` で削除
   - VPC Lambda ENI 解放に 15-30 分（AWS の仕様）
