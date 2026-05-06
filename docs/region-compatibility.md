# リージョン互換性マトリックス

本プロジェクトの各ユースケースで使用する AWS サービスのリージョン対応状況です。

## サービス別リージョン対応

| サービス | us-east-1 | us-west-2 | eu-west-1 | ap-northeast-1 | ap-southeast-1 |
|---------|-----------|-----------|-----------|----------------|----------------|
| FSx for NetApp ONTAP | ✅ | ✅ | ✅ | ✅ | ✅ |
| S3 Access Points | ✅ | ✅ | ✅ | ✅ | ✅ |
| Lambda | ✅ | ✅ | ✅ | ✅ | ✅ |
| Step Functions | ✅ | ✅ | ✅ | ✅ | ✅ |
| EventBridge Scheduler | ✅ | ✅ | ✅ | ✅ | ✅ |
| Amazon Athena | ✅ | ✅ | ✅ | ✅ | ✅ |
| Amazon Bedrock | ✅ | ✅ | ✅ | ✅ | ✅ |
| Amazon Rekognition | ✅ | ✅ | ✅ | ✅ | ✅ |
| Amazon Comprehend | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Amazon Textract** | ✅ | ✅ | ✅ | **❌** | ✅ |
| **Amazon Comprehend Medical** | ✅ | ✅ | ✅ | **❌** | **❌** |
| AWS Deadline Cloud | ✅ | ✅ | ✅ | ✅ | — |
| Amazon SNS | ✅ | ✅ | ✅ | ✅ | ✅ |
| AWS Secrets Manager | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Kinesis Data Streams** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **SageMaker Batch Transform** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **AWS X-Ray** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **CloudWatch EMF** | ✅ | ✅ | ✅ | ✅ | ✅ |

## ユースケース別推奨リージョン

| UC | 推奨リージョン | 制約 |
|---|--------------|------|
| UC1 法務 | 全リージョン | なし |
| UC2 金融 | us-east-1, us-west-2, eu-west-1 | Textract 非対応リージョンではクロスリージョン呼び出し（`TEXTRACT_REGION` パラメータ） |
| UC3 製造 | 全リージョン | なし |
| UC4 メディア | us-east-1, us-west-2, eu-west-1 | Deadline Cloud 対応リージョン |
| UC5 医療 | us-east-1, us-west-2, eu-west-1 | Comprehend Medical 非対応リージョンではクロスリージョン呼び出し（`COMPREHEND_MEDICAL_REGION` パラメータ） |
| UC6 半導体 | 全リージョン | なし |
| UC7 ゲノミクス | us-east-1, us-west-2, eu-west-1 | Comprehend Medical 非対応リージョンではクロスリージョン呼び出し |
| UC8 エネルギー | 全リージョン | なし |
| UC9 自動運転 | 全リージョン | SageMaker Batch Transform 利用時はインスタンスタイプの可用性を確認 |
| UC10 建設 | us-east-1, us-west-2, eu-west-1 | Textract 非対応リージョンではクロスリージョン呼び出し |
| UC11 小売 | 全リージョン | Kinesis ストリーミングモード利用時はシャード料金がリージョンにより異なる |
| UC12 物流 | us-east-1, us-west-2, eu-west-1 | Textract 非対応リージョンではクロスリージョン呼び出し |
| UC13 教育 | us-east-1, us-west-2, eu-west-1 | Textract 非対応リージョンではクロスリージョン呼び出し |
| UC14 保険 | us-east-1, us-west-2, eu-west-1 | Textract 非対応リージョンではクロスリージョン呼び出し |

## クロスリージョン呼び出し

Textract と Comprehend Medical が利用できないリージョンでは、Lambda から別リージョンの API をクロスリージョンで呼び出します。

```yaml
# UC2: Textract のクロスリージョン呼び出し
TextractRegion: "us-east-1"  # Textract 対応リージョンを指定

# UC5: Comprehend Medical のクロスリージョン呼び出し
ComprehendMedicalRegion: "us-east-1"  # Comprehend Medical 対応リージョンを指定
```

> **注意**: クロスリージョン呼び出しではデータが別リージョンに転送されます。コンプライアンス要件（データレジデンシー等）を確認してください。

## Phase 3 サービスのリージョン別考慮事項

| サービス | リージョン制約 | 備考 |
|---------|-------------|------|
| Kinesis Data Streams | ほぼ全商用リージョンで利用可能 | シャード料金はリージョンにより異なる（例: us-east-1: $0.015/h, ap-northeast-1: $0.0195/h） |
| SageMaker Batch Transform | ほぼ全リージョンで利用可能 | インスタンスタイプ（ml.m5.xlarge 等）の可用性がリージョンにより異なる |
| AWS X-Ray | 全商用リージョンで利用可能 | 特記事項なし |
| CloudWatch EMF | 全商用リージョンで利用可能 | 特記事項なし |

> **SageMaker インスタンスタイプの確認**: デプロイ前に [SageMaker 料金ページ](https://aws.amazon.com/sagemaker/pricing/) でターゲットリージョンのインスタンスタイプ可用性を確認してください。

> **Kinesis シャード料金の確認**: リージョンによりシャード時間料金が異なります。詳細は [Kinesis Data Streams 料金ページ](https://aws.amazon.com/kinesis/data-streams/pricing/) を参照してください。

## 参考リンク

- [Textract 対応リージョン](https://docs.aws.amazon.com/general/latest/gr/textract.html)
- [Comprehend Medical 対応リージョン](https://docs.aws.amazon.com/general/latest/gr/comprehend-med.html)
- [FSx ONTAP 対応リージョン](https://docs.aws.amazon.com/general/latest/gr/fsxn.html)
- [Bedrock 対応リージョン](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)
- [Kinesis Data Streams 料金](https://aws.amazon.com/kinesis/data-streams/pricing/)
- [SageMaker 料金](https://aws.amazon.com/sagemaker/pricing/)
- [X-Ray 対応リージョン](https://docs.aws.amazon.com/general/latest/gr/xray.html)
