# HA LifeKeeper Monitoring — 検証計画

## Option A: DemoMode デプロイ検証 (Phase 18 公開前)

### 目的
DemoMode=true で SAM デプロイ → Step Functions 実行 → レポート出力を確認する。

### 前提条件
- EC2 (ap-northeast-1, SAM CLI インストール済み)
- Python 3.12
- Bedrock `amazon.nova-pro-v1:0` モデルアクセス有効化

### 手順

```bash
# 1. EC2 接続
ssh -i <key.pem> ubuntu@<ec2-ip>

# 2. リポジトリ同期
cd ~/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns
git pull origin main

# 3. デモ用 S3 バケット作成 + サンプルログ配置
DEMO_BUCKET="ha-lifekeeper-demo-$(date +%s)"
aws s3 mb s3://$DEMO_BUCKET
aws s3 cp test-data/ha-lifekeeper-monitoring/ s3://$DEMO_BUCKET/lifekeeper/logs/ --recursive

# 4. SAM ビルド・デプロイ
cd solutions/ha/lifekeeper-monitoring
sam build
sam deploy --no-confirm-changeset \
  --stack-name ha-lifekeeper-demo \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    DemoMode=true \
    S3AccessPointAlias=$DEMO_BUCKET \
    OutputBucketName=$DEMO_BUCKET \
    NotificationEmail=yoshiki@netapp.com \
    ClusterName=demo-cluster \
    TriggerMode=POLLING \
    ScheduleExpression="rate(60 minutes)" \
    FailoverAlertSeverity=CRITICAL

# 5. Step Functions 手動実行
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name ha-lifekeeper-demo \
  --query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" \
  --output text)

EXEC_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --input '{"trigger":"manual","cluster_name":"demo-cluster"}' \
  --query 'executionArn' --output text)

# 6. 実行結果確認 (30秒後)
sleep 30
aws stepfunctions describe-execution --execution-arn $EXEC_ARN --query 'status'

# 7. レポート確認
aws s3 ls s3://$DEMO_BUCKET/reports/ --recursive
aws s3 cp s3://$DEMO_BUCKET/reports/ /tmp/reports/ --recursive
cat /tmp/reports/*.md | head -50

# 8. クリーンアップ
sam delete --stack-name ha-lifekeeper-demo --no-prompts
aws s3 rb s3://$DEMO_BUCKET --force
```

### 期待される結果
- [ ] `sam build` 成功
- [ ] `sam deploy` 成功 (CloudFormation CREATE_COMPLETE)
- [ ] Step Functions 実行 SUCCEEDED
- [ ] Discovery: 5ファイル検出
- [ ] Processing: ヘルススコア算出 (70 = WARNING想定)
- [ ] Report: Markdown レポート S3 出力
- [ ] CloudWatch Logs にエラーなし

### 所要時間
~30分 (EC2 が起動済みの場合)

---

## Option B: 実 LifeKeeper 環境検証 (Phase 19 用)

### 目的
実際の LifeKeeper HA クラスタでフェイルオーバーを発生させ、ログ → S3 AP → パイプライン → RCA の E2E を検証する。

### ライセンス取得

| 方法 | 即時性 | コスト |
|------|--------|--------|
| AWS Marketplace Subscribe (時間課金) | ✅ 即座 | $0.18-0.51/hr/node |
| SIOS Technical Support (評価版依頼) | 1-3営業日 | 無料 (30日) |
| AWS Partner Solution (Quick Start) | ✅ CFn 自動構築 | Marketplace pricing |

**推奨**: AWS Marketplace + Partner Solution Quick Start の組み合わせ。

### 環境構成

