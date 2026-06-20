# 通信ネットワーク分析 — CDR/ネットワークログ異常検知 Demo Guide

🌐 **Language / 言語**: 日本語 | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本デモでは、CDR（通話詳細記録）とネットワーク機器ログの自動分析パイプラインを実演する。Athena によるトラフィック統計と Bedrock による異常検知で、ネットワーク障害の早期発見とコンプライアンスレポートを自動化する。

**デモの核心メッセージ**: CDR/ネットワークログを AI が自動分析し、異常をリアルタイムで検出、デイリーレポートを自動生成する。

**想定時間**: 3〜5 分

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **役職** | ネットワーク運用エンジニア / NOC オペレーター |
| **日常業務** | ネットワーク監視、障害対応、トラフィック分析、コンプライアンスレポート作成 |
| **課題** | 大量の CDR/ログから異常を早期発見し、規制当局へのレポートを自動化したい |
| **期待する成果** | MTTR（平均復旧時間）の短縮とレポート作成工数の削減 |

### Persona: 田中さん（ネットワーク運用エンジニア）

- 日々数百万件の CDR と大量の syslog を処理
- 「異常をシステムが自動検出し、重要なアラートだけを確認したい」
- 毎月の規制当局向けネットワーク品質レポートを自動化したい

---

## Demo Scenario: 通信ネットワークの異常検知とレポート自動化

### ワークフロー全体像

```
CDR / ネットワークログ  →  自動検出  →  統計分析 / 異常検知  →  デイリーレポート
 (FSx for ONTAP)              S3 AP        Athena / Bedrock        S3 + SNS アラート
```

---

## ステップバイステップ デプロイ・検証手順

### Step 1: 前提条件の確認

```bash
# AWS CLI バージョン確認
aws --version   # v2.x 必須

# SAM CLI バージョン確認
sam --version   # 1.x 以上

# Python バージョン確認
python3 --version  # 3.9 以上

# AWS 認証情報確認
aws sts get-caller-identity
```

### Step 2: リポジトリのクローンとディレクトリ移動

```bash
git clone https://github.com/Yoshiki0705/fsxn-s3ap-serverless-patterns.git
cd fsxn-s3ap-serverless-patterns/telecom-network-analytics
```

### Step 3: テスト用サンプルデータの配置

FSx for ONTAP ボリューム上に以下の構造でサンプルデータを配置します:

```
/cdr/
  2026/06/02/morning.csv       # CDR ファイル（CSV 形式）
  2026/06/02/afternoon.csv
  2026/06/02/evening.parquet   # CDR ファイル（Parquet 形式）
/syslog/
  2026/06/02/router01.log      # Syslog RFC 5424 形式
  2026/06/02/switch01.log
```

**CDR サンプルデータ（CSV 形式）**:
```csv
caller_id,callee_id,duration_sec,timestamp,cell_tower_id
09012345678,09098765432,120,2026-06-02T09:15:30Z,TOWER-001
09087654321,09011112222,45,2026-06-02T09:16:00Z,TOWER-002
```

**Syslog サンプルデータ（RFC 5424 形式）**:
```
<34>1 2026-06-02T09:20:00Z router01 kernel - - link-down interface GigabitEthernet0/1
<165>1 2026-06-02T09:21:00Z switch01 system - - CPU utilization 85% exceeds threshold
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
# SAM ビルド
sam build

# デプロイ（samconfig.toml.example をコピーして編集）
cp samconfig.toml.example samconfig.toml
# samconfig.toml の parameter_overrides を編集

# または直接デプロイ
sam deploy \
  --stack-name fsxn-telecom-demo \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
    CdrSuffixFilter=".csv,.asn1,.parquet" \
    AnomalyThresholdStdDev=3 \
    CapacityThresholdPercent=80 \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

### Step 5: デプロイの確認

```bash
# スタック状態確認
aws cloudformation describe-stacks \
  --stack-name fsxn-telecom-demo \
  --query "Stacks[0].StackStatus" \
  --region ap-northeast-1

# Lambda 関数一覧確認
aws lambda list-functions \
  --query "Functions[?contains(FunctionName, 'telecom')].FunctionName" \
  --region ap-northeast-1
```

### Step 6: ワークフローの手動実行

```bash
# Step Functions ARN を取得
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-telecom-demo \
  --query "Stacks[0].Outputs[?OutputKey=='WorkflowStateMachineArn'].OutputValue" \
  --output text \
  --region ap-northeast-1)

# ワークフローを手動実行
EXECUTION_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --region ap-northeast-1 \
  --query "executionArn" \
  --output text)

echo "Execution ARN: $EXECUTION_ARN"
```

### Step 7: 実行状態の監視

```bash
# 実行状態の確認
aws stepfunctions describe-execution \
  --execution-arn $EXECUTION_ARN \
  --query "status" \
  --region ap-northeast-1

# ステップ別の実行履歴確認
aws stepfunctions get-execution-history \
  --execution-arn $EXECUTION_ARN \
  --region ap-northeast-1 \
  --output table
```

### Step 8: 出力結果の確認

```bash
# 出力バケット名を取得
OUTPUT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name fsxn-telecom-demo \
  --query "Stacks[0].Outputs[?OutputKey=='OutputBucketName'].OutputValue" \
  --output text \
  --region ap-northeast-1)

# 今日の日付でレポートを確認
TODAY=$(date +%Y-%m-%d)
aws s3 ls s3://${OUTPUT_BUCKET}/reports/daily/${TODAY}/ --region ap-northeast-1

# CDR トラフィック統計を確認
aws s3 cp \
  s3://${OUTPUT_BUCKET}/reports/daily/${TODAY}/cdr-stats.json \
  - --region ap-northeast-1 | python3 -m json.tool

