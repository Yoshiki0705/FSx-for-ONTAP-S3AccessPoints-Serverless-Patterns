# VFX レンダリング品質チェック — Demo Guide

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本デモでは、VFX レンダリング出力の品質チェックパイプラインを実演する。レンダリングフレームの自動検証により、アーティファクトやエラーフレームを早期検出する。

**デモの核心メッセージ**: 大量のレンダリングフレームを自動検証し、品質問題を即座に検出。再レンダリングの判断を迅速化する。

**想定時間**: 3〜5 分

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **役職** | VFX スーパーバイザー / レンダリング TD |
| **日常業務** | レンダリングジョブ管理、品質確認、ショット承認 |
| **課題** | 数千フレームの目視確認に膨大な時間がかかる |
| **期待する成果** | 問題フレームの自動検出と再レンダリング判断の迅速化 |

### Persona: 中村さん（VFX スーパーバイザー）

- 1 プロジェクトで 50+ ショット、各ショット 100〜500 フレーム
- レンダリング完了後の品質確認がボトルネック
- 「黒フレーム、ノイズ過多、テクスチャ欠落を自動で検出したい」

---

## Demo Scenario: レンダリングバッチ品質検証

### ワークフロー全体像

```
レンダリング出力     フレーム解析      品質判定          QC レポート
(EXR/PNG)     →   メタデータ    →   異常検出    →    ショット別
                   抽出             (統計分析)        サマリー
```

---

## Storyboard（5 セクション / 3〜5 分）

### Section 1: Problem Statement（0:00–0:45）

**ナレーション要旨**:
> レンダリングファームから出力された数千フレーム。黒フレーム、ノイズ、テクスチャ欠落等の問題を目視で確認するのは非現実的。

**Key Visual**: レンダリング出力フォルダ（大量の EXR ファイル）

### Section 2: Pipeline Trigger（0:45–1:30）

**ナレーション要旨**:
> レンダリングジョブ完了後、品質チェックパイプラインが自動起動。ショット単位で並列処理。

**Key Visual**: ワークフロー起動、ショット一覧

### Section 3: Frame Analysis（1:30–2:30）

**ナレーション要旨**:
> 各フレームのピクセル統計（平均輝度、分散、ヒストグラム）を算出。フレーム間の一貫性もチェック。

**Key Visual**: フレーム解析処理中、ピクセル統計グラフ

### Section 4: Quality Assessment（2:30–3:45）

**ナレーション要旨**:
> 統計的外れ値を検出し、問題フレームを特定。黒フレーム（輝度ゼロ）、ノイズ過多（分散異常）等を分類。

**Key Visual**: 問題フレーム一覧、カテゴリ別分類

### Section 5: QC Report（3:45–5:00）

**ナレーション要旨**:
> ショット別の QC レポートを生成。再レンダリングが必要なフレーム範囲と推定原因を提示。

**Key Visual**: AI 生成 QC レポート（ショット別サマリー + 推奨対応）

---

## Screen Capture Plan

| # | 画面 | セクション |
|---|------|-----------|
| 1 | レンダリング出力フォルダ | Section 1 |
| 2 | パイプライン起動画面 | Section 2 |
| 3 | フレーム解析進捗 | Section 3 |
| 4 | 問題フレーム検出結果 | Section 4 |
| 5 | QC レポート | Section 5 |

---

## Narration Outline

| セクション | 時間 | キーメッセージ |
|-----------|------|--------------|
| Problem | 0:00–0:45 | 「数千フレームの目視確認は非現実的」 |
| Trigger | 0:45–1:30 | 「レンダリング完了で自動的に QC 開始」 |
| Analysis | 1:30–2:30 | 「ピクセル統計でフレーム品質を定量評価」 |
| Assessment | 2:30–3:45 | 「問題フレームを自動分類・特定」 |
| Report | 3:45–5:00 | 「再レンダリング判断を即座に支援」 |

---

## Sample Data Requirements

| # | データ | 用途 |
|---|--------|------|
| 1 | 正常フレーム（100 枚） | ベースライン |
| 2 | 黒フレーム（3 枚） | 異常検出デモ |
| 3 | ノイズ過多フレーム（5 枚） | 品質判定デモ |
| 4 | テクスチャ欠落フレーム（2 枚） | 分類デモ |

