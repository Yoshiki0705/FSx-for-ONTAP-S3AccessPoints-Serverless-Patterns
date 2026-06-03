# 化学・素材 — SDS 危険分類抽出 / GHS バリデーション Demo Guide

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本デモでは、FSx for ONTAP 上のファイルを S3 Access Points 経由で AI/ML サービスが自動分析するパイプラインを実演します。

**想定時間**: 3〜5 分

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **役職** | 化学メーカー 安全管理責任者 / 研究開発部 ラボマネージャー |
| **日常業務** | SDS（安全データシート）管理、ラボノート記録、規制対応 |
| **課題** | 多言語 SDS の手動管理、ラボノートからのデータ抽出、GHS 対応 |
| **期待する成果** | SDS の自動分類・構造化とラボノートの知見抽出 |

---

## ステップバイステップ デプロイ・検証手順

### Step 1: 前提条件の確認

```bash
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
aws sts get-caller-identity
```

### Step 2: リポジトリのクローンとディレクトリ移動

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/chemical-sds-management
```

### Step 3: テスト用サンプルデータの配置

FSx ONTAP ボリューム上にサンプルデータを配置してください。


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

cp samconfig.toml.example samconfig.toml
# samconfig.toml を編集

sam deploy \
  --stack-name fsxn-chemical-sds-demo \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

### Step 5: ワークフローの手動実行

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-chemical-sds-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text --region ap-northeast-1)

aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --region ap-northeast-1
```

### Step 6: 出力結果の確認

```bash
OUTPUT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name fsxn-chemical-sds-demo \
  --query "Stacks[0].Outputs[?OutputKey=='OutputBucketName'].OutputValue" \
  --output text --region ap-northeast-1)

TODAY=$(date +%Y-%m-%d)
aws s3 ls s3://${OUTPUT_BUCKET}/reports/${TODAY}/ --region ap-northeast-1
```

---

## トラブルシューティング

| 症状 | 原因 | 解決策 |
|------|------|--------|
| Discovery Lambda タイムアウト | S3 AP アクセス失敗 | NetworkOrigin 設定確認 |
| `AccessDenied` | IAM ポリシー ARN 形式誤り | `arn:aws:s3:{region}:{account}:accesspoint/{name}` 形式確認 |
| AI/ML サービスエラー | リージョン設定 | Cross-Region 設定確認 |

---

## クリーンアップ

```bash
aws s3 rm s3://${OUTPUT_BUCKET} --recursive --region ap-northeast-1
aws cloudformation delete-stack --stack-name fsxn-chemical-sds-demo --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-chemical-sds-demo --region ap-northeast-1
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

## 撮影ガイド

### 事前準備

```bash
# Lambda パッケージ作成
cd chemical-sds-management
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

