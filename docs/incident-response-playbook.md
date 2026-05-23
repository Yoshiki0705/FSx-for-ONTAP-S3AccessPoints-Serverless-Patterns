# インシデント対応 Playbook — FSx ONTAP S3AP パターン

## 概要

本 Playbook は、FSx ONTAP S3 Access Points を使用したサーバーレスパターンで
セキュリティインシデントが発生した場合の対応手順を定義します。

> **Governance Caveat**: 本 Playbook は技術的な対応手順のガイダンスです。組織のインシデント対応ポリシーに従い、適格なセキュリティ専門家の指示のもとで実行してください。

## インシデント分類

| レベル | 定義 | 例 | 対応時間目標 |
|--------|------|-----|------------|
| P1 Critical | データ漏洩の確認 or 進行中の不正アクセス | 不正な GetObject 大量実行 | 即時（15 分以内に封じ込め） |
| P2 High | 不正アクセスの試行検出 | AccessDenied の異常増加 | 1 時間以内 |
| P3 Medium | 設定ミスの検出 | 過剰な IAM 権限 | 24 時間以内 |
| P4 Low | 監査指摘事項 | ログ保持期間の不足 | 1 週間以内 |

## 検知ソース

| ソース | 検知内容 | 設定 |
|--------|---------|------|
| CloudTrail | S3 AP への全 API コール | デフォルト有効 |
| GuardDuty | 異常なアクセスパターン | 有効化推奨 |
| CloudWatch Alarms | エラー率の異常増加 | EnableCloudWatchAlarms=true |
| FSx ONTAP 監査ログ | ファイルアクセス監査 | ONTAP 側で設定 |
| IAM Access Analyzer | 外部アクセス可能なリソース | 有効化推奨 |

## 対応フロー

### Phase 1: 検知・トリアージ（0-15 分）

```
アラート受信
  ├─ CloudTrail で該当イベントを確認
  ├─ 影響範囲を特定（どの S3 AP、どのファイル）
  ├─ インシデントレベルを判定
  └─ エスカレーション判断
```

**確認コマンド:**

```bash
# 直近の S3 AP アクセスを確認
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=ResourceName,AttributeValue=<S3_AP_ARN> \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ) \
  --max-results 50

# 特定 IAM ロールのアクティビティ
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=Username,AttributeValue=<ROLE_NAME> \
  --start-time $(date -u -v-24H +%Y-%m-%dT%H:%M:%SZ)
```

### Phase 2: 封じ込め（15-60 分）

**即時封じ込めオプション:**

```bash
# Option A: S3 AP リソースポリシーで全アクセスを拒否
aws s3control put-access-point-policy \
  --account-id <ACCOUNT_ID> \
  --name <AP_NAME> \
  --policy '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": ["arn:aws:s3:<REGION>:<ACCOUNT>:accesspoint/<AP_NAME>",
                   "arn:aws:s3:<REGION>:<ACCOUNT>:accesspoint/<AP_NAME>/object/*"]
    }]
  }'

# Option B: Lambda 関数の実行を停止（Reserved Concurrency = 0）
aws lambda put-function-concurrency \
  --function-name <FUNCTION_NAME> \
  --reserved-concurrent-executions 0

# Option C: EventBridge Scheduler を無効化
aws scheduler update-schedule \
  --name <SCHEDULE_NAME> \
  --state DISABLED \
  --flexible-time-window '{"Mode":"OFF"}' \
  --schedule-expression "rate(1 hour)" \
  --target '{"Arn":"<SFN_ARN>","RoleArn":"<ROLE_ARN>"}'
```

### Phase 3: 調査（1-24 時間）

**調査項目:**

- [ ] 不正アクセスの開始時刻を特定
- [ ] アクセスされたファイルの一覧を作成
- [ ] 使用された認証情報を特定
- [ ] データ流出の有無を確認
- [ ] 攻撃経路を特定（認証情報漏洩? 設定ミス? 内部犯行?）

**調査コマンド:**

```bash
# Athena で CloudTrail ログを分析
# (CloudTrail ログが S3 に配信されている前提)
SELECT eventtime, eventsource, eventname, sourceipaddress, useragent,
       requestparameters
FROM cloudtrail_logs
WHERE eventsource = 's3.amazonaws.com'
  AND requestparameters LIKE '%<AP_NAME>%'
  AND eventtime > '2026-05-23T00:00:00Z'
ORDER BY eventtime DESC
LIMIT 100;
```

### Phase 4: 復旧（調査完了後）

- [ ] 漏洩した認証情報を無効化・ローテーション
- [ ] S3 AP ポリシーを正しい状態に復元
- [ ] Lambda 関数の Concurrency を復元
- [ ] EventBridge Scheduler を再有効化
- [ ] 動作確認テストを実行

### Phase 5: 事後対応

- [ ] インシデントレポートを作成
- [ ] 根本原因分析（RCA）を実施
- [ ] 再発防止策を実装
- [ ] 監視・アラートの改善
- [ ] 関係者への報告

## 予防的コントロール

| コントロール | 実装方法 | 対象テンプレート |
|------------|---------|----------------|
| IAM 最小権限 | Lambda Role に必要最小限のアクション | 全 UC |
| S3 AP リソースポリシー | Principal + Condition 制限 | 手動設定 |
| VPC Origin AP | VPC 外からのアクセスを拒否 | ネットワーク設計 |
| CloudTrail 有効化 | 全 S3 API コールを記録 | AWS アカウント設定 |
| GuardDuty 有効化 | 異常検知 | AWS アカウント設定 |
| Secrets Manager ローテーション | ONTAP 認証情報の定期更新 | Phase 12 実装済み |

---

> **重要**: 本 Playbook は技術的なガイダンスであり、法的助言ではありません。実際のインシデント対応では、組織のセキュリティポリシー、法務部門、および必要に応じて法執行機関と連携してください。