---

## Timeline

### 1 週間以内に達成可能

| タスク | 所要時間 |
|--------|---------|
| サンプルフレームデータ準備 | 3 時間 |
| パイプライン実行確認 | 2 時間 |
| 画面キャプチャ取得 | 2 時間 |
| ナレーション原稿作成 | 2 時間 |
| 動画編集 | 4 時間 |

### Future Enhancements

- ディープラーニングによるアーティファクト検出
- レンダリングファーム連携（自動再レンダリング）
- ショットトラッキングシステム統合

---

## Technical Notes

| コンポーネント | 役割 |
|--------------|------|
| Step Functions | ワークフローオーケストレーション |
| Lambda (Frame Analyzer) | フレームメタデータ・ピクセル統計抽出 |
| Lambda (Quality Checker) | 統計的品質判定 |
| Lambda (Report Generator) | Bedrock による QC レポート生成 |
| Amazon Athena | フレーム統計の集計分析 |

### フォールバック

| シナリオ | 対応 |
|---------|------|
| 大容量フレーム処理遅延 | サムネイル解析に切替 |
| Bedrock 遅延 | 事前生成レポートを表示 |

---

*本ドキュメントは技術プレゼンテーション用デモ動画の制作ガイドです。*

---

## 出力先について: FSxN S3 Access Point (Pattern A)

UC4 media-vfx は **Pattern A: Native S3AP Output** に分類されます
（`docs/output-destination-patterns.md` 参照）。

**設計**: レンダリングメタデータ、フレーム品質評価は全て FSxN S3 Access Point 経由で
オリジナルレンダリングアセットと**同一の FSx ONTAP ボリューム**に書き戻されます。標準 S3 バケットは
作成されません（"no data movement" パターン）。

**CloudFormation パラメータ**:
- `S3AccessPointAlias`: 入力データ読み取り用 S3 AP Alias
- `S3AccessPointOutputAlias`: 出力書き込み用 S3 AP Alias（入力と同じでも可）

**デプロイ例**:
```bash
aws cloudformation deploy \
  --template-file media-vfx/template-deploy.yaml \
  --stack-name fsxn-media-vfx-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (他の必須パラメータ)
```

**SMB/NFS ユーザーからの見え方**:
```
/vol/renders/
  ├── shot_001/frame_0001.exr         # オリジナルレンダーフレーム
  └── qc/shot_001/                     # フレーム品質評価（同じボリューム内）
      └── frame_0001_qc.json
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
- 📸 **UI/UX 再撮影**: 未実施

### 既存スクリーンショット（Phase 1-6 から該当分）

*(該当なし。再検証時に新規撮影してください)*

### 再検証時の UI/UX 対象画面（推奨撮影リスト）

- （再検証時に定義）

### 撮影ガイド

1. **事前準備**:
   - `bash scripts/verify_phase7_prerequisites.sh` で前提確認（共通 VPC/S3 AP 有無）
   - `UC=media-vfx bash scripts/package_generic_uc.sh` で Lambda パッケージ
   - `bash scripts/deploy_generic_ucs.sh UC4` でデプロイ

2. **サンプルデータ配置**:
   - S3 AP Alias 経由で `renders/` プレフィックスにサンプルファイルをアップロード
   - Step Functions `fsxn-media-vfx-demo-workflow` を起動（入力 `{}`）

3. **撮影**（CloudShell・ターミナルは閉じる、ブラウザ右上のユーザー名は黒塗り）:
   - S3 出力バケット `fsxn-media-vfx-demo-output-<account>` の俯瞰
   - AI/ML 出力 JSON のプレビュー（`build/preview_*.html` の形式を参考に）
   - SNS メール通知（該当する場合）

4. **マスク処理**:
   - `python3 scripts/mask_uc_demos.py media-vfx-demo` で自動マスク
   - `docs/screenshots/MASK_GUIDE.md` に従って追加マスク（必要に応じて）

5. **クリーンアップ**:
   - `bash scripts/cleanup_generic_ucs.sh UC4` で削除
   - VPC Lambda ENI 解放に 15-30 分（AWS の仕様）
