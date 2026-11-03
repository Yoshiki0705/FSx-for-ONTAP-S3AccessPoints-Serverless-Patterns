# CloudFormation / SAM の罠

> このファイルはリポジトリに含まれる（GitHub から読める）。ローカルの Kiro では
> `.kiro/steering/pitfalls-cfn-sam.md` が読み込み条件だけを持ち、
> 該当する作業をしているときにこの内容へ誘導する。`.kiro/` は公開しないため、
> 知識の本体は常にこちら側に置く。

## パターンのデプロイ経路（2026-08-12 実測）

各パターンのディレクトリで **`sam build && sam deploy`** を使う。UC15-UC28 の 14 本を
この方法でデプロイして確認済み。

**使わないもの**: `scripts/deploy_generic_ucs.sh` と `scripts/package_generic_uc.sh` は
現状動かない（各ファイル先頭に理由を書いた）。前者は 4 パターンが宣言していない
パラメータを無条件に渡して CloudFormation に即エラーにされ、後者はディレクトリ再編前の
パスを前提にしていて生成する S3 キーがテンプレートの期待と一致しない。
`template-deploy.yaml` は SAM を使えない利用者向けの**生成物**で、zip キーの命名が
7 パターンで実装と食い違い、1 パターンには存在しない。手で直さず、必要になったら生成し直す。

**渡し忘れると静かに壊れるパラメータ**: `S3AccessPointName`。空だと
`HasS3AccessPointName` が false になり、IAM ポリシーから accesspoint 形式の ARN が落ちて
S3 AP への読み書きが AccessDenied になる（bucket 形式の ARN では認可されない）。

**空値の渡し方はコマンドラインと設定ファイルで違う**（SAM CLI 1.162.1 で実測）:

- `sam deploy --parameter-overrides "Key="` は**拒否される**
  （`Key= is not a valid format`）。`ParameterKey=Key,ParameterValue=` を使う。
- `samconfig.toml` の `parameter_overrides = ["Key=", ...]` は**通る**。
  つまり samconfig.toml.example に書かれている `S3AccessPointName=` の形自体は有効で、
  問題は構文ではなく**空値そのものが上記の AccessDenied を招くこと**。

| Pitfall | Solution |
|---------|----------|
| `RecursiveDeleteOption` duplicate key in YAML | Single key only: `RecursiveDeleteOption: true` |
| `SNSPublishMessagePolicy` with TopicArn | Use `TopicName: !GetAtt Topic.TopicName` |
| `Handler: index.handler` but file is `handler.py` | Use `Handler: handler.handler` |
| `DefinitionBody` inline in SAM StateMachine | Use `DefinitionUri: statemachine/workflow.asl.json` |
| `S3ObjectStorageMode: REFERENCE` on `AWS::Serverless::Function` silently has no effect | Released SAM drops unrecognized `CodeUri` keys during transform, so `sam validate`/`sam deploy` succeed but the function runs in `COPY` mode. The SAM-side name is `StorageMode` (not `S3ObjectStorageMode`), added upstream in aws/serverless-application-model#3959 but **not in any release yet** (latest 1.111.0 predates the merge). Use a native `AWS::Lambda::Function` with `Code.S3ObjectStorageMode` meanwhile; mixing `AWS::Serverless::` and native `AWS::` resources in one template is confirmed supported. Silent-drop tracked in aws/serverless-application-model#3970. See docs/aws-feature-requests/lambda-healthomics-s3ap-gaps.md FR-7 |
| CloudFormation `validate-template` fails for large templates | Use S3 URL upload for templates >51KB |
| CFn deploy with `CAPABILITY_IAM` → InsufficientCapabilitiesException | Use `CAPABILITY_NAMED_IAM` (template creates named IAM roles). `--capabilities CAPABILITY_NAMED_IAM` |
| `AWS::Serverless::StateMachine` with `Logging` and an explicit `Policies` → `CreateStateMachine` fails: "not authorized to access the Log Destination" (2026-11-03) | SAM adds no log-delivery permissions when `Policies` is given. Add a statement for `logs:CreateLogDelivery`, `GetLogDelivery`, `UpdateLogDelivery`, `DeleteLogDelivery`, `ListLogDeliveries`, `PutLogEvents`, `PutResourcePolicy`, `DescribeResourcePolicies`, `DescribeLogGroups` with `Resource: "*"` (these actions take no resource ARN) |
| `sam deploy --parameter-overrides` with a JSON value arrives cut at the first `{` (2026-11-03) | Use `sam package` then `aws cloudformation deploy --parameter-overrides`, and read the value back with `describe-stacks` and compare. `scripts/deploy-japanese-document-ocr-agent.sh` does both |
| A non-ASCII character in a CloudFormation parameter value becomes `?`, also when set through the API (2026-11-03) | Pass ASCII-only JSON (`json.dumps(obj, ensure_ascii=True)` gives `\uXXXX`) and let the consumer parse it |
| A deleted SAM stack leaves its `AWS::Serverless::LayerVersion` versions behind (default `RetentionPolicy: Retain`), found by listing layers after a cleanup | Set `RetentionPolicy: Delete` when every consumer is in the same stack. Otherwise list and delete the versions in the cleanup script |