```
┌─────────────────────────────────────────────────────────┐
│ VPC (10.0.0.0/16)                                       │
├──────────────────────┬──────────────────────────────────┤
│ AZ-a (10.0.1.0/24)  │ AZ-c (10.0.2.0/24)              │
│                      │                                  │
│ EC2: node1           │ EC2: node2                       │
│ - LifeKeeper v10     │ - LifeKeeper v10                │
│ - RHEL 9.x          │ - RHEL 9.x                      │
│ - t3.large           │ - t3.large                      │
│ - SAP/NFS Recovery Kit│ - SAP/NFS Recovery Kit          │
│                      │                                  │
├──────────────────────┴──────────────────────────────────┤
│ FSx for ONTAP (Multi-AZ)                                │
│ - 128 MBps throughput                                   │
│ - SVM: svm-lifekeeper                                   │
│ - Volume: vol_lifekeeper_data (NFS)                     │
│ - Volume: vol_lifekeeper_logs (NFS) → S3 AP             │
│ - S3 Access Point: lifekeeper-logs-s3ap                 │
└─────────────────────────────────────────────────────────┘
```

### コスト見積もり (月額)

| リソース | 月額 | 備考 |
|---------|------|------|
| EC2 t3.large × 2 | ~$120 | LifeKeeper nodes |
| LifeKeeper license (Marketplace) | ~$260 | $0.18/hr × 2 × 730h |
| FSx for ONTAP (128 MBps, Multi-AZ) | ~$194 | 既存環境流用可能 |
| S3 AP + Lambda + Step Functions | < $5 | Serverless |
| Bedrock Nova Pro | < $1 | 検証時のみ |
| **合計** | **~$580** | **検証期間のみ (数日なら ~$50)** |

### 検証シナリオ

1. **正常状態**: LifeKeeper ヘルスチェック → Score 100
2. **通信パス劣化**: node 間レイテンシ増加 → Score 85 (WARNING)
3. **手動スイッチオーバー**: `lkswitch` → ISP→OSF→ISS→ISP 遷移 → Score 70
4. **障害フェイルオーバー**: node1 停止 → 自動フェイルオーバー → Score 30 (CRITICAL) + SNS アラート
5. **FSx 層障害切り分け**: NFS マウント一時切断 → ストレージ vs アプリ判別

### 手順概要

```bash
# 1. Partner Solution デプロイ (CFn Quick Start)
#    → VPC + EC2 × 2 + LifeKeeper 自動インストール

# 2. FSx for ONTAP 追加 (既存 or 新規)
#    → SVM 作成, Volume 作成, S3 AP 作成

# 3. LifeKeeper 設定
#    → NFS Recovery Kit 設定, Communication Path 設定, VIP 設定

# 4. ログ出力設定
#    → LifeKeeper ログ → FSx NFS volume に書き込み

# 5. S3 AP 監視パターンデプロイ
#    → solutions/ha/lifekeeper-monitoring/ を DemoMode=false でデプロイ

# 6. フェイルオーバーテスト
#    → lkswitch / ノード停止 → ログ生成 → パイプライン実行 → RCA 確認

# 7. スクリーンショット取得
#    → Step Functions 実行画面, CloudWatch ダッシュボード, レポート出力

# 8. クリーンアップ
#    → CFn スタック削除, FSx 環境削除 (既存流用の場合は Volume のみ削除)
```

### タイムライン

| Day | タスク |
|-----|--------|
| Day 1 | Marketplace Subscribe + Partner Solution デプロイ + FSx 設定 |
| Day 2 | LifeKeeper 設定 + NFS Recovery Kit + ログ出力確認 |
| Day 3 | 監視パターンデプロイ + フェイルオーバーテスト + スクリーンショット |
| Day 4 | ブログ記事執筆 (Phase 19) + クリーンアップ |

### 成果物 (Phase 19 ブログ用)

- [ ] E2E フェイルオーバー検証のスクリーンショット
- [ ] Bedrock RCA 出力の品質サンプル
- [ ] Step Functions 実行グラフ (成功)
- [ ] CloudWatch ヘルススコアメトリクス
- [ ] SNS アラート受信画面
- [ ] パフォーマンス計測 (パイプライン E2E レイテンシ)
