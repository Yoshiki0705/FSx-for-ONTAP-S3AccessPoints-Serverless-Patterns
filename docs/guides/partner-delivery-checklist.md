# NetApp Partner Delivery Checklist

## Purpose

NetApp パートナーが顧客環境に FSx for ONTAP S3 AP Serverless Patterns をデプロイする際の事前確認・検証・引き渡しチェックリスト。

---

## 1. ONTAP Prerequisites

- [ ] ONTAP バージョン確認: 9.15.1 以上（Persistent Store + protobuf 対応）
- [ ] FPolicy ポリシーモード: **async non-mandatory**（Persistent Store 必須条件）
- [ ] SVM 構成確認: SVM 名、管理 LIF IP、データ LIF IP
- [ ] **ファイルシステム管理 IP 確認**: `aws fsx describe-file-systems --query 'FileSystems[0].OntapConfiguration.Endpoints.Management.IpAddresses[0]'`（fsxadmin はこの IP でのみ認証可能。SVM 管理 IP では不可）
- [ ] ボリュームスコープ: 対象ボリューム名、ジャンクションパス、セキュリティスタイル
- [ ] プロトコル確認: NFSv3 / NFSv4.1 / SMB のどれが有効か
- [ ] Persistent Store ボリュームサイジング: 想定イベント量 × ダウンタイム時間
- [ ] FPolicy external engine 登録: サーバー IP、ポート（9898）、プロトコル（TCP）
- [ ] ONTAP 管理ユーザー: fsxadmin または専用 automation アカウント
- [ ] 自己署名 TLS 証明書: 管理 LIF の証明書検証設定確認
- [ ] **Protobuf モード切り替え**: REST API のみ対応（CLI `-format` パラメータは 9.17.1 で未実装）

## 2. S3 Access Point Configuration

- [ ] NetworkOrigin 選定: VPC / Internet（[Decision Tree](decision-trees.md#1-s3ap-networkorigin-selection) 参照）
- [ ] S3AP エイリアス確認: `xxx-ext-s3alias` 形式
- [ ] S3AP 名確認: IAM ポリシー ARN に使用する名前
- [ ] IAM ポリシー ARN 形式: `arn:aws:s3:{region}:{account}:accesspoint/{name}`
- [ ] S3AP リソースポリシー: 必要に応じて `s3control put-access-point-policy` で設定
- [ ] ヘルスマーカーファイル: NFS 経由で `_health/marker.txt` を作成済み
- [ ] VPC Endpoint 設定（VPC Origin の場合）: Gateway or Interface EP

## 3. AWS Infrastructure

- [ ] VPC 構成: VPC ID、Private Subnet IDs、Security Group ID
- [ ] Security Group: ONTAP SVM SG → FPolicy サーバー SG（TCP 9898）
- [ ] Secrets Manager: ONTAP 認証情報シークレット作成済み
- [ ] SNS Topic: アラート通知用トピック作成済み + サブスクリプション確認済み
- [ ] S3 デプロイバケット: SAM パッケージ用バケット存在確認
- [ ] IAM 権限: デプロイ実行者に `CAPABILITY_NAMED_IAM` 権限あり

## 4. Deployment Validation

- [ ] Phase 12 スタック全 7 つが CREATE_COMPLETE
- [ ] Phase 13 スタック（s3ap-external-monitor, cost-dashboard, lineage-retention, flexclone-pipeline）デプロイ成功
- [ ] Capacity Forecast Lambda 手動実行成功
- [ ] Secrets Rotation テスト実行成功（4 ステップ完了）
- [ ] S3AP External Monitor Lambda 手動実行 → メトリクス値 1

## 5. Replay Validation

- [ ] Fargate タスク停止（ECS stop-task）
- [ ] ダウンタイム中にテストファイル作成（5 ファイル以上）
- [ ] ECS サービス自動復旧確認（新タスク起動）
- [ ] FPolicy engine IP 更新（disable → modify → enable）
- [ ] SQS メッセージ到達確認（全イベント受信）
- [ ] Out-of-order 配信の確認（順序保証なしを理解）
- [ ] 下流の冪等性確認（重複イベント処理可能）

## 6. Security Validation

- [ ] fsxadmin Secrets Rotation: 4 ステップ完了確認
- [ ] IAM least-privilege: 各 Lambda ロールに最小権限のみ
- [ ] VPC Endpoint 設定: 必要なエンドポイントが存在
- [ ] Security Group: SourceSecurityGroupId ベース（CIDR ではない）
- [ ] 暗号化: SQS（SqsManagedSseEnabled）、DynamoDB（AWS managed key）
- [ ] BREAK_GLASS: SNS アラート + DynamoDB 監査ログ確認

## 7. Operational Handover

- [ ] SLO Dashboard URL 共有: `https://{region}.console.aws.amazon.com/cloudwatch/...`
- [ ] Cost Dashboard URL 共有
- [ ] Runbook 場所共有: `docs/runbooks/slo-violation-response.md`
- [ ] SNS アラートサブスクリプション: 運用チームのメールアドレス登録
- [ ] BREAK_GLASS 承認プロセス: 誰が承認するか明確化
- [ ] エスカレーション連絡先: AWS Support + NetApp Support の連絡先
- [ ] 定期検証スケジュール: 四半期ごとの再検証日程設定

---

## Sign-Off

| 項目 | 値 |
|------|-----|
| Partner Engineer | _________________________ |
| Customer Contact | _________________________ |
| Deployment Date | _________________________ |
| ONTAP Version | _________________________ |
| AWS Region | _________________________ |
| S3AP NetworkOrigin | VPC / Internet |
| Replay Test Result | Pass / Fail |
| SLO Dashboard Confirmed | Yes / No |
| Runbook Delivered | Yes / No |

**署名**: _________________________ **日付**: _________________________
