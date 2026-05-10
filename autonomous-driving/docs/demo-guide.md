# 走行データ前処理・アノテーション — Demo Guide

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本デモでは、自動運転開発における走行データの前処理とアノテーションパイプラインを実演する。大量のセンサーデータを自動分類・品質チェックし、学習データセットを効率的に構築する。

**デモの核心メッセージ**: 走行データの品質検証とメタデータ付与を自動化し、AI 学習用データセット構築を加速する。

**想定時間**: 3〜5 分

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **役職** | データエンジニア / ML エンジニア |
| **日常業務** | 走行データ管理、アノテーション、学習データセット構築 |
| **課題** | 大量の走行データから有用なシーンを効率的に抽出できない |
| **期待する成果** | データ品質の自動検証とシーン分類の効率化 |

### Persona: 伊藤さん（データエンジニア）

- 毎日 TB 単位の走行データが蓄積
- カメラ・LiDAR・レーダーの同期確認が手動
- 「品質の良いデータだけを自動で学習パイプラインに送りたい」

---

## Demo Scenario: 走行データバッチ前処理

### ワークフロー全体像

```
走行データ        データ検証       シーン分類        データセット
(ROS bag等)  →   品質チェック  →  メタデータ   →   カタログ生成
                  同期確認        付与 (AI)
```

---

## Storyboard（5 セクション / 3〜5 分）

### Section 1: Problem Statement（0:00–0:45）

**ナレーション要旨**:
> 毎日 TB 単位で蓄積される走行データ。品質の悪いデータ（センサー欠損、同期ずれ）が混在し、手動での選別は非現実的。

**Key Visual**: 走行データフォルダ構造、データ量の可視化

### Section 2: Pipeline Trigger（0:45–1:30）

**ナレーション要旨**:
> 新規走行データがアップロードされると、前処理パイプラインが自動起動。

**Key Visual**: データアップロード → ワークフロー自動起動

### Section 3: Quality Validation（1:30–2:30）

**ナレーション要旨**:
> センサーデータの完全性チェック: フレーム欠損、タイムスタンプ同期、データ破損を自動検出。

**Key Visual**: 品質チェック結果 — センサー別の健全性スコア

### Section 4: Scene Classification（2:30–3:45）

**ナレーション要旨**:
> AI がシーンを自動分類: 交差点、高速道路、悪天候、夜間等。メタデータとして付与。

**Key Visual**: シーン分類結果テーブル、カテゴリ別分布

### Section 5: Dataset Catalog（3:45–5:00）

**ナレーション要旨**:
> 品質検証済みデータのカタログを自動生成。シーン条件で検索可能なデータセットとして利用可能に。

**Key Visual**: データセットカタログ、検索インターフェース

---

## Screen Capture Plan

| # | 画面 | セクション |
|---|------|-----------|
| 1 | 走行データフォルダ構造 | Section 1 |
| 2 | パイプライン起動画面 | Section 2 |
| 3 | 品質チェック結果 | Section 3 |
| 4 | シーン分類結果 | Section 4 |
| 5 | データセットカタログ | Section 5 |

---

## Narration Outline

| セクション | 時間 | キーメッセージ |
|-----------|------|--------------|
| Problem | 0:00–0:45 | 「TB 単位のデータから有用なシーンを手動選別は不可能」 |
| Trigger | 0:45–1:30 | 「アップロードで自動的に前処理開始」 |
| Validation | 1:30–2:30 | 「センサー欠損・同期ずれを自動検出」 |
| Classification | 2:30–3:45 | 「AI がシーンを自動分類しメタデータ付与」 |
| Catalog | 3:45–5:00 | 「検索可能なデータセットカタログを自動生成」 |

---

## Sample Data Requirements

| # | データ | 用途 |
|---|--------|------|
| 1 | 正常走行データ（5 セッション） | ベースライン |
| 2 | フレーム欠損データ（2 件） | 品質チェックデモ |
| 3 | 多様なシーンデータ（交差点、高速、夜間） | 分類デモ |

---

## Timeline

### 1 週間以内に達成可能

