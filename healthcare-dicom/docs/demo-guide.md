# DICOM 匿名化ワークフロー — Demo Guide

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本デモでは、医療画像（DICOM）の匿名化ワークフローを実演する。研究データ共有のために患者個人情報を自動除去し、匿名化品質を検証するプロセスを示す。

**デモの核心メッセージ**: DICOM ファイルから患者識別情報を自動除去し、研究利用可能な匿名化データセットを安全に生成する。

**想定時間**: 3〜5 分

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **役職** | 医療情報管理者 / 臨床研究データマネージャー |
| **日常業務** | 医療画像管理、研究データ提供、プライバシー保護 |
| **課題** | 大量の DICOM ファイルの手動匿名化は時間がかかりミスのリスクがある |
| **期待する成果** | 安全で確実な匿名化と監査証跡の自動化 |

### Persona: 高橋さん（臨床研究データマネージャー）

- 多施設共同研究で 10,000+ DICOM ファイルの匿名化が必要
- 患者名、ID、生年月日等の確実な除去が求められる
- 「匿名化漏れゼロを保証しつつ、画像品質は維持したい」

---

## Demo Scenario: 研究データ共有のための DICOM 匿名化

### ワークフロー全体像

```
DICOM ファイル     タグ解析        匿名化処理        品質検証
(患者情報含む) →  メタデータ   →   個人情報除去  →   匿名化確認
                  抽出            ハッシュ化        レポート生成
```

---

## Storyboard（5 セクション / 3〜5 分）

### Section 1: Problem Statement（0:00–0:45）

**ナレーション要旨**:
> 多施設共同研究のために 10,000 件の DICOM ファイルを匿名化する必要がある。手動処理ではミスのリスクがあり、個人情報漏洩は許されない。

**Key Visual**: DICOM ファイル一覧、患者情報タグのハイライト

### Section 2: Workflow Trigger（0:45–1:30）

**ナレーション要旨**:
> 匿名化対象のデータセットを指定し、匿名化ワークフローを起動。匿名化ルール（除去・ハッシュ化・一般化）を設定。

**Key Visual**: ワークフロー起動、匿名化ルール設定画面

### Section 3: De-identification（1:30–2:30）

**ナレーション要旨**:
> 各 DICOM ファイルの個人情報タグを自動処理。患者名→ハッシュ、生年月日→年齢範囲、施設名→匿名コード。画像ピクセルデータは保持。

**Key Visual**: 匿名化処理進捗、タグ変換の before/after

### Section 4: Quality Verification（2:30–3:45）

**ナレーション要旨**:
> 匿名化後のファイルを自動検証。残存する個人情報がないか全タグをスキャン。画像の整合性も確認。

**Key Visual**: 検証結果 — 匿名化成功率、残存リスクタグ一覧

### Section 5: Audit Report（3:45–5:00）

**ナレーション要旨**:
> 匿名化処理の監査レポートを自動生成。処理件数、除去タグ数、検証結果を記録。研究倫理委員会への提出資料として利用可能。

**Key Visual**: 監査レポート（処理サマリー + コンプライアンス証跡）

---

## Screen Capture Plan

| # | 画面 | セクション |
|---|------|-----------|
| 1 | DICOM ファイル一覧（匿名化前） | Section 1 |
| 2 | ワークフロー起動・ルール設定 | Section 2 |
| 3 | 匿名化処理進捗 | Section 3 |
| 4 | 品質検証結果 | Section 4 |
| 5 | 監査レポート | Section 5 |

---

## Narration Outline

| セクション | 時間 | キーメッセージ |
|-----------|------|--------------|
| Problem | 0:00–0:45 | 「大量 DICOM の匿名化漏れは許されない」 |
| Trigger | 0:45–1:30 | 「匿名化ルールを設定してワークフロー起動」 |
| Processing | 1:30–2:30 | 「個人情報タグを自動除去、画像品質は維持」 |
| Verification | 2:30–3:45 | 「全タグスキャンで匿名化漏れゼロを確認」 |
| Report | 3:45–5:00 | 「監査証跡を自動生成、倫理委員会に提出可能」 |

---

## Sample Data Requirements

| # | データ | 用途 |
|---|--------|------|
| 1 | テスト DICOM ファイル（20 件） | メイン処理対象 |
| 2 | 複雑なタグ構造の DICOM（5 件） | エッジケース |
| 3 | プライベートタグ含む DICOM（3 件） | 高リスク検証 |

---

## Timeline

### 1 週間以内に達成可能

| タスク | 所要時間 |
|--------|---------|
| テスト DICOM データ準備 | 3 時間 |
| パイプライン実行確認 | 2 時間 |
| 画面キャプチャ取得 | 2 時間 |
| ナレーション原稿作成 | 2 時間 |
| 動画編集 | 4 時間 |

### Future Enhancements

- 画像内テキスト（バーンイン）の自動検出・除去
- FHIR 連携による匿名化マッピング管理
- 差分匿名化（追加データの増分処理）

---

## Technical Notes

| コンポーネント | 役割 |
|--------------|------|
| Step Functions | ワークフローオーケストレーション |
| Lambda (Tag Parser) | DICOM タグ解析・個人情報検出 |
| Lambda (De-identifier) | タグ匿名化処理 |
| Lambda (Verifier) | 匿名化品質検証 |
| Lambda (Report Generator) | 監査レポート生成 |

### フォールバック

| シナリオ | 対応 |
|---------|------|
| DICOM パース失敗 | 事前処理済みデータを使用 |
| 検証エラー | 手動確認フローに切替 |

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

- S3 出力バケット（dicom-metadata/、deid-reports/、diagnoses/）
- Comprehend Medical エンティティ検出結果（Cross-Region）
- DICOM 匿名化済みメタデータ JSON

### 撮影ガイド

1. **事前準備**:
   - `bash scripts/verify_phase7_prerequisites.sh` で前提確認（共通 VPC/S3 AP 有無）
   - `UC=healthcare-dicom bash scripts/package_generic_uc.sh` で Lambda パッケージ
   - `bash scripts/deploy_generic_ucs.sh UC5` でデプロイ

2. **サンプルデータ配置**:
   - S3 AP Alias 経由で `dicom/` プレフィックスにサンプルファイルをアップロード
   - Step Functions `fsxn-healthcare-dicom-demo-workflow` を起動（入力 `{}`）

3. **撮影**（CloudShell・ターミナルは閉じる、ブラウザ右上のユーザー名は黒塗り）:
   - S3 出力バケット `fsxn-healthcare-dicom-demo-output-<account>` の俯瞰
   - AI/ML 出力 JSON のプレビュー（`build/preview_*.html` の形式を参考に）
   - SNS メール通知（該当する場合）

4. **マスク処理**:
   - `python3 scripts/mask_uc_demos.py healthcare-dicom-demo` で自動マスク
   - `docs/screenshots/MASK_GUIDE.md` に従って追加マスク（必要に応じて）

5. **クリーンアップ**:
   - `bash scripts/cleanup_generic_ucs.sh UC5` で削除
   - VPC Lambda ENI 解放に 15-30 分（AWS の仕様）
