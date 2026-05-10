# 検層データ異常検知・コンプライアンスレポート — Demo Guide

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本デモでは、坑井検層データの異常検知とコンプライアンスレポート生成パイプラインを実演する。検層データの品質問題を自動検出し、規制報告書を効率的に作成する。

**デモの核心メッセージ**: 検層データの異常を自動検知し、規制要件に準拠したコンプライアンスレポートを即座に生成する。

**想定時間**: 3〜5 分

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **役職** | 地質エンジニア / データアナリスト / コンプライアンス担当 |
| **日常業務** | 検層データ解析、坑井評価、規制報告書作成 |
| **課題** | 大量の検層データから異常を手動で検出するのは時間がかかる |
| **期待する成果** | データ品質の自動検証と規制レポートの効率化 |

### Persona: 松本さん（地質エンジニア）

- 50+ 坑井の検層データを管理
- 規制当局への定期報告が必要
- 「データ異常を自動検出し、レポート作成を効率化したい」

---

## Demo Scenario: 検層データバッチ分析

### ワークフロー全体像

```
検層データ        データ検証       異常検知          コンプライアンス
(LAS/DLIS)   →   品質チェック  →  統計分析    →    レポート生成
                  フォーマット     外れ値検出
```

---

## Storyboard（5 セクション / 3〜5 分）

### Section 1: Problem Statement（0:00–0:45）

**ナレーション要旨**:
> 50 坑井分の検層データを定期的に品質検証し、規制当局に報告する必要がある。手動分析では見落としリスクが高い。

**Key Visual**: 検層データファイル一覧（LAS/DLIS 形式）

### Section 2: Data Ingestion（0:45–1:30）

**ナレーション要旨**:
> 検層データファイルをアップロードし、品質検証パイプラインを起動。フォーマット検証から開始。

**Key Visual**: ワークフロー起動、データフォーマット検証

### Section 3: Anomaly Detection（1:30–2:30）

**ナレーション要旨**:
> 各検層カーブ（GR, SP, Resistivity 等）に対して統計的異常検知を実行。深度区間ごとの外れ値を検出。

**Key Visual**: 異常検知処理中、検層カーブの異常ハイライト

### Section 4: Results Review（2:30–3:45）

**ナレーション要旨**:
> 検出された異常を坑井別・カーブ別に確認。異常の種類（スパイク、欠損、範囲逸脱）を分類。

**Key Visual**: 異常検出結果テーブル、坑井別サマリー

### Section 5: Compliance Report（3:45–5:00）

**ナレーション要旨**:
> AI が規制要件に準拠したコンプライアンスレポートを自動生成。データ品質サマリー、異常対応記録、推奨アクションを含む。

**Key Visual**: コンプライアンスレポート（規制フォーマット準拠）

---

## Screen Capture Plan

| # | 画面 | セクション |
|---|------|-----------|
| 1 | 検層データファイル一覧 | Section 1 |
| 2 | パイプライン起動・フォーマット検証 | Section 2 |
| 3 | 異常検知処理結果 | Section 3 |
| 4 | 坑井別異常サマリー | Section 4 |
| 5 | コンプライアンスレポート | Section 5 |

---

## Narration Outline

| セクション | 時間 | キーメッセージ |
|-----------|------|--------------|
| Problem | 0:00–0:45 | 「50 坑井の検層データ品質検証を手動で行うのは限界」 |
| Ingestion | 0:45–1:30 | 「データアップロードで自動的に検証開始」 |
| Detection | 1:30–2:30 | 「統計的手法で各カーブの異常を検出」 |
| Results | 2:30–3:45 | 「坑井別・カーブ別に異常を分類・確認」 |
| Report | 3:45–5:00 | 「規制準拠のレポートを AI が自動生成」 |

---

## Sample Data Requirements

| # | データ | 用途 |
|---|--------|------|
| 1 | 正常検層データ（LAS 形式、10 坑井） | ベースライン |
| 2 | スパイク異常データ（3 件） | 異常検知デモ |
| 3 | 欠損区間データ（2 件） | 品質チェックデモ |
| 4 | 範囲逸脱データ（2 件） | 分類デモ |

---

## Timeline

### 1 週間以内に達成可能

| タスク | 所要時間 |
|--------|---------|
| サンプル検層データ準備 | 3 時間 |
| パイプライン実行確認 | 2 時間 |
| 画面キャプチャ取得 | 2 時間 |
| ナレーション原稿作成 | 2 時間 |
| 動画編集 | 4 時間 |

### Future Enhancements

- リアルタイム掘削データ監視
- 地層対比の自動化
- 3D 地質モデル連携

---

## Technical Notes

| コンポーネント | 役割 |
|--------------|------|
| Step Functions | ワークフローオーケストレーション |
| Lambda (LAS Parser) | 検層データフォーマット解析 |
| Lambda (Anomaly Detector) | 統計的異常検知 |
| Lambda (Report Generator) | Bedrock によるコンプライアンスレポート生成 |
| Amazon Athena | 検層データの集計分析 |

### フォールバック

| シナリオ | 対応 |
|---------|------|
| LAS パース失敗 | 事前解析済みデータを使用 |
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
- 📸 **UI/UX 再撮影**: ✅ 2026-05-10 再デプロイ検証で撮影済み （UC8 Step Functions グラフ、Lambda 実行成功を確認）
- 🔄 **再現方法**: 本ドキュメント末尾の「撮影ガイド」を参照

### 2026-05-10 再デプロイ検証で撮影（UI/UX 中心）

#### UC8 Step Functions Graph view（SUCCEEDED）

![UC8 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc8-demo/uc8-stepfunctions-graph.png)

Step Functions Graph view は各 Lambda / Parallel / Map ステートの実行状況を
色で可視化するエンドユーザー最重要画面。

### 既存スクリーンショット（Phase 1-6 から該当分）

*(該当なし。再検証時に新規撮影してください)*

### 再検証時の UI/UX 対象画面（推奨撮影リスト）

- S3 出力バケット（segy-metadata/、anomalies/、reports/）
- Athena クエリ結果（SEG-Y メタデータ統計）
- Rekognition 坑井ログ画像ラベル
- 異常検知レポート

### 撮影ガイド

1. **事前準備**:
   - `bash scripts/verify_phase7_prerequisites.sh` で前提確認（共通 VPC/S3 AP 有無）
   - `UC=energy-seismic bash scripts/package_generic_uc.sh` で Lambda パッケージ
   - `bash scripts/deploy_generic_ucs.sh UC8` でデプロイ

2. **サンプルデータ配置**:
   - S3 AP Alias 経由で `seismic/` プレフィックスにサンプルファイルをアップロード
   - Step Functions `fsxn-energy-seismic-demo-workflow` を起動（入力 `{}`）

3. **撮影**（CloudShell・ターミナルは閉じる、ブラウザ右上のユーザー名は黒塗り）:
   - S3 出力バケット `fsxn-energy-seismic-demo-output-<account>` の俯瞰
   - AI/ML 出力 JSON のプレビュー（`build/preview_*.html` の形式を参考に）
   - SNS メール通知（該当する場合）

4. **マスク処理**:
   - `python3 scripts/mask_uc_demos.py energy-seismic-demo` で自動マスク
   - `docs/screenshots/MASK_GUIDE.md` に従って追加マスク（必要に応じて）

5. **クリーンアップ**:
   - `bash scripts/cleanup_generic_ucs.sh UC8` で削除
   - VPC Lambda ENI 解放に 15-30 分（AWS の仕様）
