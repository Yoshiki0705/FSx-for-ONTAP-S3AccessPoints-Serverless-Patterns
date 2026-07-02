# UC25: 電力・ユーティリティ — ドローン画像点検 / SCADA 異常検知

🌐 **Language / 言語**: 日本語 | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **ドキュメント**: [アーキテクチャ図](docs/architecture.md) | [デモガイド](docs/demo-guide.md)

## 概要

FSx for ONTAP の S3 Access Points を活用し、送電設備のドローン点検画像から欠陥検出、SCADA ログの時系列異常検知、FLIR 熱画像のホットスポット分析を行うサーバーレスワークフローです。

## Success Metrics

### Outcome
文書処理と分析の自動化により、オペレーション効率化とコンプライアンス強化を実現する。

### Metrics
| メトリクス | 目標値（例） |
|-----------|------------|
| 欠陥検出率 | ≥ 85% |
| SCADA 異常偽陽性率 | < 10% |
| サーマルホットスポット検出精度 | ≥ 90% |
| レポート生成時間 | < 5 分 / バッチ |
| コスト / 日次実行 | < $3.00 |
| Human Review 必須率 | > 30%（Critical 重大度検出時は全件確認） |

### Measurement Method
Step Functions 実行履歴、AI/ML サービス抽出結果、CloudWatch EMF Metrics（ProcessingDuration, SuccessCount, ErrorCount）。

### Human Review Requirements
- 低信頼度結果は手動確認が必要
- Critical アラートはドメイン専門家がレビュー
- 定期サマリレポートは経営層がレビュー

## アーキテクチャ

詳細なデータフロー図は[アーキテクチャドキュメント](docs/architecture.md)を参照してください。

## 前提条件

> **S3 AP NetworkOrigin 注意**: Discovery Lambda は VPC 内に配置されます。S3 Access Point の NetworkOrigin が `Internet` の場合、S3 Gateway VPC Endpoint 経由ではアクセスできません（FSx データプレーンにルーティングされないため）。NetworkOrigin=VPC の S3 AP を使用するか、NAT Gateway 経由のアクセスを設定してください。詳細は [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md) を参照。

- AWS アカウントと適切な IAM 権限
- FSx for ONTAP ファイルシステム（ONTAP 9.17.1P4D3 以上）
- S3 Access Point が有効化されたボリューム
- VPC、プライベートサブネット
- Amazon Bedrock モデルアクセスが有効（Claude / Nova）

## デプロイ手順

```bash
# 前提: AWS SAM CLI が必要です。sam build がコードと共有レイヤーを自動でパッケージングします。
sam build

sam deploy \
  --stack-name fsxn-utilities-inspection \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    ScheduleExpression="cron(0 0 * * ? *)" \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region ap-northeast-1
```

> **注意**: `template.yaml` は SAM CLI（`sam build` + `sam deploy`）で使用します。
> `aws cloudformation deploy` コマンドで直接デプロイする場合は `template-deploy.yaml` を使用してください（Lambda zip ファイルの事前パッケージングと S3 アップロードが必要です）。

## ⚠️ パフォーマンスに関する注意事項

- FSx for ONTAP のスループットキャパシティは **NFS/SMB/S3 AP 全体で共有**されます。MapConcurrency=10 で並列処理を行う場合、同一ボリュームの他のワークロードに影響する可能性があります。
- 大量ファイルの一括処理を行う場合は、FSx for ONTAP の Throughput Capacity (MBps) を確認し、必要に応じて MapConcurrency を調整してください。
- 推奨: 本番環境では最初に MapConcurrency=5 で開始し、FSx for ONTAP の CloudWatch メトリクス (ThroughputUtilization) を監視しながら段階的に増加させてください。

## クリーンアップ

```bash
aws s3 rm s3://fsxn-utilities-inspection-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-utilities-inspection --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-utilities-inspection --region ap-northeast-1
```

## コスト見積もり（月額概算）

> **注記**: ap-northeast-1 リージョンの概算。実際のコストは使用量により異なります。

| 構成 | 月額概算 |
|------|---------|
| 最小構成（日次 1 回） | ~$8-20 |
| 標準構成 | ~$20-50 |

---

## Governance Note

> 本パターンは技術アーキテクチャガイダンスを提供します。法的・コンプライアンス・規制上の助言ではありません。SCADA データは重要インフラ情報です。アクセス権限管理と監査ログの保持は電気事業法および重要インフラ保護ガイドラインに準拠してください。

> **関連規制**: 電気事業法、電気設備技術基準

---

## S3AP Compatibility

S3 Access Points for FSx for ONTAP の互換性制約、トラブルシューティング、トリガーパターンについては [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md) を参照してください。
