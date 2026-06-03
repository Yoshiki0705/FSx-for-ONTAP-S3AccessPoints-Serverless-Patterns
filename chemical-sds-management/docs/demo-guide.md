# 化学・素材 — SDS 危険分類抽出 / GHS バリデーション Demo Guide

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本デモでは、FSx for ONTAP 上のファイルを S3 Access Points 経由で AI/ML サービスが自動分析するパイプラインを実演します。

**想定時間**: 3〜5 分

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
