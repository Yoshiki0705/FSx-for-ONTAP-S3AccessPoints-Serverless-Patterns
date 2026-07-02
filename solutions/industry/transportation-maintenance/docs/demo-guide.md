# 運輸・鉄道 — 設備点検画像分析 / 保守レポート管理 Demo Guide

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本デモでは、鉄道設備の点検画像から劣化指標を自動検出し、安全重要インフラに対する低閾値検出と人間レビューフラグの仕組みを実演する。12ヶ月の劣化トレンドに基づく保守優先度の自動ランキングも紹介する。

**デモの核心メッセージ**: AI が点検画像から劣化を検出し重大度を分類。安全重要インフラは低閾値 + 人間レビュー必須で見逃しリスクを最小化する。

**想定時間**: 3〜5 分

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **役職** | 鉄道会社 保線部門長 / 運輸事業者 設備管理責任者 |
| **日常業務** | 車両・線路の定期点検、保守レポート管理、障害対応 |
| **課題** | 点検画像の目視確認に時間がかかる、保守レポートの集約が手動 |
| **期待する成果** | 点検画像の自動異常検出と保守レポートの構造化 |

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
cd fsxn-s3ap-serverless-patterns/solutions/industry/transportation-maintenance
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
# FSx for ONTAP NFS マウント
sudo mount -t nfs <FSx-ONTAP-DATA-LIF-IP>:/vol1 /mnt/fsxn

# サンプルデータ配置
cp -r sample-data/* /mnt/fsxn/<prefix>/
```

### Step 4: SAM ビルドとデプロイ

```bash
# 前提: AWS SAM CLI が必要です。sam build がコードと共有レイヤーを自動でパッケージングします。
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


![Step Functions Graph View (SUCCEEDED)](../../docs/screenshots/masked/uc22-demo/step-functions-graph-view.png)

## 撮影ガイド

### 事前準備

```bash
# Lambda パッケージ作成
cd solutions/industry/transportation-maintenance
# 前提: AWS SAM CLI が必要です。sam build がコードと共有レイヤーを自動でパッケージングします。
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

