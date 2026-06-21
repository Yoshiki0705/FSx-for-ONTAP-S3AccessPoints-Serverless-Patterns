# 農業・食品 — 農地航空画像分析 / トレーサビリティ文書管理 Demo Guide

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本デモでは、農地ドローン画像の作物異常検出とトレーサビリティ文書の自動分類パイプラインを実演する。Rekognition/Bedrock による植生分析と Textract/Comprehend によるロット情報抽出で、食品安全管理を自動化する。

**デモの核心メッセージ**: ドローン画像から作物の異常を AI が自動検出し、トレーサビリティ文書をロット別に自動分類・構造化する。

**想定時間**: 3〜5 分

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **役職** | 農業法人 品質管理部長 / 食品メーカー トレーサビリティ担当 |
| **日常業務** | 農地モニタリング、産地証明管理、トレーサビリティ文書管理 |
| **課題** | 大量の圃場画像と出荷文書の手動管理、産地偽装リスクの早期検出 |
| **期待する成果** | 航空画像の自動分析とトレーサビリティ文書のデジタル化 |

---

## ステップバイステップ デプロイ・検証手順

### Step 1: 前提条件の確認

```bash
aws --version && sam --version && python3 --version
aws sts get-caller-identity
```

### Step 2: リポジトリのクローンとディレクトリ移動

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/solutions/industry/agri-food-traceability
```

### Step 3: テスト用サンプルデータの配置

```
/aerial/
  field-A/2026-06-01/drone-001.tiff   # GeoTIFF（GPS メタデータ付き）
  field-B/2026-06-01/drone-002.jpg    # JPEG with EXIF GPS
/traceability/
  harvest/lot-2026-001.pdf            # 収穫記録
  shipping/manifest-2026-001.pdf      # 出荷マニフェスト
  inspection/cert-2026-001.pdf        # 検査証明書
```


**NFS マウントとファイル配置例:**

```bash
# FSx for ONTAP NFS マウント
sudo mount -t nfs <FSx-ONTAP-DATA-LIF-IP>:/vol1 /mnt/fsxn

# サンプルデータ配置
cp -r sample-data/* /mnt/fsxn/<prefix>/
```

### Step 4: SAM ビルドとデプロイ

```bash
sam build
sam deploy \
  --stack-name fsxn-agri-demo \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

### Step 5: ワークフロー実行と結果確認

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-agri-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text --region ap-northeast-1)

aws stepfunctions start-execution --state-machine-arn $STATE_MACHINE_ARN --region ap-northeast-1
```

---

## 検証チェックリスト

| チェック項目 | 期待される結果 |
|------------|--------------|
| 画像検出 | GeoTIFF/JPEG ファイルが検出される |
| 作物異常分析 | 信頼度 ≥ 0.70 の異常が分類される |
| 位置情報未検証 | GPS 欠損画像が "location-unverified" になる |
| トレーサビリティ抽出 | ロット ID、日付、産地が抽出される |
| 低信頼度文書 | < 0.80 の文書が "review-required" になる |
| レポート生成 | 120 秒以内に完了 |

---

## クリーンアップ

```bash
aws cloudformation delete-stack --stack-name fsxn-agri-demo --region ap-northeast-1
```

---

*本ドキュメントは技術プレゼンテーション用デモ動画の制作ガイドです。*
---

## 出力先について: OutputDestination で選択可能

本パターンは `OutputDestination` パラメータで AI 成果物の書き込み先を選択できます。

| モード | 説明 |
|--------|------|
| `STANDARD_S3`（デフォルト） | 新しい S3 バケットに書き込み |
| `FSXN_S3AP` | FSx for ONTAP S3 AP 経由で同一ボリュームに書き戻し（NFS/SMB ユーザーが直接参照可能） |

```bash
# STANDARD_S3 モード（デフォルト）
sam deploy --parameter-overrides OutputDestination=STANDARD_S3 ...

# FSXN_S3AP モード（no data movement）
sam deploy --parameter-overrides OutputDestination=FSXN_S3AP OutputS3APPrefix=ai-outputs/ ...
```

詳細は [output-destination-patterns.md](../../docs/output-destination-patterns.md) を参照。

---

## 検証済みの UI/UX スクリーンショット

### 検証ステータス

- ⏳ **E2E 検証**: 未実施（デプロイ・実行予定）
- 📸 **UI/UX 撮影**: 未実施（検証後に撮影予定）

### 推奨撮影リスト

以下の画面を検証時に撮影する予定です:

- Step Functions ワークフロー実行成功画面
- S3 出力バケットのディレクトリ構造
- AI/ML 処理結果の JSON プレビュー
- SNS 通知メール
- CloudWatch メトリクスダッシュボード

---


![Step Functions Graph View (SUCCEEDED)](../../docs/screenshots/masked/uc21-demo/step-functions-graph-view.png)

## 撮影ガイド

### 事前準備

```bash
# Lambda パッケージ作成
cd solutions/industry/agri-food-traceability
sam build

# デプロイ
sam deploy --guided
```

### 撮影手順

1. **サンプルデータ配置**: S3 AP 経由でテストファイルをアップロード
2. **ワークフロー実行**: Step Functions を手動実行
3. **画面撮影**:
   - Step Functions 実行グラフ（SUCCEEDED 状態）
   - S3 出力バケットの俯瞰
   - AI 処理結果 JSON のプレビュー
   - SNS 通知メール（受信確認）
4. **マスク処理**: `python3 scripts/mask_uc_demos.py <stack-name>` で自動マスク

### マスク対象

- AWS アカウント ID（12 桁）
- リソース ID（vpc-xxx, subnet-xxx 等）
- IP アドレス
- メールアドレス
- ブラウザのユーザー名表示

> 詳細は [`docs/screenshots/MASK_GUIDE.md`](../../docs/screenshots/MASK_GUIDE.md) を参照。

