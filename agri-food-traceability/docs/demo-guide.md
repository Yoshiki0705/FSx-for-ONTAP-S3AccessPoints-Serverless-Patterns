# 農業・食品 — 農地航空画像分析 / トレーサビリティ文書管理 Demo Guide

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本デモでは、農地ドローン画像の作物異常検出とトレーサビリティ文書の自動分類パイプラインを実演する。Rekognition/Bedrock による植生分析と Textract/Comprehend によるロット情報抽出で、食品安全管理を自動化する。

**デモの核心メッセージ**: ドローン画像から作物の異常を AI が自動検出し、トレーサビリティ文書をロット別に自動分類・構造化する。

**想定時間**: 3〜5 分

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
cd fsxn-s3ap-serverless-patterns/agri-food-traceability
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
# FSx ONTAP NFS マウント
sudo mount -t nfs <FSxN-DATA-LIF-IP>:/vol1 /mnt/fsxn

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
