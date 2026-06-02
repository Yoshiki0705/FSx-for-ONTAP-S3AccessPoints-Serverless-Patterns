# cfn-guard / cdk-nag Suppression ガイド

## 許容される Resource: "*" パターン

以下の AWS サービスはリソースレベルの IAM ポリシーをサポートしていません。`Resource: "*"` は正しい使用方法であり、セキュリティスキャンでの false positive として suppress してください。

| サービス | アクション | 理由 | 参照 |
|---------|-----------|------|------|
| Amazon Rekognition | `rekognition:DetectLabels`, `rekognition:DetectModerationLabels`, `rekognition:DetectText` | API がリソース ARN をサポートしない | [IAM for Rekognition](https://docs.aws.amazon.com/rekognition/latest/dg/security_iam_service-with-iam.html) |
| Amazon Textract | `textract:AnalyzeDocument`, `textract:DetectDocumentText` | 同期 API はリソース ARN をサポートしない | [IAM for Textract](https://docs.aws.amazon.com/textract/latest/dg/security_iam_service-with-iam.html) |
| Amazon Comprehend | `comprehend:DetectEntities`, `comprehend:DetectKeyPhrases`, `comprehend:DetectDominantLanguage` | 検出 API はリソース ARN をサポートしない | [IAM for Comprehend](https://docs.aws.amazon.com/comprehend/latest/dg/security_iam_service-with-iam.html) |
| AWS X-Ray | `xray:PutTraceSegments`, `xray:PutTelemetryRecords` | リソースレベルポリシー未サポート | [IAM for X-Ray](https://docs.aws.amazon.com/xray/latest/devguide/security_iam_service-with-iam.html) |

## cfn-guard suppression 例

```
# cfn-guard rule suppression for Rekognition (no resource-level IAM support)
let rekognition_actions = ["rekognition:DetectLabels", "rekognition:DetectModerationLabels"]
rule suppress_rekognition_wildcard when %rekognition_actions {
    # SUPPRESSED: Rekognition does not support resource-level policies
}
```

## cdk-nag suppression 例 (TypeScript)

```typescript
NagSuppressions.addResourceSuppressions(rekognitionRole, [
  {
    id: 'AwsSolutions-IAM5',
    reason: 'Rekognition APIs do not support resource-level IAM policies',
    appliesTo: ['Resource::*'],
  },
]);
```
