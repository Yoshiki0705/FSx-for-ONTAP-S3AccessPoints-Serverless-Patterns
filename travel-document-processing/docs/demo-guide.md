# 旅行・ホスピタリティ — 予約文書処理 / 施設点検画像分析 Demo Guide

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本デモでは、ホテル・旅館の予約文書と施設点検画像の自動分析パイプラインを実演する。Textract/Comprehend による予約データ抽出と Rekognition/Bedrock による施設状態分析で、オペレーション効率化と施設品質維持を自動化する。

**デモの核心メッセージ**: 予約文書を AI が自動解析し構造化データを抽出、施設点検画像から状態スコアリングとメンテナンス推奨を自動生成する。

**想定時間**: 3〜5 分

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **役職** | ホテルチェーン運営マネージャー / 施設管理責任者 |
| **日常業務** | 予約管理、施設点検、メンテナンス計画、品質管理 |
| **課題** | 大量の予約文書の手動処理と施設状態の定量的把握 |
| **期待する成果** | 文書処理時間の短縮と施設品質の可視化 |

---

## Demo Scenario: 予約文書処理と施設状態分析の自動化

### ワークフロー全体像

```
予約文書 / 施設画像  →  自動検出  →  データ抽出 / 状態分析  →  レポート生成
 (FSx ONTAP)           S3 AP      Textract / Rekognition    S3 + SNS
```

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
cd fsxn-s3ap-serverless-patterns/travel-document-processing
```

### Step 3: テスト用サンプルデータの配置

FSx ONTAP ボリューム上に以下の構造でサンプルデータを配置:

```
/reservations/
  2026/06/booking-confirmation-001.pdf    # 予約確認書
  2026/06/cancellation-notice-002.pdf     # キャンセル通知
  2026/06/guest-correspondence-003.pdf    # ゲスト対応文書
/inspections/
  2026/06/room-101-bathroom.jpg           # 客室点検画像
  2026/06/lobby-entrance.png              # 共用部点検画像
  2026/06/exterior-wall-north.tiff        # 外装点検画像
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

cp samconfig.toml.example samconfig.toml
# samconfig.toml を編集

sam deploy \
  --stack-name fsxn-travel-demo \
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
  --stack-name fsxn-travel-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text --region ap-northeast-1)

EXECUTION_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --region ap-northeast-1 --query "executionArn" --output text)
```

### Step 6: 出力結果の確認

```bash
OUTPUT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name fsxn-travel-demo \
  --query "Stacks[0].Outputs[?OutputKey=='OutputBucketName'].OutputValue" \
  --output text --region ap-northeast-1)

TODAY=$(date +%Y-%m-%d)
aws s3 ls s3://${OUTPUT_BUCKET}/reports/${TODAY}/ --region ap-northeast-1

# 予約処理サマリ確認
aws s3 cp s3://${OUTPUT_BUCKET}/reports/${TODAY}/reservation-summary.json \
  - --region ap-northeast-1 | python3 -m json.tool

# 施設状態レポート確認
aws s3 cp s3://${OUTPUT_BUCKET}/reports/${TODAY}/facility-condition.json \
  - --region ap-northeast-1 | python3 -m json.tool
```

---

## 検証チェックリスト

| チェック項目 | 確認方法 | 期待される結果 |
|------------|---------|--------------|
| 予約文書検出 | Step Functions ログ | Discovery が文書ファイル数を返す |
| データ抽出 | reservation-summary.json | 宿泊者名、日付、部屋タイプ、金額が含まれる |
| 多言語対応 | 英語文書でテスト | 言語検出 + 適切なモデル選択 |
| 施設状態分析 | facility-condition.json | 清潔度スコア (0–100) が含まれる |
| メンテナンス推奨 | facility-condition.json | Bedrock 生成の推奨事項が含まれる |
| エラーハンドリング | errors/ ディレクトリ | 抽出失敗文書のエラー記録 |

---

## トラブルシューティング

| 症状 | 原因 | 解決策 |
|------|------|--------|
| Discovery Lambda タイムアウト | S3 AP アクセス失敗 | NetworkOrigin 設定確認 |
| Textract エラー | Cross-Region 設定不備 | us-east-1 への接続設定確認 |
| 言語検出失敗 | スキャン品質不良 | 高解像度スキャンを推奨 |
| `AccessDenied` | IAM ポリシー ARN 形式誤り | `arn:aws:s3:{region}:{account}:accesspoint/{name}` 形式確認 |

---

## クリーンアップ

```bash
aws s3 rm s3://${OUTPUT_BUCKET} --recursive --region ap-northeast-1
aws cloudformation delete-stack --stack-name fsxn-travel-demo --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-travel-demo --region ap-northeast-1
```

---

*本ドキュメントは技術プレゼンテーション用デモ動画の制作ガイドです。*
