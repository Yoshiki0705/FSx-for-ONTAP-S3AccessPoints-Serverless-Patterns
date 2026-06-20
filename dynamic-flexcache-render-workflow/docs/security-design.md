# Dynamic FlexCache Workflow — セキュリティ設計

## IAM Least Privilege

### Lambda 実行ロール

```yaml
Policies:
  - PolicyName: DynamicFlexCacheMinimal
    PolicyDocument:
      Statement:
        # Secrets Manager（ONTAP 認証情報のみ）
        - Effect: Allow
          Action: secretsmanager:GetSecretValue
          Resource: !Sub 'arn:aws:secretsmanager:${AWS::Region}:${AWS::AccountId}:secret:${OntapSecretName}*'
        
        # S3（レポート出力のみ）
        - Effect: Allow
          Action: s3:PutObject
          Resource: !Sub '${OutputBucket.Arn}/*'
        
        # SNS（通知のみ）
        - Effect: Allow
          Action: sns:Publish
          Resource: !Ref NotificationTopic
```

### Step Functions 実行ロール

```yaml
Policies:
  - PolicyName: InvokeLambdaOnly
    PolicyDocument:
      Statement:
        - Effect: Allow
          Action: lambda:InvokeFunction
          Resource:
            - !GetAtt CreateFlexCacheFunction.Arn
            - !GetAtt SubmitJobFunction.Arn
            - !GetAtt MonitorJobFunction.Arn
            - !GetAtt CleanupFlexCacheFunction.Arn
            - !GetAtt ReportFunction.Arn
```

## Secrets Manager

### シークレット構造

```json
{
  "username": "flexcache_operator",
  "password": "<strong-password>"
}
```

### ローテーション

- 自動ローテーション推奨（30日間隔）
- ローテーション時は ONTAP 側のパスワードも同期更新が必要
- Lambda のキャッシュ（`_credentials`）はコールドスタート時にリフレッシュ

## ONTAP RBAC 最小権限

### FlexCache 操作用ロール

```bash
# ロール作成
security login role create -vserver svm1 \
  -role flexcache_operator \
  -cmddirname "volume flexcache create" -access all

security login role create -vserver svm1 \
  -role flexcache_operator \
  -cmddirname "volume flexcache delete" -access all

security login role create -vserver svm1 \
  -role flexcache_operator \
  -cmddirname "volume flexcache show" -access readonly

security login role create -vserver svm1 \
  -role flexcache_operator \
  -cmddirname "volume flexcache prepopulate start" -access all

security login role create -vserver svm1 \
  -role flexcache_operator \
  -cmddirname "job show" -access readonly

# ユーザー作成
security login create -vserver svm1 \
  -user-or-group-name flexcache_operator \
  -application http \
  -authentication-method password \
  -role flexcache_operator
```

## TLS Certificate Validation

```python
# デフォルト: TLS 検証有効
config = OntapClientConfig(
    management_ip="10.0.0.1",
    secret_name="fsxn/ontap-credentials",
    verify_ssl=True,  # デフォルト
)

# PoC/Lab のみ: TLS 検証無効（警告ログ出力）
config = OntapClientConfig(
    management_ip="10.0.0.1",
    secret_name="fsxn/ontap-credentials",
    verify_ssl=False,  # 本番では使用禁止
)
```

## S3 AP Policy

### Lambda からの S3 AP アクセス

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetObject"],
      "Resource": [
        "arn:aws:s3:ap-northeast-1:ACCOUNT:accesspoint/fsxn-cache-s3ap",
        "arn:aws:s3:ap-northeast-1:ACCOUNT:accesspoint/fsxn-cache-s3ap/object/*"
      ]
    }
  ]
}
```

## KMS 暗号化

- **S3 出力バケット**: SSE-KMS（aws/s3 マネージドキー）
- **SNS Topic**: KMS 暗号化（aws/sns）
- **DynamoDB**: 暗号化デフォルト有効
- **FSx for ONTAP volume**: FSx 管理の KMS キー

## Audit Logging

- **CloudTrail**: 全 API コール記録
- **ONTAP 監査ログ**: FlexCache 作成/削除操作
- **CloudWatch Logs**: Lambda 実行ログ（機密データはログに含めない）

## タグ付け

```yaml
Tags:
  - Key: Project
    Value: fsxn-s3ap-serverless-patterns
  - Key: Pattern
    Value: dynamic-flexcache-render-workflow
  - Key: JobId
    Value: !Ref JobId  # ジョブ単位の追跡
  - Key: Environment
    Value: !Ref Environment
```

## ユーザー入力バリデーション

```python
def validate_job_request(event: dict) -> None:
    """ジョブリクエストのバリデーション"""
    required_fields = ["job_id", "origin_volume", "origin_svm"]
    for field in required_fields:
        if field not in event or not event[field]:
            raise ValueError(f"Missing required field: {field}")
    
    # job_id のフォーマット検証（英数字とハイフンのみ）
    import re
    if not re.match(r'^[a-zA-Z0-9\-_]+$', event["job_id"]):
        raise ValueError("job_id must contain only alphanumeric, hyphens, underscores")
    
    # size_gb の範囲検証
    size_gb = event.get("size_gb", 100)
    if size_gb < 1 or size_gb > 10000:
        raise ValueError(f"size_gb must be between 1 and 10000, got {size_gb}")
```