# 異常検知結果を確認
aws s3 cp \
  s3://${OUTPUT_BUCKET}/reports/daily/${TODAY}/anomalies.json \
  - --region ap-northeast-1 | python3 -m json.tool
```

### Step 9: CloudWatch メトリクスの確認

```bash
# 処理統計メトリクスを確認
aws cloudwatch get-metric-statistics \
  --namespace FSxN-S3AP-Patterns \ # allow:naming
  --metric-name SuccessCount \
  --dimensions Name=UseCase,Value=telecom-network-analytics \
  --start-time $(date -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Sum \
  --region ap-northeast-1
```

---

## 検証チェックリスト

| チェック項目 | 確認方法 | 期待される結果 |
|------------|---------|--------------|
| CDR ファイル検出 | Step Functions 実行ログ | Discovery ステップが CDR ファイル数を返す |
| Athena トラフィック統計 | S3 出力バケット確認 | `cdr-stats.json` が生成されている |
| syslog パース | Step Functions 実行ログ | Log Analyzer ステップが完了 |
| 異常検知 | `anomalies.json` 確認 | 異常フラグ付きレコードが含まれる（テストデータ次第） |
| デイリーレポート | S3 バケット確認 | `network-health.json` が `reports/daily/{today}/` に存在 |
| SNS アラート | メール受信確認 | 重大異常がある場合のみ通知メールが届く |

---

## トラブルシューティング

| 症状 | 原因 | 解決策 |
|------|------|--------|
| Discovery Lambda タイムアウト | VPC 内から S3 AP へのアクセス失敗 | NetworkOrigin 設定を確認。Internet Origin AP の場合は VPC 外実行か NAT Gateway 経由が必要 |
| CDR パースエラー | ファイル形式が想定外 | `CdrSuffixFilter` パラメータを確認。`errors/cdr/` に詳細エラーが記録される |
| Athena クエリ失敗 | ワークグループ設定不備 | Athena ワークグループとクエリ結果バケットの設定を確認 |
| Bedrock 呼び出し失敗 | モデルアクセス未許可 | Bedrock コンソールでモデルアクセスを有効化 |
| `AccessDenied` on S3 AP | IAM ポリシーの ARN 形式が誤り | `arn:aws:s3:{region}:{account}:accesspoint/{name}` 形式を使用しているか確認 |

---

## Storyboard（5 セクション / 3〜5 分）

### Section 1: Problem Statement（0:00–0:45）

**ナレーション要旨**:
> 日々数百万件の CDR とネットワークログが蓄積される。手動分析では異常検知に時間がかかり、規制当局へのレポート作成も工数がかかる。

**Key Visual**: CDR ファイル一覧、syslog ファイル蓄積状況

### Section 2: Data Discovery（0:45–1:30）

**ナレーション要旨**:
> EventBridge Scheduler が毎日 00:00 UTC にワークフローを起動。Discovery Lambda が S3 AP 経由で CDR と syslog ファイルを自動検出。

**Key Visual**: Step Functions グラフ、Discovery ステップの実行ログ

### Section 3: Traffic Analysis（1:30–2:30）

**ナレーション要旨**:
> CDR Analyzer が Athena で通話統計を集計。時間帯別通話量、平均通話時間、ピーク同時接続数を算出。

**Key Visual**: Athena クエリ結果、トラフィック統計グラフ

### Section 4: Anomaly Detection（2:30–3:45）

**ナレーション要旨**:
> Bedrock が 7 日間のベースラインと比較して 3σ超過の異常を検出。syslog から link-down や機器障害イベントも自動検出。

**Key Visual**: 異常検知結果 JSON、機器障害イベント一覧

### Section 5: Daily Report（3:45–5:00）

**ナレーション要旨**:
> Report Lambda がデイリーネットワーク健全性レポートを自動生成。S3 に保存し、重大異常があれば SNS でアラート。オペレーターは確認・対応するだけ。

**Key Visual**: ネットワーク健全性レポート JSON、SNS 通知メール

---

## クリーンアップ

```bash
# 出力バケットのデータ削除
aws s3 rm s3://${OUTPUT_BUCKET} --recursive --region ap-northeast-1

# スタック削除
aws cloudformation delete-stack \
  --stack-name fsxn-telecom-demo \
  --region ap-northeast-1

# 削除完了まで待機
aws cloudformation wait stack-delete-complete \
  --stack-name fsxn-telecom-demo \
  --region ap-northeast-1

echo "クリーンアップ完了"
```

---

## Technical Notes

| コンポーネント | 役割 |
|--------------|------|
| Step Functions | ワークフローオーケストレーション（並列 Map State） |
| Lambda (Discovery) | S3 AP からの CDR/syslog ファイル検出 |
| Lambda (CDR Analyzer) | CDR パース + Athena トラフィック統計 |
| Lambda (Log Analyzer) | Syslog RFC 5424 パース + 機器障害検出 |
| Lambda (Anomaly Detector) | Bedrock による 3σ異常検知 |
| Lambda (Report) | デイリーレポート生成 + SNS アラート |

### フォールバック

| シナリオ | 対応 |
|---------|------|
| Athena クエリ失敗 | exponential backoff 3 回リトライ後にエラー記録 |
| Bedrock 推論失敗 | exponential backoff 3 回リトライ後に SNS 通知 |
| CDR パース失敗 | `errors/cdr/` にエラー記録し、残りファイルを継続処理 |

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


![Step Functions Graph View (SUCCEEDED)](../../docs/screenshots/masked/uc18-demo/step-functions-graph-view.png)

## 撮影ガイド

### 事前準備

```bash
# Lambda パッケージ作成
cd telecom-network-analytics
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