| タスク | 所要時間 |
|--------|---------|
| サンプル走行データ準備 | 3 時間 |
| パイプライン実行確認 | 2 時間 |
| 画面キャプチャ取得 | 2 時間 |
| ナレーション原稿作成 | 2 時間 |
| 動画編集 | 4 時間 |

### Future Enhancements

- 3D アノテーション自動生成
- アクティブラーニングによるデータ選択
- データバージョニング統合

---

## Technical Notes

| コンポーネント | 役割 |
|--------------|------|
| Step Functions | ワークフローオーケストレーション |
| Lambda (Python 3.13) | センサーデータ品質検証、シーン分類、カタログ生成 |
| Lambda SnapStart | コールドスタート削減（`EnableSnapStart=true` でオプトイン） |
| SageMaker (4-way routing) | 推論（Batch / Serverless / Provisioned / Inference Components） |
| SageMaker Inference Components | 真の scale-to-zero（`EnableInferenceComponents=true`） |
| Amazon Bedrock | シーン分類・アノテーション提案 |
| Amazon Athena | メタデータ検索・集計 |
| CloudFormation Guard Hooks | デプロイ時セキュリティポリシー強制 |

### ローカルテスト (Phase 6A)

```bash
# SAM CLI でローカルテスト
sam local invoke \
  --template autonomous-driving/template-deploy.yaml \
  --event events/uc09-autonomous-driving/discovery-event.json \
  --env-vars events/env.json \
  DiscoveryFunction
```

### フォールバック

| シナリオ | 対応 |
|---------|------|
| 大容量データ処理遅延 | サブセットで実行 |
| 分類精度不足 | 事前分類済み結果を表示 |

---

*本ドキュメントは技術プレゼンテーション用デモ動画の制作ガイドです。*

---

## 検証済みの UI/UX スクリーンショット

Phase 7 UC15/16/17 と UC6/11/14 のデモと同じ方針で、**エンドユーザーが日常業務で実際に
見る UI/UX 画面**を対象とする。技術者向けビュー（Step Functions グラフ、CloudFormation
スタックイベント等）は `docs/verification-results-*.md` に集約。

### このユースケースの検証ステータス

- ⚠️ **E2E 検証**: 一部機能のみ（本番環境では追加検証推奨）
- 📸 **UI/UX 再撮影**: 未実施

### 既存スクリーンショット（Phase 1-6 から該当分）

*(該当なし。再検証時に新規撮影してください)*

### 再検証時の UI/UX 対象画面（推奨撮影リスト）

- S3 出力バケット（keyframes/、annotations/、qc/）
- Rekognition キーフレーム物体検出結果
- LiDAR 点群品質チェックサマリー
- COCO 互換アノテーション JSON

### 撮影ガイド

1. **事前準備**:
   - `bash scripts/verify_phase7_prerequisites.sh` で前提確認（共通 VPC/S3 AP 有無）
   - `UC=autonomous-driving bash scripts/package_generic_uc.sh` で Lambda パッケージ
   - `bash scripts/deploy_generic_ucs.sh UC9` でデプロイ

2. **サンプルデータ配置**:
   - S3 AP Alias 経由で `footage/` プレフィックスにサンプルファイルをアップロード
   - Step Functions `fsxn-autonomous-driving-demo-workflow` を起動（入力 `{}`）

3. **撮影**（CloudShell・ターミナルは閉じる、ブラウザ右上のユーザー名は黒塗り）:
   - S3 出力バケット `fsxn-autonomous-driving-demo-output-<account>` の俯瞰
   - AI/ML 出力 JSON のプレビュー（`build/preview_*.html` の形式を参考に）
   - SNS メール通知（該当する場合）

4. **マスク処理**:
   - `python3 scripts/mask_uc_demos.py autonomous-driving-demo` で自動マスク
   - `docs/screenshots/MASK_GUIDE.md` に従って追加マスク（必要に応じて）

5. **クリーンアップ**:
   - `bash scripts/cleanup_generic_ucs.sh UC9` で削除
   - VPC Lambda ENI 解放に 15-30 分（AWS の仕様）
