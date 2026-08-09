# CloudFormation / SAM の罠

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/steering/pitfalls-cfn-sam.md` が読み込み条件だけを持ち、
> 該当する作業をしているときにこの内容へ誘導する。`.kiro/` は公開しないため、
> 知識の本体は常にこちら側に置く。

| Pitfall | Solution |
|---------|----------|
| `RecursiveDeleteOption` duplicate key in YAML | Single key only: `RecursiveDeleteOption: true` |
| `SNSPublishMessagePolicy` with TopicArn | Use `TopicName: !GetAtt Topic.TopicName` |
| `Handler: index.handler` but file is `handler.py` | Use `Handler: handler.handler` |
| `DefinitionBody` inline in SAM StateMachine | Use `DefinitionUri: statemachine/workflow.asl.json` |
| `S3ObjectStorageMode: REFERENCE` on `AWS::Serverless::Function` silently has no effect | Released SAM drops unrecognized `CodeUri` keys during transform, so `sam validate`/`sam deploy` succeed but the function runs in `COPY` mode. The SAM-side name is `StorageMode` (not `S3ObjectStorageMode`), added upstream in aws/serverless-application-model#3959 but **not in any release yet** (latest 1.111.0 predates the merge). Use a native `AWS::Lambda::Function` with `Code.S3ObjectStorageMode` meanwhile; mixing `AWS::Serverless::` and native `AWS::` resources in one template is confirmed supported. Silent-drop tracked in aws/serverless-application-model#3970. See docs/aws-feature-requests/lambda-healthomics-s3ap-gaps.md FR-7 |
| CloudFormation `validate-template` fails for large templates | Use S3 URL upload for templates >51KB |
| CFn deploy with `CAPABILITY_IAM` → InsufficientCapabilitiesException | Use `CAPABILITY_NAMED_IAM` (template creates named IAM roles). `--capabilities CAPABILITY_NAMED_IAM` |
