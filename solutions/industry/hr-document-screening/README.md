# UC27: 人材・HR — 履歴書スクリーニング / PII 厳格モード

🌐 **Language / 言語**: 日本語 | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **ドキュメント**: [アーキテクチャ図](docs/architecture.md) | [デモガイド](docs/demo-guide.md)

## 概要

FSx for ONTAP の S3 Access Points を活用し、履歴書・職務経歴書からスキル・経験を構造化抽出し、PII 厳格モードで保護特性を除外したスコアリングを行うサーバーレスワークフローです。

> **重要: 規制上の注意事項**
> 本パターンは**文書トリアージおよび要約ワークフロー**であり、自動採用決定システムではありません。最終的な採用決定は必ず資格を持つ人事担当者が行ってください。利用前に、各国・地域の労働法、プライバシー規制（GDPR、APPI、CCPA 等）、差別禁止要件への適合を検証する必要があります。出力には保護特性による順位付けを含めず、評価説明は職務関連の資格・経験のみを根拠とします。

## Success Metrics

### Outcome
文書処理と分析の自動化により、オペレーション効率化とコンプライアンス強化を実現する。

### Metrics
| メトリクス | 目標値（例） |
|-----------|------------|
| 履歴書データ抽出率 | ≥ 90% |
| スコアリング公平性 | 保護特性バイアスなし（年齢・性別・国籍除外） |
| PII コンプライアンス | 100%（ログへの PII 出力ゼロ） |
| レポート生成時間 | < 5 分 / バッチ |
| コスト / 日次実行 | < $2.00 |
| Human Review 必須率 | > 30%（全スコアリング結果を人事チームが確認） |

### Measurement Method
Step Functions 実行履歴、AI/ML サービス抽出結果、CloudWatch EMF Metrics（ProcessingDuration, SuccessCount, ErrorCount）。

### Human Review Requirements
- 低信頼度結果は手動確認が必要
- Critical アラートはドメイン専門家がレビュー
- 定期サマリレポートは経営層がレビュー

### Output Safeguard Requirements
- 出力スキーマに age/gender/ethnicity/nationality フィールドを含めないこと
- 評価説明は職務関連の資格・経験のみを根拠とすること
- 検出された保護特性は保存前に除去されること
- 全ての推薦結果は人間レビューを必須とすること

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
  --template-file hr-document-screening/template.yaml \
  --stack-name fsxn-hr-screening \
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
- 大量ファイルの一括処理を行う場合は、FSx for ONTAP の Throughput Capacity (MBps) を確認し、必要に応じて MapConcurrency を調整してください。
- 推奨: 本番環境では最初に MapConcurrency=5 で開始し、FSx for ONTAP の CloudWatch メトリクス (ThroughputUtilization) を監視しながら段階的に増加させてください。

## クリーンアップ

```bash
aws s3 rm s3://fsxn-hr-screening-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-hr-screening --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-hr-screening --region ap-northeast-1
```

## コスト見積もり（月額概算）

> **注記**: ap-northeast-1 リージョンの概算。実際のコストは使用量により異なります。

| 構成 | 月額概算 |
|------|---------|
| 最小構成（日次 1 回） | ~$8-20 |
| 標準構成 | ~$20-50 |

---

## Governance Note

> 本パターンは技術アーキテクチャガイダンスを提供します。法的・コンプライアンス・規制上の助言ではありません。採用選考における AI 活用は、職業安定法および男女雇用機会均等法に準拠し、保護特性（年齢、性別、国籍等）によるバイアスを排除してください。AI スコアリングは参考情報であり、最終判断は人事担当者が行う必要があります。

> **関連規制**: 職業安定法、個人情報保護法、労働基準法

---

## S3AP Compatibility

S3 Access Points for FSx for ONTAP の互換性制約、トラブルシューティング、トリガーパターンについては [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md) を参照してください。
