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

## ユースケース別推奨リージョン

| UC | 推奨リージョン | 制約 |
|---|--------------|------|
| UC1 法務 | 全リージョン | なし |
| UC2 金融 | us-east-1, us-west-2, eu-west-1 | Textract 非対応リージョンではクロスリージョン呼び出し（`TEXTRACT_REGION` パラメータ） |
| UC3 製造 | 全リージョン | なし |
| UC4 メディア | us-east-1, us-west-2, eu-west-1 | Deadline Cloud 対応リージョン |
| UC5 医療 | us-east-1, us-west-2, eu-west-1 | Comprehend Medical 非対応リージョンではクロスリージョン呼び出し（`COMPREHEND_MEDICAL_REGION` パラメータ） |

## クロスリージョン呼び出し

Textract と Comprehend Medical が利用できないリージョンでは、Lambda から別リージョンの API をクロスリージョンで呼び出します。

```yaml
# UC2: Textract のクロスリージョン呼び出し
TextractRegion: "us-east-1"  # Textract 対応リージョンを指定

# UC5: Comprehend Medical のクロスリージョン呼び出し
ComprehendMedicalRegion: "us-east-1"  # Comprehend Medical 対応リージョンを指定
```

> **注意**: クロスリージョン呼び出しではデータが別リージョンに転送されます。コンプライアンス要件（データレジデンシー等）を確認してください。

## 参考リンク

- [Textract 対応リージョン](https://docs.aws.amazon.com/general/latest/gr/textract.html)
- [Comprehend Medical 対応リージョン](https://docs.aws.amazon.com/general/latest/gr/comprehend-med.html)
- [FSx ONTAP 対応リージョン](https://docs.aws.amazon.com/general/latest/gr/fsxn.html)
- [Bedrock 対応リージョン](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)
