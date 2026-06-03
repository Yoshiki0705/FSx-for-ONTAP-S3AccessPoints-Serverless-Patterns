# 運輸・鉄道 — 設備点検画像分析 / 保守レポート管理 Demo Guide

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本デモでは、鉄道設備の点検画像から劣化指標を自動検出し、安全重要インフラに対する低閾値検出と人間レビューフラグの仕組みを実演する。12ヶ月の劣化トレンドに基づく保守優先度の自動ランキングも紹介する。

**デモの核心メッセージ**: AI が点検画像から劣化を検出し重大度を分類。安全重要インフラは低閾値 + 人間レビュー必須で見逃しリスクを最小化する。

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
cd fsxn-s3ap-serverless-patterns/transportation-maintenance
```

### Step 3: テスト用サンプルデータの配置

```
/inspections/
  route-A/2026-06-01/
    track-section-01.jpg         # 一般軌道（標準閾値 80%）
    bridge-span-01.jpg           # 橋梁（安全重要閾値 60%）
    signal-unit-01.png           # 信号設備（安全重要閾値 60%）
    rail-joint-01.tiff           # レール接合部（安全重要閾値 60%）
/maintenance-reports/
  2026/06/report-route-A.pdf     # 保守報告書（PDF）
  2026/06/lifecycle-data.xlsx    # ライフサイクルデータ（Excel）
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
  --stack-name fsxn-transport-demo \
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
  --stack-name fsxn-transport-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text --region ap-northeast-1)

aws stepfunctions start-execution --state-machine-arn $STATE_MACHINE_ARN --region ap-northeast-1
```

---

## 検証チェックリスト

| チェック項目 | 期待される結果 |
|------------|--------------|
| 画像検出 | ルート・日付別に画像が検出される |
| 標準閾値検出 | 一般軌道画像は 80% 閾値で検出 |
| 安全重要閾値検出 | 橋梁/信号/レール接合部は 60% 閾値で検出 |
| 人間レビューフラグ | < 90% 検出に `human_review_required: true` |
| 重大度分類 | critical/major/minor/observation の 4 段階 |
| 低解像度マーク | < 1024×768 画像に `requires-reinspection` |
| 保守報告書抽出 | 修理履歴・ライフサイクルデータが構造化される |
| 優先度ランキング | 重大度×部品年齢でソートされたランキング |

---

## トラブルシューティング

| 症状 | 原因 | 解決策 |
|------|------|--------|
| Discovery タイムアウト | S3 AP アクセス失敗 | NetworkOrigin 設定確認 |
| Rekognition 結果なし | 画像品質不良 | 解像度・コントラスト確認 |
| Textract 失敗 | Cross-Region 設定不備 | us-east-1 接続設定確認 |
| `AccessDenied` | IAM ARN 形式誤り | accesspoint ARN 形式確認 |

---

## クリーンアップ

```bash
aws cloudformation delete-stack --stack-name fsxn-transport-demo --region ap-northeast-1
```

---

*本ドキュメントは技術プレゼンテーション用デモ動画の制作ガイドです。*
