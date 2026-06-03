# UC26: 不動産 — 物件画像分析 / 契約書抽出

🌐 **Language / 言語**: 日本語 | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **ドキュメント**: [アーキテクチャ図](docs/architecture.md) | [デモガイド](docs/demo-guide.md)

## 概要

FSx for ONTAP の S3 Access Points を活用し、物件画像から特徴抽出・リスティング説明文自動生成、賃貸契約書から条件抽出、PII 検出によるプライバシー保護を行うサーバーレスワークフローです。

## Success Metrics

### Outcome
文書処理と分析の自動化により、オペレーション効率化とコンプライアンス強化を実現する。

### Metrics
| メトリクス | 目標値（例） |
|-----------|------------|
| 物件特徴抽出精度 | ≥ 85% |
| PII 検出率 | ≥ 95% |
| 契約条件抽出精度 | ≥ 90% |
| レポート生成時間 | < 5 分 / バッチ |
| コスト / 日次実行 | < $2.50 |
| Human Review 必須率 | > 20%（PII 検出画像は全件確認） |

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
- Amazon Textract — Cross-Region (us-east-1) 呼び出し設定

## デプロイ手順

```bash
aws cloudformation deploy \
  --template-file real-estate-portfolio/template.yaml \
  --stack-name fsxn-real-estate \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    ScheduleExpression="cron(0 0 * * ? *)" \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-northeast-1
```

## ⚠️ パフォーマンスに関する注意事項

- FSx for ONTAP のスループットキャパシティは **NFS/SMB/S3 AP 全体で共有**されます。MapConcurrency=10 で並列処理を行う場合、同一ボリュームの他のワークロードに影響する可能性があります。
- 大量ファイルの一括処理を行う場合は、FSx ONTAP の Throughput Capacity (MBps) を確認し、必要に応じて MapConcurrency を調整してください。
- 推奨: 本番環境では最初に MapConcurrency=5 で開始し、FSx ONTAP の CloudWatch メトリクス (ThroughputUtilization) を監視しながら段階的に増加させてください。

## クリーンアップ

```bash
aws s3 rm s3://fsxn-real-estate-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-real-estate --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-real-estate --region ap-northeast-1
```

## コスト見積もり（月額概算）

> **注記**: ap-northeast-1 リージョンの概算。実際のコストは使用量により異なります。

| 構成 | 月額概算 |
|------|---------|
| 最小構成（日次 1 回） | ~$8-20 |
| 標準構成 | ~$20-50 |

---

## Governance Note

> 本パターンは技術アーキテクチャガイダンスを提供します。法的・コンプライアンス・規制上の助言ではありません。賃貸契約書に含まれるテナント情報は個人情報保護法に基づき適切に管理してください。物件画像に映り込む個人情報の取り扱いには宅地建物取引業法の規定にも留意してください。

> **関連規制**: 宅地建物取引業法、個人情報保護法

---

## S3AP Compatibility

S3 Access Points for FSx for ONTAP の互換性制約、トラブルシューティング、トリガーパターンについては [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md) を参照してください。
